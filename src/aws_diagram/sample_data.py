from __future__ import annotations

from aws_diagram.models import DiagramModel, Edge, Group, Resource, RouteRow, RouteTable, Subnet


def build_sample_model(show_routes: bool = False) -> DiagramModel:
    subnets = [
        Subnet("subnet-public-a", "Example-Public-us-east-1a", "10.0.0.0/27", "us-east-1a", "public", "rtb-public-a"),
        Subnet("subnet-private-a", "Example-Private-us-east-1a", "10.0.0.64/27", "us-east-1a", "private", "rtb-private-a"),
        Subnet("subnet-db-a", "Example-Database-us-east-1a", "10.0.0.128/28", "us-east-1a", "database", "rtb-db-a"),
        Subnet("subnet-public-b", "Example-Public-us-east-1b", "10.0.0.32/27", "us-east-1b", "public", "rtb-public-b"),
        Subnet("subnet-private-b", "Example-Private-us-east-1b", "10.0.0.96/27", "us-east-1b", "private", "rtb-private-b"),
        Subnet("subnet-db-b", "Example-Database-us-east-1b", "10.0.0.144/28", "us-east-1b", "database", "rtb-db-b"),
    ]

    resources = [
        Resource("tgw-example", "transit_gateway", "Example", ["tgw-example", "tgw-attachment-example"], placement="edge"),
        Resource("tgw-peer", "tgw_peering", "Peering", ["tgw-peer-example"], placement="left"),
        Resource("igw", "internet_gateway", "Internet Gateway", ["igw-example"], placement="ingress"),
        Resource("waf", "waf", "Example-Web-ACL", ["web-acl-example"], placement="ingress"),
        Resource("public-elb", "alb", "Public-App-ALB", [], placement="ingress", public=True),
        Resource("test-lb", "alb", "Public-Web-ALB", [], placement="ingress", public=True),
        Resource("temp-lb", "alb", "Partner-Access-ALB", [], placement="ingress", public=True),
        Resource("mirror-elb", "alb", "Shared-Services-ALB", [], placement="ingress", public=True),
        Resource("sftp-elb", "nlb", "SFTP-NLB", ["198.51.100.20"], placement="ingress", public=True),
        Resource("nat-a", "nat_gateway", "NAT-us-east-1a", ["198.51.100.10", "10.0.0.10"], az="us-east-1a", subnet_id="subnet-public-a"),
        Resource("nat-b", "nat_gateway", "NAT-us-east-1b", ["198.51.100.11", "10.0.0.42"], az="us-east-1b", subnet_id="subnet-public-b"),
        Resource("app-a1", "ec2_instance", "App-Server-A1", ["10.0.0.73"], az="us-east-1a", subnet_id="subnet-private-a", group="sg-app-a"),
        Resource("web-a1", "ec2_instance", "Web-Server-A1", ["10.0.0.74"], az="us-east-1a", subnet_id="subnet-private-a", group="sg-app-a"),
        Resource("partner-a1", "ec2_instance", "Partner-Worker-A1", ["10.0.0.75"], az="us-east-1a", subnet_id="subnet-private-a", group="sg-app-a"),
        Resource("ops-a1", "ec2_instance", "Ops-Node-A1", ["10.0.0.76"], az="us-east-1a", subnet_id="subnet-private-a", group="sg-app-a"),
        Resource("shared-b1", "ec2_instance", "Shared-Node-B1", ["10.0.0.101"], az="us-east-1b", subnet_id="subnet-private-b", group="sg-app-b"),
        Resource("shared-b2", "ec2_instance", "Shared-Node-B2", ["10.0.0.102"], az="us-east-1b", subnet_id="subnet-private-b", group="sg-app-b"),
        Resource("api-b1", "ec2_instance", "API-Server-B1", ["10.0.0.103"], az="us-east-1b", subnet_id="subnet-private-b", group="sg-app-b"),
        Resource("db-a", "ec2_instance", "Database-Node-A", ["10.0.0.140"], az="us-east-1a", subnet_id="subnet-db-a", group="sg-db-a"),
        Resource("db-b", "ec2_instance", "Database-Node-B", ["10.0.0.141"], az="us-east-1b", subnet_id="subnet-db-b", group="sg-db-b"),
    ]

    groups = [
        Group("sg-app-a", "Example-App-Access", ["app-a1", "web-a1", "partner-a1", "ops-a1"], "security_group"),
        Group("sg-app-b", "Example-App-Access", ["shared-b1", "shared-b2", "api-b1"], "security_group"),
        Group("sg-db-a", "Example-Database", ["db-a"], "security_group"),
        Group("sg-db-b", "Example-Database", ["db-b"], "security_group"),
    ]

    edges = [
        Edge("tgw-peer", "tgw-example"),
        Edge("igw", "waf"),
        Edge("waf", "public-elb"),
        Edge("waf", "test-lb"),
        Edge("waf", "temp-lb"),
        Edge("waf", "mirror-elb"),
        Edge("igw", "sftp-elb"),
        Edge("public-elb", "app-a1"),
        Edge("test-lb", "web-a1"),
        Edge("temp-lb", "partner-a1"),
        Edge("mirror-elb", "shared-b1"),
        Edge("mirror-elb", "shared-b2"),
        Edge("sftp-elb", "app-a1"),
        Edge("tgw-example", "sftp-elb"),
    ]

    route_tables = [
        RouteTable(
            "rtb-public-a",
            "rtb-public-a",
            "VPC Route Table",
            ["Example-Public-us-east-1a"],
            [RouteRow("10.0.0.0/24", "local"), RouteRow("0.0.0.0/0", "igw-example")],
        ),
        RouteTable(
            "rtb-private-a",
            "rtb-private-a",
            "VPC Route Table",
            ["Example-Private-us-east-1a"],
            [RouteRow("10.0.0.0/24", "local"), RouteRow("0.0.0.0/0", "nat-a")],
        ),
        RouteTable(
            "rtb-db-a",
            "rtb-db-a",
            "VPC Route Table",
            ["Example-Database-us-east-1a"],
            [RouteRow("10.0.0.0/24", "local")],
        ),
    ]

    return DiagramModel(
        title="Example AWS",
        region="us-east-1",
        vpc_id="vpc-example",
        vpc_name="Example-App-VPC",
        vpc_cidr="10.0.0.0/24",
        azs=["us-east-1a", "us-east-1b"],
        subnets=subnets,
        resources=resources,
        groups=groups,
        edges=edges,
        route_tables=route_tables if show_routes else [],
    )
