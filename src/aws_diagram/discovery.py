from __future__ import annotations

import configparser
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from aws_diagram.models import DiagramModel, Edge, Group, Resource, RouteRow, RouteTable, Subnet


ACCOUNT_RE = re.compile(r":(\d{12}):")
TIER_ORDER = {"public": 0, "private": 1, "database": 2, "other": 3}
READ_ONLY_OPERATIONS = {
    ("sts", "get-caller-identity"),
    ("ec2", "describe-vpcs"),
    ("ec2", "describe-subnets"),
    ("ec2", "describe-route-tables"),
    ("ec2", "describe-internet-gateways"),
    ("ec2", "describe-nat-gateways"),
    ("ec2", "describe-instances"),
    ("ec2", "describe-security-groups"),
    ("ec2", "describe-vpn-connections"),
    ("ec2", "describe-vpn-gateways"),
    ("ec2", "describe-vpc-peering-connections"),
    ("ec2", "describe-vpc-endpoints"),
    ("ec2", "describe-transit-gateways"),
    ("ec2", "describe-transit-gateway-vpc-attachments"),
    ("ec2", "describe-transit-gateway-peering-attachments"),
    ("ec2", "describe-transit-gateway-route-tables"),
    ("ec2", "get-transit-gateway-route-table-associations"),
    ("ec2", "search-transit-gateway-routes"),
    ("elbv2", "describe-load-balancers"),
    ("elbv2", "describe-target-groups"),
    ("elbv2", "describe-target-health"),
    ("rds", "describe-db-instances"),
    ("wafv2", "list-web-acls"),
    ("wafv2", "list-resources-for-web-acl"),
}


class DiscoveryError(RuntimeError):
    pass


def _run_aws(
    profile: str | None,
    region: str,
    service: str,
    operation: str,
    extra_args: list[str] | None = None,
) -> dict:
    if (service, operation) not in READ_ONLY_OPERATIONS:
        raise DiscoveryError(f"Refusing non-read-only AWS CLI call: {service} {operation}")
    cmd = ["aws"]
    if profile:
        cmd.extend(["--profile", profile])
    cmd.extend(["--region", region, service, operation, "--output", "json"])
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DiscoveryError(result.stderr.strip() or f"aws {service} {operation} failed")
    return json.loads(result.stdout or "{}")


def _run_best_effort(
    profile: str | None,
    region: str,
    service: str,
    operation: str,
    extra_args: list[str] | None = None,
) -> dict:
    try:
        return _run_aws(profile, region, service, operation, extra_args)
    except DiscoveryError:
        return {}


def _normalize_profile_name(section_name: str) -> str:
    return section_name[len("profile ") :] if section_name.startswith("profile ") else section_name


def _account_from_profile_metadata(values: configparser.SectionProxy) -> str | None:
    if values.get("sso_account_id"):
        return values.get("sso_account_id")
    if values.get("aws_account_id"):
        return values.get("aws_account_id")
    role_arn = values.get("role_arn", "")
    match = ACCOUNT_RE.search(role_arn)
    if match:
        return match.group(1)
    return None


def resolve_profile(account: str, preferred_profile: str | None = None) -> str | None:
    if preferred_profile:
        return preferred_profile

    config = configparser.RawConfigParser()
    config.read([str(Path.home() / ".aws" / "config"), str(Path.home() / ".aws" / "credentials")])

    candidates: list[str] = []
    by_name: set[str] = set()
    exact_name = f"account-{account}"
    for section_name in config.sections():
        profile_name = _normalize_profile_name(section_name)
        profile_account = _account_from_profile_metadata(config[section_name])
        if profile_name == exact_name:
            return profile_name
        if profile_account == account:
            candidates.append(profile_name)
            by_name.add(profile_name)
            continue
        if account in profile_name:
            candidates.append(profile_name)
            by_name.add(profile_name)

    if exact_name in by_name:
        return exact_name
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return sorted(candidates)[0]
    return None


def _tag_name(resource: dict) -> str | None:
    for tag in resource.get("Tags", []) or []:
        if tag.get("Key") == "Name":
            return tag.get("Value")
    return None


def _select_vpc(vpcs: list[dict], selector: str) -> dict:
    normalized = selector.strip()
    for vpc in vpcs:
        if vpc.get("VpcId") == normalized:
            return vpc
    for vpc in vpcs:
        if (_tag_name(vpc) or "") == normalized:
            return vpc
    raise DiscoveryError(f"Could not find VPC {selector}")


def _public_subnet_ids(
    vpc_id: str,
    subnets: list[dict],
    route_tables: list[dict],
    internet_gateway_ids: set[str],
) -> tuple[set[str], dict[str, str | None]]:
    main_route_table = None
    subnet_route_table: dict[str, dict] = {}
    subnet_route_table_id: dict[str, str | None] = {}
    for route_table in route_tables:
        route_table_id = route_table.get("RouteTableId")
        for association in route_table.get("Associations", []):
            if association.get("Main"):
                main_route_table = route_table
            subnet_id = association.get("SubnetId")
            if subnet_id:
                subnet_route_table[subnet_id] = route_table
                subnet_route_table_id[subnet_id] = route_table_id

    public_ids: set[str] = set()
    for subnet in subnets:
        if subnet["VpcId"] != vpc_id:
            continue
        route_table = subnet_route_table.get(subnet["SubnetId"], main_route_table)
        subnet_route_table_id.setdefault(
            subnet["SubnetId"],
            route_table.get("RouteTableId") if route_table else None,
        )
        if not route_table:
            continue
        for route in route_table.get("Routes", []):
            gateway_id = route.get("GatewayId", "")
            if route.get("DestinationCidrBlock") == "0.0.0.0/0" and gateway_id in internet_gateway_ids:
                public_ids.add(subnet["SubnetId"])
                break
    return public_ids, subnet_route_table_id


def _route_target(route: dict) -> str:
    for field in (
        "GatewayId",
        "NatGatewayId",
        "TransitGatewayId",
        "VpcPeeringConnectionId",
        "VpcEndpointId",
        "NetworkInterfaceId",
        "InstanceId",
        "LocalGatewayId",
        "CarrierGatewayId",
        "CoreNetworkArn",
        "EgressOnlyInternetGatewayId",
    ):
        value = route.get(field)
        if value:
            return value
    if route.get("DestinationPrefixListId"):
        return route["DestinationPrefixListId"]
    return "local"


def _route_destination(route: dict) -> str:
    return (
        route.get("DestinationCidrBlock")
        or route.get("DestinationIpv6CidrBlock")
        or route.get("DestinationPrefixListId")
        or "unknown"
    )


def _collapse_routes(routes: list[dict]) -> list[RouteRow]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    passthrough: list[RouteRow] = []
    for route in routes:
        destination = _route_destination(route)
        target = _route_target(route)
        note = route.get("State", "")
        if note and note != "active":
            passthrough.append(RouteRow(destination, target, note))
            continue
        grouped[(target, note)].append(destination)

    collapsed: list[RouteRow] = []
    for (target, note), destinations in sorted(grouped.items()):
        if len(destinations) > 6:
            collapsed.append(RouteRow(f"{len(destinations)} destinations", target, "collapsed"))
            continue
        for destination in sorted(destinations):
            collapsed.append(RouteRow(destination, target, note))
    return collapsed + passthrough


def _sanitize_group_id(prefix: str, label: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f"{prefix}-{normalized or 'group'}"


def _resource_details(*values: str | None) -> list[str]:
    details = []
    for value in values:
        if value:
            details.append(value)
    return details


def _named_value(resource: dict, fallback: str | None = None) -> str | None:
    return _tag_name(resource) or fallback


def _load_balancer_details(load_balancer: dict) -> list[str]:
    ip_addresses = []
    for zone in load_balancer.get("AvailabilityZones", []):
        for address in zone.get("LoadBalancerAddresses", []) or []:
            if address.get("IpAddress"):
                ip_addresses.append(address["IpAddress"])
    if ip_addresses:
        return [", ".join(ip_addresses[:4])]
    if load_balancer.get("DNSName"):
        return [load_balancer["DNSName"]]
    return []


def _subnet_tier(
    subnet: dict,
    public_ids: set[str],
    database_subnet_ids: set[str],
) -> str:
    subnet_id = subnet["SubnetId"]
    if subnet_id in public_ids:
        return "public"
    name = (_tag_name(subnet) or "").lower()
    if subnet_id in database_subnet_ids or any(token in name for token in ("db", "database", "rds")):
        return "database"
    return "private"


def _collect_route_tables(
    route_tables: list[dict],
    subnet_name_by_id: dict[str, str],
    vpc_id: str,
) -> list[RouteTable]:
    tables: list[RouteTable] = []
    for route_table in route_tables:
        if route_table.get("VpcId") != vpc_id:
            continue
        associations = []
        for association in route_table.get("Associations", []):
            subnet_id = association.get("SubnetId")
            if subnet_id and subnet_id in subnet_name_by_id:
                associations.append(subnet_name_by_id[subnet_id])
            elif association.get("Main"):
                associations.append("Main")
        label = _tag_name(route_table) or route_table["RouteTableId"]
        tables.append(
            RouteTable(
                route_table["RouteTableId"],
                label,
                "VPC Route Table",
                sorted(associations),
                _collapse_routes(route_table.get("Routes", [])),
            )
        )
    return tables


def _collect_tgw_route_tables(
    profile: str | None,
    region: str,
    transit_gateway_ids: set[str],
) -> list[RouteTable]:
    if not transit_gateway_ids:
        return []

    route_tables = _run_best_effort(profile, region, "ec2", "describe-transit-gateway-route-tables").get(
        "TransitGatewayRouteTables",
        [],
    )
    tables: list[RouteTable] = []
    for table in route_tables:
        if table.get("TransitGatewayId") not in transit_gateway_ids:
            continue
        table_id = table["TransitGatewayRouteTableId"]
        associations_resp = _run_best_effort(
            profile,
            region,
            "ec2",
            "get-transit-gateway-route-table-associations",
            ["--transit-gateway-route-table-id", table_id],
        )
        routes_resp = _run_best_effort(
            profile,
            region,
            "ec2",
            "search-transit-gateway-routes",
            ["--transit-gateway-route-table-id", table_id, "--filters", "Name=state,Values=active"],
        )
        associations = []
        for association in associations_resp.get("Associations", []):
            resource_id = association.get("ResourceId")
            if resource_id:
                associations.append(resource_id)
        rows = []
        for route in routes_resp.get("Routes", []):
            attachments = []
            for attachment in route.get("TransitGatewayAttachments", []):
                attachment_id = attachment.get("ResourceId") or attachment.get("TransitGatewayAttachmentId")
                if attachment_id:
                    attachments.append(attachment_id)
            rows.append(
                RouteRow(
                    route.get("DestinationCidrBlock", "unknown"),
                    ", ".join(attachments) or "attachment",
                    route.get("State", ""),
                )
            )
        tables.append(
            RouteTable(
                table_id,
                table.get("Tags", [{}])[0].get("Value") or table_id,
                "Transit Gateway Route Table",
                sorted(associations),
                rows[:20],
            )
        )
    return tables


def _collect_waf_edges(
    profile: str | None,
    region: str,
    external_lbs: list[dict],
) -> tuple[list[Resource], list[Edge]]:
    waf_resources: list[Resource] = []
    waf_edges: list[Edge] = []
    if not external_lbs:
        return waf_resources, waf_edges

    lb_arns = {load_balancer["LoadBalancerArn"]: f"lb-{load_balancer['LoadBalancerName']}" for load_balancer in external_lbs}
    response = _run_best_effort(profile, region, "wafv2", "list-web-acls", ["--scope", "REGIONAL"])
    for web_acl in response.get("WebACLs", []):
        associations = _run_best_effort(
            profile,
            region,
            "wafv2",
            "list-resources-for-web-acl",
            ["--web-acl-arn", web_acl["ARN"], "--resource-type", "APPLICATION_LOAD_BALANCER"],
        )
        matched_targets = [lb_arns[arn] for arn in associations.get("ResourceArns", []) if arn in lb_arns]
        if not matched_targets:
            continue
        resource_id = f"waf-{web_acl['Name']}"
        waf_resources.append(Resource(resource_id, "waf", web_acl["Name"], [web_acl["Id"]], placement="ingress"))
        for target in matched_targets:
            waf_edges.append(Edge(resource_id, target))
    return waf_resources, waf_edges


def discover_account(
    account: str,
    region: str,
    vpc: str,
    profile: str | None = None,
    show_routes: bool = False,
) -> DiagramModel:
    resolved_profile = resolve_profile(account, profile)
    if profile is None and resolved_profile is None:
        raise DiscoveryError(
            f"Could not resolve an AWS profile for account {account} from ~/.aws/config or ~/.aws/credentials. "
            "Use --profile to override if needed."
        )

    identity = _run_aws(resolved_profile, region, "sts", "get-caller-identity")
    actual_account = identity.get("Account")
    if actual_account != account:
        profile_hint = resolved_profile or "default AWS CLI profile"
        raise DiscoveryError(
            f"AWS CLI resolved to account {actual_account}, but requested account {account}. "
            f"Current context: {profile_hint}."
        )

    vpcs = _run_aws(resolved_profile, region, "ec2", "describe-vpcs").get("Vpcs", [])
    subnets = _run_aws(resolved_profile, region, "ec2", "describe-subnets").get("Subnets", [])
    route_tables = _run_aws(resolved_profile, region, "ec2", "describe-route-tables").get("RouteTables", [])
    internet_gateways = _run_aws(resolved_profile, region, "ec2", "describe-internet-gateways").get("InternetGateways", [])
    nat_gateways = _run_aws(resolved_profile, region, "ec2", "describe-nat-gateways").get("NatGateways", [])
    reservations = _run_aws(resolved_profile, region, "ec2", "describe-instances").get("Reservations", [])
    security_groups = _run_aws(resolved_profile, region, "ec2", "describe-security-groups").get("SecurityGroups", [])
    load_balancers = _run_aws(resolved_profile, region, "elbv2", "describe-load-balancers").get("LoadBalancers", [])
    target_groups = _run_aws(resolved_profile, region, "elbv2", "describe-target-groups").get("TargetGroups", [])
    db_instances = _run_aws(resolved_profile, region, "rds", "describe-db-instances").get("DBInstances", [])
    vpn_connections = _run_best_effort(resolved_profile, region, "ec2", "describe-vpn-connections").get("VpnConnections", [])
    vpn_gateways = _run_best_effort(resolved_profile, region, "ec2", "describe-vpn-gateways").get("VpnGateways", [])
    vpc_peering_connections = _run_best_effort(
        resolved_profile,
        region,
        "ec2",
        "describe-vpc-peering-connections",
    ).get("VpcPeeringConnections", [])
    vpc_endpoints = _run_best_effort(resolved_profile, region, "ec2", "describe-vpc-endpoints").get("VpcEndpoints", [])
    transit_gateways = _run_best_effort(
        resolved_profile,
        region,
        "ec2",
        "describe-transit-gateways",
    ).get("TransitGateways", [])
    tgw_vpc_attachments = _run_best_effort(
        resolved_profile,
        region,
        "ec2",
        "describe-transit-gateway-vpc-attachments",
    ).get("TransitGatewayVpcAttachments", [])
    tgw_peering_attachments = _run_best_effort(
        resolved_profile,
        region,
        "ec2",
        "describe-transit-gateway-peering-attachments",
    ).get("TransitGatewayPeeringAttachments", [])

    selected_vpc = _select_vpc(vpcs, vpc)
    vpc_id = selected_vpc["VpcId"]
    vpc_name = _tag_name(selected_vpc) or vpc_id
    vpc_cidr = selected_vpc.get("CidrBlock", "")

    vpc_subnets = [subnet for subnet in subnets if subnet.get("VpcId") == vpc_id]
    if not vpc_subnets:
        raise DiscoveryError(f"No subnets found in VPC {vpc_id}")

    subnet_lookup = {subnet["SubnetId"]: subnet for subnet in vpc_subnets}
    security_group_name = {sg["GroupId"]: sg.get("GroupName", sg["GroupId"]) for sg in security_groups}
    attached_igws = {
        igw["InternetGatewayId"]
        for igw in internet_gateways
        for attachment in igw.get("Attachments", [])
        if attachment.get("VpcId") == vpc_id
    }
    public_ids, route_table_by_subnet = _public_subnet_ids(vpc_id, vpc_subnets, route_tables, attached_igws)

    database_subnet_ids: set[str] = set()
    for db in db_instances:
        subnet_group = db.get("DBSubnetGroup", {})
        if subnet_group.get("VpcId") != vpc_id:
            continue
        for db_subnet in subnet_group.get("Subnets", []):
            if db_subnet.get("SubnetIdentifier") in subnet_lookup:
                database_subnet_ids.add(db_subnet["SubnetIdentifier"])

    subnet_models = [
        Subnet(
            id=subnet["SubnetId"],
            name=_tag_name(subnet) or subnet["SubnetId"],
            cidr=subnet.get("CidrBlock", ""),
            az=subnet["AvailabilityZone"],
            tier=_subnet_tier(subnet, public_ids, database_subnet_ids),
            route_table_id=route_table_by_subnet.get(subnet["SubnetId"]),
        )
        for subnet in sorted(vpc_subnets, key=lambda item: (item["AvailabilityZone"], TIER_ORDER[_subnet_tier(item, public_ids, database_subnet_ids)], item.get("CidrBlock", "")))
    ]
    azs = sorted({subnet.az for subnet in subnet_models})
    subnet_name_by_id = {subnet.id: subnet.name for subnet in subnet_models}

    resources: list[Resource] = []
    groups: dict[str, Group] = {}
    edges: list[Edge] = []
    warnings: list[str] = []
    internal_service_targets: list[str] = []
    endpoint_targets: list[str] = []

    transit_gateway_labels = {
        gateway["TransitGatewayId"]: _named_value(gateway)
        for gateway in transit_gateways
        if gateway.get("TransitGatewayId")
    }
    transit_gateway_resource_ids: dict[str, str] = {}

    if attached_igws:
        resources.append(Resource("igw", "internet_gateway", "Internet Gateway", sorted(attached_igws), placement="ingress"))

    transit_gateway_ids: set[str] = set()
    for attachment in tgw_vpc_attachments:
        if attachment.get("VpcId") != vpc_id or attachment.get("State") not in {"available", "pending"}:
            continue
        transit_gateway_id = attachment.get("TransitGatewayId")
        attachment_id = attachment.get("TransitGatewayAttachmentId")
        if not transit_gateway_id:
            continue
        transit_gateway_ids.add(transit_gateway_id)
        tgw_label = transit_gateway_labels.get(transit_gateway_id)
        if not tgw_label:
            continue
        resource_id = f"tgw-{transit_gateway_id}"
        if not any(resource.id == resource_id for resource in resources):
            resources.append(
                Resource(
                    resource_id,
                    "transit_gateway",
                    tgw_label,
                    _resource_details(transit_gateway_id, attachment_id),
                    placement="edge",
                )
            )
            transit_gateway_resource_ids[transit_gateway_id] = resource_id

    attached_vpn_gateways = {
        gateway["VpnGatewayId"]
        for gateway in vpn_gateways
        for attachment in gateway.get("VpcAttachments", [])
        if attachment.get("VpcId") == vpc_id
    }

    for peering in vpc_peering_connections:
        requester = peering.get("RequesterVpcInfo", {})
        accepter = peering.get("AccepterVpcInfo", {})
        if requester.get("VpcId") != vpc_id and accepter.get("VpcId") != vpc_id:
            continue
        peer_vpc = accepter if requester.get("VpcId") == vpc_id else requester
        peer_vpc_id = peer_vpc.get("VpcId")
        peer_owner = peer_vpc.get("OwnerId")
        resources.append(
            Resource(
                id=f"pcx-{peering['VpcPeeringConnectionId']}",
                kind="vpc_peering",
                label=_named_value(peering, peering["VpcPeeringConnectionId"]),
                details=_resource_details(peer_vpc_id, peer_owner, peering.get("Status", {}).get("Code")),
                placement="left",
            )
        )

    for attachment in tgw_peering_attachments:
        if attachment.get("State") not in {"available", "pendingAcceptance", "pending"}:
            continue
        local_tgw_id = attachment.get("TransitGatewayId")
        peer_tgw_id = attachment.get("PeerTransitGatewayId")
        if local_tgw_id not in transit_gateway_ids and peer_tgw_id not in transit_gateway_ids:
            continue
        resource_id = f"tgw-peering-{attachment['TransitGatewayAttachmentId']}"
        resources.append(
            Resource(
                resource_id,
                "tgw_peering",
                _named_value(attachment, attachment["TransitGatewayAttachmentId"]),
                _resource_details(attachment.get("PeerRegion"), attachment.get("PeerAccountId"), peer_tgw_id),
                placement="left",
            )
        )
        local_resource_id = transit_gateway_resource_ids.get(local_tgw_id) or transit_gateway_resource_ids.get(peer_tgw_id)
        if local_resource_id:
            edges.append(Edge(resource_id, local_resource_id))

    for nat in nat_gateways:
        if nat.get("VpcId") != vpc_id or nat.get("State") != "available":
            continue
        subnet_id = nat.get("SubnetId")
        subnet = subnet_lookup.get(subnet_id)
        if not subnet:
            continue
        addresses = nat.get("NatGatewayAddresses", [])
        public_ip = next((address.get("PublicIp") for address in addresses if address.get("PublicIp")), None)
        private_ip = next((address.get("PrivateIp") for address in addresses if address.get("PrivateIp")), None)
        resources.append(
            Resource(
                id=f"nat-{nat['NatGatewayId']}",
                kind="nat_gateway",
                label=_tag_name(nat) or "NAT Gateway",
                details=_resource_details(public_ip, private_ip),
                az=subnet["AvailabilityZone"],
                subnet_id=subnet_id,
            )
        )

    instances = []
    for reservation in reservations:
        for instance in reservation.get("Instances", []):
            if instance.get("SubnetId") not in subnet_lookup:
                continue
            if instance.get("State", {}).get("Name") not in {"running", "pending", "stopped"}:
                continue
            instances.append(instance)

    instance_resource_ids: dict[str, str] = {}
    for instance in instances:
        subnet = subnet_lookup[instance["SubnetId"]]
        group_label = None
        for tag in instance.get("Tags", []) or []:
            if tag.get("Key") == "aws:autoscaling:groupName":
                group_label = tag.get("Value")
                group_kind = "auto_scaling_group"
                break
        else:
            if instance.get("SecurityGroups"):
                first_group = instance["SecurityGroups"][0]
                group_label = security_group_name.get(first_group.get("GroupId"), first_group.get("GroupName"))
                group_kind = "security_group"
            else:
                group_kind = "group"

        resource_id = instance["InstanceId"]
        instance_resource_ids[instance["InstanceId"]] = resource_id
        resources.append(
            Resource(
                id=resource_id,
                kind="ec2_instance",
                label=_tag_name(instance) or instance["InstanceId"],
                details=_resource_details(instance.get("PublicIpAddress"), instance.get("PrivateIpAddress")),
                az=subnet["AvailabilityZone"],
                subnet_id=instance["SubnetId"],
                group=_sanitize_group_id(group_kind, group_label) if group_label else None,
                public=bool(instance.get("PublicIpAddress")),
            )
        )
        if group_label:
            group_id = _sanitize_group_id(group_kind, group_label)
            groups.setdefault(group_id, Group(group_id, group_label, kind=group_kind)).member_ids.append(resource_id)

    load_balancers_in_vpc = [lb for lb in load_balancers if lb.get("VpcId") == vpc_id]
    lb_resource_ids: dict[str, str] = {}
    for load_balancer in load_balancers_in_vpc:
        lb_id = f"lb-{load_balancer['LoadBalancerName']}"
        lb_resource_ids[load_balancer["LoadBalancerArn"]] = lb_id
        kind = "nlb" if load_balancer.get("Type") == "network" else "alb"
        placement = "ingress" if load_balancer.get("Scheme") == "internet-facing" else "service"
        resources.append(
            Resource(
                id=lb_id,
                kind=kind,
                label=load_balancer["LoadBalancerName"],
                details=_load_balancer_details(load_balancer),
                placement=placement,
                public=placement == "ingress",
                internal=placement == "service",
            )
        )
        if placement == "service":
            internal_service_targets.append(lb_id)

    interface_endpoints = [
        endpoint
        for endpoint in vpc_endpoints
        if endpoint.get("VpcId") == vpc_id and endpoint.get("VpcEndpointType") in {"Interface", "GatewayLoadBalancer"}
    ]
    for endpoint in interface_endpoints:
        service_name = endpoint.get("ServiceName", "")
        short_name = service_name.split(".")[-1] if service_name else endpoint["VpcEndpointId"]
        resources.append(
            Resource(
                id=f"vpce-{endpoint['VpcEndpointId']}",
                kind="privatelink",
                label=_named_value(endpoint, short_name),
                details=_resource_details(endpoint["VpcEndpointId"], endpoint.get("VpcEndpointType"), service_name),
                placement="service",
                internal=True,
            )
        )
        endpoint_targets.append(f"vpce-{endpoint['VpcEndpointId']}")

    internet_facing_lbs = [lb for lb in load_balancers_in_vpc if lb.get("Scheme") == "internet-facing"]
    waf_resources, waf_edges = _collect_waf_edges(resolved_profile, region, internet_facing_lbs)
    resources.extend(waf_resources)
    edges.extend(waf_edges)

    for load_balancer in internet_facing_lbs:
        target_resource = lb_resource_ids[load_balancer["LoadBalancerArn"]]
        if waf_edges:
            if not any(edge.target == target_resource for edge in waf_edges):
                edges.append(Edge("igw", target_resource))
        else:
            edges.append(Edge("igw", target_resource))

    for instance in instances:
        if instance.get("PublicIpAddress"):
            edges.append(Edge("igw", instance_resource_ids[instance["InstanceId"]]))

    target_group_ids_by_lb: dict[str, list[str]] = defaultdict(list)
    for target_group in target_groups:
        for lb_arn in target_group.get("LoadBalancerArns", []):
            if lb_arn in lb_resource_ids:
                target_group_ids_by_lb[lb_arn].append(target_group["TargetGroupArn"])

    for lb_arn, target_group_arns in target_group_ids_by_lb.items():
        source = lb_resource_ids[lb_arn]
        for target_group_arn in target_group_arns:
            health = _run_best_effort(
                resolved_profile,
                region,
                "elbv2",
                "describe-target-health",
                ["--target-group-arn", target_group_arn],
            )
            for target in health.get("TargetHealthDescriptions", []):
                target_id = target.get("Target", {}).get("Id")
                if target_id in instance_resource_ids:
                    edges.append(Edge(source, instance_resource_ids[target_id]))

    for db in db_instances:
        subnet_group = db.get("DBSubnetGroup", {})
        if subnet_group.get("VpcId") != vpc_id:
            continue
        security_group_ids = [group["VpcSecurityGroupId"] for group in db.get("VpcSecurityGroups", [])]
        group_label = security_group_name.get(security_group_ids[0]) if security_group_ids else None
        group_id = _sanitize_group_id("security-group", group_label) if group_label else None
        if group_label:
            groups.setdefault(group_id, Group(group_id, group_label, kind="security_group"))
        for db_subnet in subnet_group.get("Subnets", []):
            subnet_id = db_subnet.get("SubnetIdentifier")
            subnet = subnet_lookup.get(subnet_id)
            if not subnet:
                continue
            resource_id = f"rds-{db['DBInstanceIdentifier']}-{subnet_id}"
            endpoint = db.get("Endpoint", {}).get("Address")
            resources.append(
                Resource(
                    id=resource_id,
                    kind="rds",
                    label=db["DBInstanceIdentifier"],
                    details=_resource_details(endpoint),
                    az=subnet["AvailabilityZone"],
                    subnet_id=subnet_id,
                    group=group_id,
                )
            )
            if group_id:
                groups[group_id].member_ids.append(resource_id)

    for vpn in vpn_connections:
        include = False
        if vpn.get("VpnGatewayId") in attached_vpn_gateways:
            include = True
        if vpn.get("TransitGatewayId") in transit_gateway_ids:
            include = True
        if not include:
            continue
        outside_ips = [telemetry.get("OutsideIpAddress") for telemetry in vpn.get("VgwTelemetry", []) if telemetry.get("OutsideIpAddress")]
        resource_id = f"vpn-{vpn['VpnConnectionId']}"
        resources.append(
            Resource(
                resource_id,
                "vpn_connection",
                _tag_name(vpn) or vpn["VpnConnectionId"],
                outside_ips[:4],
                placement="left",
            )
        )
        if vpn.get("TransitGatewayId") in transit_gateway_resource_ids:
            edges.append(Edge(resource_id, transit_gateway_resource_ids[vpn["TransitGatewayId"]]))

    route_table_models: list[RouteTable] = []
    if show_routes:
        route_table_models = _collect_route_tables(route_tables, subnet_name_by_id, vpc_id)
        route_table_models.extend(_collect_tgw_route_tables(resolved_profile, region, transit_gateway_ids))

    service_targets = internal_service_targets + endpoint_targets
    for peering in [resource for resource in resources if resource.kind == "vpc_peering"]:
        peering_target = endpoint_targets[0] if endpoint_targets else (internal_service_targets[0] if internal_service_targets else None)
        if peering_target:
            edges.append(Edge(peering.id, peering_target))

    named_tgws = [transit_gateway_resource_ids[tgw_id] for tgw_id in sorted(transit_gateway_resource_ids)]
    primary_tgw_target = internal_service_targets[0] if internal_service_targets else (endpoint_targets[0] if endpoint_targets else None)
    if named_tgws and primary_tgw_target:
        edges.append(Edge(named_tgws[0], primary_tgw_target))

    resources.sort(
        key=lambda resource: (
            {"left": 0, "edge": 1, "ingress": 2, "service": 3, "subnet": 4}.get(resource.placement, 5),
            resource.az or "",
            resource.label.lower(),
        )
    )

    if show_routes and not route_table_models:
        warnings.append("No route tables were discovered for this VPC scope.")

    return DiagramModel(
        title=f"AWS Architecture Diagram {vpc_name}",
        region=region,
        vpc_id=vpc_id,
        vpc_name=vpc_name,
        vpc_cidr=vpc_cidr,
        azs=azs,
        subnets=subnet_models,
        resources=resources,
        groups=list(groups.values()),
        edges=edges,
        route_tables=route_table_models,
        warnings=warnings,
    )
