from __future__ import annotations

import re
from dataclasses import dataclass, field

from aws_diagram.models import DiagramModel, Group, Resource, RouteTable, SecurityGroupRule, SecurityGroupSummary, Subnet


TIER_ORDER = ("public", "private", "database")
HEADER_COLOR = {
    "public": "#7AA116",
    "private": "#00A4A6",
    "database": "#00A4A6",
}


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2


@dataclass
class GroupLayout:
    group: Group
    box: Rect
    member_ids: list[str]


@dataclass
class NodeLayout:
    id: str
    kind: str
    label: str
    details: list[str]
    box: Rect
    icon: Rect
    style: str
    text_x: int
    text_y: int
    text_anchor: str = "start"
    resource: Resource | None = None


@dataclass
class SubnetLayout:
    subnet: Subnet
    box: Rect
    header_color: str
    title_x: int
    title_y: int
    cidr_x: int
    cidr_y: int
    group_layouts: list[GroupLayout] = field(default_factory=list)
    ungrouped_ids: list[str] = field(default_factory=list)


@dataclass
class RouteTableLayout:
    table: RouteTable
    box: Rect


@dataclass
class DiagramLayout:
    canvas_width: int
    canvas_height: int
    outer: Rect
    vpc: Rect
    corridor: Rect
    public_band: Rect
    service_band: Rect
    public_lb_group_box: Rect | None
    az_boxes: dict[str, Rect]
    subnet_layouts: dict[str, SubnetLayout]
    node_layouts: dict[str, NodeLayout]
    route_table_layouts: list[RouteTableLayout]
    actual_resource_ids: set[str]
    public_lb_ids: list[str]
    ingress_lb_ids: list[str]
    service_ids: list[str]
    left_ids: list[str]
    edge_ids: list[str]
    title_text: str
    title_pos: Point
    aws_cloud_icon: Rect
    subtitle_text: str
    subtitle_pos: Point
    footer_vpc_text: str
    footer_vpc_pos: Point
    footer_region_text: str
    footer_region_pos: Point
    flow_label_text: str | None = None
    flow_label_pos: Point | None = None
    public_lb_caption: str | None = None
    public_lb_caption_pos: Point | None = None


def _brand_title(vpc_name: str) -> str:
    tokens = [token for token in re.split(r"[-_\s]+", vpc_name) if token]
    if not tokens:
        return "AWS"
    return f"{tokens[0].title()} AWS"


def _display_items(resources: list[Resource]) -> tuple[dict[str, list[Resource]], list[Resource]]:
    grouped: dict[str, list[Resource]] = {}
    ungrouped: list[Resource] = []
    for resource in resources:
        if resource.group:
            grouped.setdefault(resource.group, []).append(resource)
        else:
            ungrouped.append(resource)
    return grouped, ungrouped


def _group_height(member_count: int) -> int:
    return 34 + member_count * 68


def _subnet_content_height(resources: list[Resource], tier: str) -> int:
    grouped, ungrouped = _display_items(resources)
    if tier == "public":
        row_count = len(ungrouped) + sum(len(members) for members in grouped.values())
        return max(110, 30 + row_count * 68)

    height = 20
    for members in grouped.values():
        height += _group_height(len(members)) + 16
    if ungrouped:
        height += len(ungrouped) * 68 + 12
    minimum = 180 if tier == "private" else 130
    return max(minimum, height)


def _subnets_for_tier_az(subnets: list[Subnet], tier: str, az: str) -> list[Subnet]:
    return sorted(
        [subnet for subnet in subnets if subnet.tier == tier and subnet.az == az],
        key=lambda subnet: (subnet.name.lower(), subnet.cidr, subnet.id),
    )


def _subnet_stack_height(
    subnets: list[Subnet],
    resources_by_subnet: dict[str, list[Resource]],
    tier: str,
) -> int:
    if not subnets:
        return 0
    heights = [_subnet_content_height(resources_by_subnet.get(subnet.id, []), tier) for subnet in subnets]
    return sum(heights) + max(0, len(heights) - 1) * 18


def _route_table_height(table: RouteTable) -> int:
    return 92 + len(table.rows[:18]) * 24


def _rule_source_line_count(rule: SecurityGroupRule, width: int = 72) -> int:
    lines = 1
    current = 0
    for source in rule.sources:
        source_length = len(source) + (2 if current else 0)
        if current and current + source_length > width:
            lines += 1
            current = len(source)
        else:
            current += source_length
    return lines


def _wrapped_item_line_count(items: list[str], width: int = 88) -> int:
    lines = 1
    current = 0
    for item in items:
        item_length = len(item) + (2 if current else 0)
        if current and current + item_length > width:
            lines += 1
            current = len(item)
        else:
            current += item_length
    return lines


def _security_group_height(group: SecurityGroupSummary) -> int:
    rules = group.inbound + group.outbound
    attached_extra = max(0, _wrapped_item_line_count(group.attached_to) - 1) * 16
    rule_height = sum(max(22, _rule_source_line_count(rule) * 14 + 8) for rule in rules)
    return max(128, 78 + attached_extra + rule_height)


def _security_group_appendix_height(groups: list[SecurityGroupSummary]) -> int:
    if not groups:
        return 0
    columns = 2
    column_heights = [0] * columns
    for index, group in enumerate(groups):
        column_heights[index % columns] += _security_group_height(group) + 18
    return 92 + max(column_heights)


def _public_lb_caption(resources: list[Resource]) -> str | None:
    return None


def _prefers_vertical_label(label: str) -> bool:
    if len(label) >= 22:
        return True
    return len(label) >= 18 and label.count("-") >= 3


def build_layout(model: DiagramModel) -> DiagramLayout:
    group_lookup = {group.id: group for group in model.groups}
    subnet_lookup = {subnet.id: subnet for subnet in model.subnets}
    resource_lookup = {resource.id: resource for resource in model.resources}

    resources_by_subnet: dict[str, list[Resource]] = {}
    for resource in model.resources:
        if resource.subnet_id:
            resources_by_subnet.setdefault(resource.subnet_id, []).append(resource)

    igw = next((resource for resource in model.resources if resource.kind == "internet_gateway"), None)
    wafs = [resource for resource in model.resources if resource.kind == "waf"]
    lb_band_resources = [
        resource
        for resource in model.resources
        if resource.kind in {"alb", "nlb"} and not resource.subnet_id and resource.placement in {"ingress", "service"}
    ]
    ingress_lbs = [resource for resource in lb_band_resources if resource.public]
    service_resources = [
        resource
        for resource in model.resources
        if not resource.subnet_id
        and resource not in lb_band_resources
        and resource.kind not in {"internet_gateway", "waf"}
        and resource.placement != "left"
        and resource.placement != "edge"
    ]
    left_resources = [resource for resource in model.resources if resource.placement == "left"]
    edge_resources = [resource for resource in model.resources if resource.placement == "edge"]

    content_height_by_tier: dict[str, int] = {}
    outer_height_by_tier: dict[str, int] = {}
    for tier in TIER_ORDER:
        tier_subnets = [subnet for subnet in model.subnets if subnet.tier == tier]
        if not tier_subnets:
            content_height_by_tier[tier] = 0
            outer_height_by_tier[tier] = 0
            continue
        content_height = max(
            _subnet_stack_height(_subnets_for_tier_az(model.subnets, tier, az), resources_by_subnet, tier)
            for az in model.azs
        )
        content_height_by_tier[tier] = content_height
        if tier == "public":
            outer_height_by_tier[tier] = max(320, content_height + 170)
        elif tier == "private":
            outer_height_by_tier[tier] = max(420, content_height + 110)
        else:
            outer_height_by_tier[tier] = max(280, content_height + 90)

    az_count = max(1, len(model.azs))
    subnet_width = 360
    left_column_width = 190 if left_resources else 90
    public_lb_count = max(1, len(lb_band_resources))
    service_count = max(1, len(service_resources))
    corridor_width = max(300, public_lb_count * 175 + 140, service_count * 230 + 60)
    az_gap = corridor_width // max(1, az_count - 1) if az_count > 1 else 120
    az_box_width = subnet_width + 24

    outer_x = 40
    outer_y = 100
    vpc_x = outer_x + left_column_width + 70
    vpc_y = 200
    public_y = vpc_y + 170
    private_y = public_y + outer_height_by_tier["public"] + 28
    database_y = private_y + outer_height_by_tier["private"] + 28
    inner_left_gutter = 140 if edge_resources else 28
    vpc_width = inner_left_gutter + az_count * az_box_width + max(0, az_count - 1) * az_gap + 52
    vpc_height = database_y - vpc_y + outer_height_by_tier["database"] + 70
    vpc = Rect(vpc_x, vpc_y, vpc_width, vpc_height)

    az_boxes: dict[str, Rect] = {}
    subnet_layouts: dict[str, SubnetLayout] = {}
    node_layouts: dict[str, NodeLayout] = {}
    actual_resource_ids = {resource.id for resource in model.resources}

    az_x_lookup: dict[str, int] = {}
    for index, az in enumerate(model.azs):
        az_x = vpc.x + inner_left_gutter + index * (az_box_width + az_gap)
        az_x_lookup[az] = az_x
        az_boxes[az] = Rect(
            az_x - 12,
            public_y - 22,
            az_box_width,
            database_y + outer_height_by_tier["database"] - public_y + 46,
        )

    if az_count == 1:
        corridor_left = vpc.center_x - 140
        corridor_right = vpc.center_x + 140
    else:
        ordered_boxes = [az_boxes[az] for az in model.azs]
        corridor_left = ordered_boxes[0].right + 12
        corridor_right = ordered_boxes[-1].x - 12
    corridor = Rect(
        corridor_left,
        public_y,
        max(220, corridor_right - corridor_left),
        database_y + outer_height_by_tier["database"] - public_y,
    )
    public_band = Rect(corridor.x, public_y, corridor.width, outer_height_by_tier["public"])
    service_band = Rect(corridor.x, public_y + max(130, outer_height_by_tier["public"] // 2 - 10), corridor.width, 170)

    def add_node(resource: Resource, box: Rect, icon: Rect, style: str, text_x: int, text_y: int, text_anchor: str = "start") -> None:
        node_layouts[resource.id] = NodeLayout(
            id=resource.id,
            kind=resource.kind,
            label=resource.label,
            details=resource.details,
            box=box,
            icon=icon,
            style=style,
            text_x=text_x,
            text_y=text_y,
            text_anchor=text_anchor,
            resource=resource,
        )

    for az in model.azs:
        az_x = az_x_lookup[az]
        for tier, y in (("public", public_y), ("private", private_y), ("database", database_y)):
            tier_subnets = _subnets_for_tier_az(model.subnets, tier, az)
            if not tier_subnets:
                continue
            subnet_y = y
            for subnet in tier_subnets:
                subnet_height = (
                    outer_height_by_tier[tier]
                    if len(tier_subnets) == 1
                    else _subnet_content_height(resources_by_subnet.get(subnet.id, []), tier)
                )
                box = Rect(az_x, subnet_y, subnet_width, subnet_height)
                subnet_layouts[subnet.id] = SubnetLayout(
                    subnet=subnet,
                    box=box,
                    header_color=HEADER_COLOR[tier],
                    title_x=box.x + 34,
                    title_y=box.y + 18,
                    cidr_x=box.center_x,
                    cidr_y=box.bottom - 12,
                )
                subnet_y += subnet_height + 18

    for subnet in model.subnets:
        layout = subnet_layouts[subnet.id]
        grouped, ungrouped = _display_items(resources_by_subnet.get(subnet.id, []))
        content_y = layout.box.y + 40
        if layout.subnet.tier == "public":
            public_resources = list(ungrouped)
            for group_id, members in grouped.items():
                group = group_lookup.get(group_id)
                if group and group.member_ids:
                    member_rank = {member_id: index for index, member_id in enumerate(group.member_ids)}
                    members = sorted(members, key=lambda member: member_rank.get(member.id, len(member_rank)))
                public_resources.extend(members)
            for resource in public_resources:
                row_box = Rect(layout.box.x + 28, content_y, min(220, layout.box.width - 56), 56)
                icon = Rect(row_box.x + 8, row_box.y + 8, 40, 40)
                add_node(resource, row_box, icon, "card", row_box.x + 58, row_box.y + 18)
                layout.ungrouped_ids.append(resource.id)
                content_y += 68
            continue

        for group_id, members in grouped.items():
            group_box = Rect(layout.box.x + 16, content_y, layout.box.width - 32, _group_height(len(members)))
            group = group_lookup.get(group_id, Group(group_id, group_id))
            if group.member_ids:
                member_rank = {member_id: index for index, member_id in enumerate(group.member_ids)}
                members = sorted(members, key=lambda member: member_rank.get(member.id, len(member_rank)))
            layout.group_layouts.append(GroupLayout(group, group_box, [member.id for member in members]))
            item_y = group_box.y + 14
            for member in members:
                row_box = Rect(group_box.x + 18, item_y, group_box.width - 36, 56)
                icon = Rect(row_box.x + 8, row_box.y + 8, 40, 40)
                add_node(member, row_box, icon, "card", row_box.x + 58, row_box.y + 18)
                item_y += 68
            content_y += group_box.height + 16

        for resource in ungrouped:
            row_box = Rect(layout.box.x + 18, content_y, layout.box.width - 36, 56)
            icon = Rect(row_box.x + 8, row_box.y + 8, 40, 40)
            add_node(resource, row_box, icon, "card", row_box.x + 58, row_box.y + 18)
            layout.ungrouped_ids.append(resource.id)
            content_y += 68

    top_center_x = vpc.center_x
    igw_icon_center_x = top_center_x
    if igw:
        igw_box = Rect(top_center_x - 30, vpc.y + 8, 270, 64)
        igw_icon = Rect(igw_box.x, igw_box.y, 58, 58)
        igw_icon_center_x = igw_icon.center_x
        add_node(igw, igw_box, igw_icon, "side_text_icon", igw_icon.right + 12, igw_box.y + 18)

    for index, waf in enumerate(wafs):
        waf_box = Rect(igw_icon_center_x - 26, vpc.y + 122 + index * 82, 320, 62)
        waf_icon = Rect(waf_box.x, waf_box.y, 52, 52)
        add_node(waf, waf_box, waf_icon, "side_text_icon", waf_icon.right + 26, waf_box.y + 16)

    public_lb_group_box: Rect | None = None
    if lb_band_resources:
        tall_public_labels = any(_prefers_vertical_label(resource.label) for resource in lb_band_resources)
        has_listener_labels = any(resource.listeners for resource in lb_band_resources)
        box_width = 165
        gap = 34
        total_width = len(lb_band_resources) * box_width + max(0, len(lb_band_resources) - 1) * gap
        current_x = corridor.center_x - total_width // 2
        listener_extra = 18 if has_listener_labels else 0
        group_height = (118 if tall_public_labels else 82) + listener_extra
        node_height = (108 if tall_public_labels else 92) + listener_extra
        public_lb_group_box = Rect(current_x - 14, public_y + 34, total_width + 28, group_height)
        for resource in lb_band_resources:
            box = Rect(current_x, public_y + 42, box_width, node_height)
            icon = Rect(box.center_x - 28, box.y + 2, 56, 56)
            add_node(resource, box, icon, "icon_label_below", box.center_x, box.y + 72, "middle")
            current_x += box_width + gap

    if service_resources:
        card_width = 230
        gap = 28
        total_width = len(service_resources) * card_width + max(0, len(service_resources) - 1) * gap
        current_x = corridor.center_x - total_width // 2
        card_y = public_y + max(194, outer_height_by_tier["public"] // 2 + 4)
        for resource in service_resources:
            box = Rect(current_x, card_y, card_width, 128)
            icon = Rect(box.center_x - 28, box.y + 16, 56, 56)
            add_node(resource, box, icon, "service_card", box.center_x, icon.bottom + 20, "middle")
            current_x += card_width + gap

    if edge_resources:
        current_y = public_y + 170
        edge_box_width = max(100, inner_left_gutter - 36)
        for resource in edge_resources:
            box = Rect(vpc.x + 18, current_y, edge_box_width, 104)
            icon = Rect(box.center_x - 30, box.y + 4, 60, 60)
            add_node(resource, box, icon, "icon_label_below", box.center_x, box.y + 76, "middle")
            current_y += 136

    if left_resources:
        current_y = public_y + (170 if edge_resources else 52)
        for resource in left_resources:
            box = Rect(outer_x + 10, current_y, left_column_width - 20, 96)
            icon = Rect(box.center_x - 30, box.y + 4, 60, 60)
            add_node(resource, box, icon, "icon_label_below", box.center_x, box.y + 76, "middle")
            current_y += 132

    if lb_band_resources or igw:
        user_box = Rect(vpc.center_x - 280, outer_y - 62, 54, 54)
        route53_box = Rect(vpc.center_x + 12, outer_y - 66, 58, 58)
        node_layouts["__user"] = NodeLayout(
            id="__user",
            kind="user",
            label="User",
            details=[],
            box=user_box,
            icon=user_box,
            style="user",
            text_x=user_box.center_x,
            text_y=user_box.bottom + 18,
            text_anchor="middle",
        )
        node_layouts["__route53"] = NodeLayout(
            id="__route53",
            kind="route53",
            label="AWS Route 53",
            details=[],
            box=route53_box,
            icon=route53_box,
            style="icon_label_below",
            text_x=route53_box.center_x,
            text_y=route53_box.bottom + 16,
            text_anchor="middle",
        )

    route_table_width = 560 if model.route_tables else 0
    route_table_layouts: list[RouteTableLayout] = []
    route_table_x = vpc.right + 36
    route_table_y = vpc.y + 26
    next_table_y = route_table_y
    for table in model.route_tables:
        box = Rect(route_table_x, next_table_y, route_table_width, _route_table_height(table))
        route_table_layouts.append(RouteTableLayout(table, box))
        next_table_y += box.height + 20

    body_width = vpc.right - outer_x + 100
    if route_table_layouts:
        body_width = route_table_layouts[-1].box.right - outer_x + 60
    outer_bottom = max(vpc.bottom + 18, next_table_y + 20 if route_table_layouts else 0)
    outer = Rect(outer_x, outer_y, body_width, outer_bottom - outer_y)
    canvas_width = outer.right + 70
    canvas_height = outer.bottom + 92 + _security_group_appendix_height(model.security_groups)

    return DiagramLayout(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        outer=outer,
        vpc=vpc,
        corridor=corridor,
        public_band=public_band,
        service_band=service_band,
        public_lb_group_box=public_lb_group_box,
        az_boxes=az_boxes,
        subnet_layouts=subnet_layouts,
        node_layouts=node_layouts,
        route_table_layouts=route_table_layouts,
        actual_resource_ids=actual_resource_ids,
        public_lb_ids=[resource.id for resource in lb_band_resources],
        ingress_lb_ids=[resource.id for resource in ingress_lbs],
        service_ids=[resource.id for resource in service_resources],
        left_ids=[resource.id for resource in left_resources],
        edge_ids=[resource.id for resource in edge_resources],
        title_text=_brand_title(model.vpc_name),
        title_pos=Point(160, 158),
        aws_cloud_icon=Rect(80, 122, 64, 64),
        subtitle_text=f"{model.vpc_name} ({model.vpc_id})",
        subtitle_pos=Point(outer.right - 520, 148),
        footer_vpc_text=f"{model.vpc_name}\n{model.vpc_cidr}",
        footer_vpc_pos=Point(210, outer.bottom + 34),
        footer_region_text=f"AWS Region {model.region}",
        footer_region_pos=Point(outer.right - 100, outer.bottom + 34),
        flow_label_text="HTTPS/SFTP" if "__user" in node_layouts else None,
        flow_label_pos=Point(vpc.center_x - 140, outer_y - 24) if "__user" in node_layouts else None,
        public_lb_caption=_public_lb_caption(lb_band_resources),
        public_lb_caption_pos=Point(public_lb_group_box.center_x, public_lb_group_box.bottom - 10) if public_lb_group_box else None,
    )
