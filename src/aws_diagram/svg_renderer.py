from __future__ import annotations

from html import escape
from pathlib import Path

from aws_diagram.icon_catalog import icon_data_uri
from aws_diagram.layout_engine import DiagramLayout, GroupLayout, NodeLayout, Point, Rect, RouteTableLayout, build_layout
from aws_diagram.models import DiagramModel
from aws_diagram.route_engine import build_routes, route_points


ICON_BY_KIND = {
    "route53": "route53",
    "internet_gateway": "internet_gateway",
    "nat_gateway": "nat_gateway",
    "alb": "alb",
    "nlb": "nlb",
    "ec2_instance": "ec2_instance",
    "rds": "rds",
    "waf": "waf",
    "transit_gateway": "transit_gateway",
    "tgw_peering": "tgw_peering",
    "site_to_site_vpn": "site_to_site_vpn",
    "vpn_connection": "vpn_connection",
    "vpc_peering": "vpc_peering",
    "privatelink": "privatelink",
}


def _header(layout: DiagramLayout) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{layout.canvas_width}" height="{layout.canvas_height}" viewBox="0 0 {layout.canvas_width} {layout.canvas_height}">',
        "  <defs>",
        "    <style>",
        "      .title { font: 700 28px Arial, sans-serif; fill: #111827; }",
        "      .subtitle { font: 700 18px Arial, sans-serif; fill: #374151; }",
        "      .footer { font: 700 18px Arial, sans-serif; fill: #374151; }",
        "      .label { font: 700 15px Arial, sans-serif; fill: #111827; }",
        "      .lb-label { font: 700 12px Arial, sans-serif; fill: #111827; }",
        "      .small { font: 500 12px Arial, sans-serif; fill: #374151; }",
        "      .tiny { font: 500 11px Arial, sans-serif; fill: #4b5563; }",
        "      .outer { fill: #ffffff; stroke: #111827; stroke-width: 2; }",
        "      .vpc { fill: #ffffff; stroke: #111827; stroke-width: 2; }",
        "      .az { fill: none; stroke: #f59e0b; stroke-width: 2; stroke-dasharray: 10 8; }",
        "      .subnet { fill: #ffffff; stroke: #374151; stroke-width: 1.8; }",
        "      .header-strip { stroke: none; }",
        "      .group { fill: none; stroke: #dc2626; stroke-width: 2; stroke-dasharray: 10 7; }",
        "      .public-group { fill: #ffffff; stroke: #374151; stroke-width: 1.6; }",
        "      .card { fill: #ffffff; stroke: #cbd5e1; stroke-width: 1.4; }",
        "      .service-card { fill: #ffffff; stroke: #111827; stroke-width: 1.6; }",
        "      .table { fill: #ffffff; stroke: #111827; stroke-width: 1.4; }",
        "      .table-head { fill: #f3f4f6; stroke: #d1d5db; stroke-width: 1; }",
        "      .flow { fill: none; stroke: #374151; stroke-width: 2.1; stroke-linecap: round; stroke-linejoin: round; }",
        "      .user-box { fill: #ffffff; stroke: #374151; stroke-width: 1.8; }",
        "      .lock-fill { fill: none; stroke: #ffffff; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }",
        "      .user-stroke { fill: none; stroke: #374151; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }",
        "    </style>",
        '    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">',
        '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#374151"/>',
        "    </marker>",
        "  </defs>",
        f'  <rect x="0" y="0" width="{layout.canvas_width}" height="{layout.canvas_height}" fill="#ffffff"/>',
    ]


def _text(x: int, y: int, content: str, klass: str, anchor: str = "start") -> str:
    return f'  <text x="{x}" y="{y}" text-anchor="{anchor}" class="{klass}">{escape(content)}</text>'


def _multiline_text(x: int, y: int, lines: list[str], klass: str, anchor: str = "start", line_height: int = 18) -> list[str]:
    output = [f'  <text x="{x}" y="{y}" text-anchor="{anchor}" class="{klass}">']
    for index, line in enumerate(lines):
        dy = "0" if index == 0 else str(line_height)
        output.append(f'    <tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    output.append("  </text>")
    return output


def _image(name: str, x: int, y: int, width: int, height: int) -> str:
    return f'  <image href="{icon_data_uri(name)}" x="{x}" y="{y}" width="{width}" height="{height}"/>'


def _rect(rect: Rect, klass: str, rx: int = 16, ry: int = 16, extra: str = "") -> str:
    suffix = f" {extra}" if extra else ""
    return f'  <rect x="{rect.x}" y="{rect.y}" width="{rect.width}" height="{rect.height}" rx="{rx}" ry="{ry}" class="{klass}"{suffix}/>'


def _path(points: list[Point]) -> str:
    if not points:
        return ""
    return " ".join(
        [f"M{points[0].x} {points[0].y}"] + [f"L{point.x} {point.y}" for point in points[1:]]
    )


def _split_line(text: str, width: int = 26) -> list[str]:
    words = text.split()
    if len(text) <= width:
        return [text]
    if len(words) <= 1:
        return [text[index : index + width] for index in range(0, min(len(text), width * 2), width)]
    lines = []
    current = []
    length = 0
    for word in words:
        if length + len(word) + len(current) > width and current:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += len(word)
    if current:
        lines.append(" ".join(current))
    return lines[:2]


def _prefers_vertical_label(node: NodeLayout, label_only: bool) -> bool:
    if not label_only:
        return False
    if len(node.label) >= 22:
        return True
    return len(node.label) >= 18 and node.label.count("-") >= 3


def _stacked_label_lines(text: str) -> list[str]:
    parts = [part for part in text.replace("_", "-").split("-") if part]
    if len(parts) <= 1:
        return _split_line(text, 10)
    lines: list[str] = []
    for part in parts:
        if len(part) <= 11:
            lines.append(part)
        else:
            lines.extend(_split_line(part, 11))
    return lines[:4]


def _draw_lock(x: int, y: int) -> list[str]:
    return [
        f'  <path d="M{x + 5} {y + 12}v-4a5 5 0 0 1 10 0v4" class="lock-fill"/>',
        f'  <rect x="{x + 3}" y="{y + 12}" width="14" height="12" rx="2" ry="2" class="lock-fill"/>',
    ]


def _draw_user(node: NodeLayout) -> list[str]:
    x, y, w, h = node.box.x, node.box.y, node.box.width, node.box.height
    center_x = x + w // 2
    return [
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" ry="6" class="user-box"/>',
        f'  <rect x="{x + 10}" y="{y + 8}" width="{w - 20}" height="22" rx="3" ry="3" class="user-stroke"/>',
        f'  <path d="M{center_x - 10} {y + 34}h20" class="user-stroke"/>',
        f'  <path d="M{center_x - 5} {y + 34}v6" class="user-stroke"/>',
        f'  <circle cx="{center_x}" cy="{y + 46}" r="7" class="user-stroke"/>',
        f'  <path d="M{center_x - 14} {y + 63}c3-7 9-10 14-10s11 3 14 10" class="user-stroke"/>',
        _text(node.text_x, node.text_y, node.label, "small", node.text_anchor),
    ]


def _draw_card(node: NodeLayout) -> list[str]:
    lines = [_rect(node.box, "card", 6, 6), _image(ICON_BY_KIND.get(node.kind, "ec2_instance"), node.icon.x, node.icon.y, node.icon.width, node.icon.height)]
    label_lines = _split_line(node.label, 28)
    text_y = node.text_y
    for line in label_lines:
        lines.append(_text(node.text_x, text_y, line, "small"))
        text_y += 14
    for detail in node.details[:2]:
        for wrapped in _split_line(detail, 24):
            lines.append(_text(node.text_x, text_y, wrapped, "tiny"))
            text_y += 13
    return lines


def _draw_service_card(node: NodeLayout) -> list[str]:
    lines = [_rect(node.box, "service-card", 18, 18), _image(ICON_BY_KIND.get(node.kind, "nlb"), node.icon.x, node.icon.y, node.icon.width, node.icon.height)]
    label_lines = _split_line(node.label, 24)
    text_y = node.text_y
    for line in label_lines:
        lines.append(_text(node.text_x, text_y, line, "label", "middle"))
        text_y += 16
    if node.details:
        for wrapped in _split_line(node.details[0], 22):
            lines.append(_text(node.text_x, text_y, wrapped, "tiny", "middle"))
            text_y += 13
    kind_caption = {
        "nlb": "Network Load Balancers",
        "alb": "Application Load Balancers",
        "privatelink": "PrivateLink Endpoints",
    }.get(node.kind)
    if kind_caption:
        lines.append(_text(node.text_x, node.box.bottom - 12, kind_caption, "small", "middle"))
    return lines


def _draw_icon_label(node: NodeLayout, label_only: bool = False) -> list[str]:
    lines = []
    if node.kind == "route53":
        lines.append(_image("route53", node.icon.x, node.icon.y, node.icon.width, node.icon.height))
    else:
        lines.append(_image(ICON_BY_KIND.get(node.kind, "ec2_instance"), node.icon.x, node.icon.y, node.icon.width, node.icon.height))
    vertical_label = _prefers_vertical_label(node, label_only)
    label_lines = _stacked_label_lines(node.label) if vertical_label else _split_line(node.label, 24)
    text_y = node.icon.bottom + 10 if vertical_label else node.text_y
    label_class = "lb-label" if label_only else "small"
    for line in label_lines:
        lines.append(_text(node.text_x, text_y, line, label_class, node.text_anchor))
        text_y += 12 if vertical_label else 15
    if not label_only:
        for detail in node.details[:2]:
            for wrapped in _split_line(detail, 22):
                lines.append(_text(node.text_x, text_y, wrapped, "tiny", node.text_anchor))
                text_y += 13
    return lines


def _draw_side_text_icon(node: NodeLayout) -> list[str]:
    lines = [_image(ICON_BY_KIND.get(node.kind, "internet_gateway"), node.icon.x, node.icon.y, node.icon.width, node.icon.height)]
    label_lines = _split_line(node.label, 24)
    text_y = node.text_y
    for line in label_lines:
        lines.append(_text(node.text_x, text_y, line, "label"))
        text_y += 15
    for detail in node.details[:2]:
        lines.append(_text(node.text_x, text_y, detail, "tiny"))
        text_y += 13
    return lines


def _draw_frame(model: DiagramModel, layout: DiagramLayout) -> list[str]:
    lines = [
        _rect(layout.outer, "outer", 18, 18),
        _image("aws_cloud", layout.aws_cloud_icon.x, layout.aws_cloud_icon.y, layout.aws_cloud_icon.width, layout.aws_cloud_icon.height),
        _text(layout.title_pos.x, layout.title_pos.y, layout.title_text, "title"),
    ]
    lines.extend(_multiline_text(layout.subtitle_pos.x, layout.subtitle_pos.y, _split_line(layout.subtitle_text, 34), "subtitle"))
    lines.append(_rect(layout.vpc, "vpc", 18, 18))
    lines.extend(_multiline_text(layout.footer_vpc_pos.x, layout.footer_vpc_pos.y, layout.footer_vpc_text.splitlines(), "footer", "middle"))
    lines.append(_text(layout.footer_region_pos.x, layout.footer_region_pos.y, layout.footer_region_text, "footer", "middle"))
    if layout.flow_label_text and layout.flow_label_pos:
        lines.append(_text(layout.flow_label_pos.x, layout.flow_label_pos.y, layout.flow_label_text, "small"))
    for az, box in layout.az_boxes.items():
        lines.append(_rect(box, "az", 18, 18))
        lines.append(_text(box.center_x, box.bottom - 10, az.upper(), "label", "middle"))
    return lines


def _draw_subnets(layout: DiagramLayout) -> list[str]:
    lines: list[str] = []
    for subnet_layout in layout.subnet_layouts.values():
        box = subnet_layout.box
        header = Rect(box.x, box.y, box.width, 28)
        lines.append(_rect(box, "subnet", 18, 18))
        lines.append(_rect(header, "header-strip", 18, 18, f'style="fill:{subnet_layout.header_color};stroke:none;"'))
        lines.append(f'  <rect x="{box.x + 4}" y="{box.y + 4}" width="20" height="20" fill="{subnet_layout.header_color}" stroke="none"/>')
        lines.extend(_draw_lock(box.x + 5, box.y + 1))
        lines.append(_text(subnet_layout.title_x, subnet_layout.title_y, subnet_layout.subnet.name, "label"))
        lines.append(_text(subnet_layout.cidr_x, subnet_layout.cidr_y, subnet_layout.subnet.cidr, "small", "middle"))
    return lines


def _draw_groups(layout: DiagramLayout) -> list[str]:
    lines: list[str] = []
    if layout.public_lb_group_box:
        lines.append(_rect(layout.public_lb_group_box, "public-group", 12, 12))
        if layout.public_lb_caption and layout.public_lb_caption_pos:
            lines.append(_text(layout.public_lb_caption_pos.x, layout.public_lb_caption_pos.y, layout.public_lb_caption, "small", "middle"))
    for subnet_layout in layout.subnet_layouts.values():
        for group in subnet_layout.group_layouts:
            lines.append(_rect(group.box, "group", 18, 18))
            lines.append(_text(group.box.center_x, group.box.bottom - 10, group.group.label, "tiny", "middle"))
    return lines


def _draw_nodes(layout: DiagramLayout) -> list[str]:
    lines: list[str] = []
    ordered = sorted(layout.node_layouts.values(), key=lambda item: (item.box.y, item.box.x))
    for node in ordered:
        if node.style == "user":
            lines.extend(_draw_user(node))
        elif node.style == "side_text_icon":
            lines.extend(_draw_side_text_icon(node))
        elif node.style == "service_card":
            lines.extend(_draw_service_card(node))
        elif node.style == "card":
            lines.extend(_draw_card(node))
        else:
            lines.extend(_draw_icon_label(node, label_only=node.id in layout.public_lb_ids))
    return lines


def _draw_route_tables(layout: DiagramLayout) -> list[str]:
    lines: list[str] = []
    for table_layout in layout.route_table_layouts:
        box = table_layout.box
        table = table_layout.table
        lines.append(_rect(box, "table", 14, 14))
        lines.append(_rect(Rect(box.x, box.y, box.width, 28), "table-head", 14, 14))
        lines.append(_text(box.x + 12, box.y + 19, table.label, "label"))
        lines.append(_text(box.x + 12, box.y + 46, table.scope, "small"))
        if table.associations:
            assoc = ", ".join(table.associations[:4])
            if len(table.associations) > 4:
                assoc += f" +{len(table.associations) - 4}"
            lines.append(_text(box.x + 12, box.y + 62, f"Assoc: {assoc}", "tiny"))
        header_y = box.y + 84
        lines.append(_text(box.x + 12, header_y, "Destination", "small"))
        lines.append(_text(box.x + 210, header_y, "Target", "small"))
        lines.append(_text(box.x + 350, header_y, "Note", "small"))
        row_y = header_y + 18
        for row in table.rows[:18]:
            lines.append(_text(box.x + 12, row_y, row.destination, "tiny"))
            lines.append(_text(box.x + 210, row_y, row.target, "tiny"))
            lines.append(_text(box.x + 350, row_y, row.note, "tiny"))
            row_y += 24
    return lines


def render_svg(model: DiagramModel) -> str:
    layout = build_layout(model)
    lines = _header(layout)
    lines.extend(_draw_frame(model, layout))
    lines.extend(_draw_subnets(layout))
    lines.extend(_draw_groups(layout))
    for route in build_routes(model, layout):
        lines.append(f'  <path d="{_path(route_points(route, layout))}" class="flow" marker-end="url(#arrow)"/>')
    lines.extend(_draw_nodes(layout))
    lines.extend(_draw_route_tables(layout))
    lines.append("</svg>")
    return "\n".join(lines)


def render_to_file(model: DiagramModel, output_path: Path) -> Path:
    output_path.write_text(render_svg(model), encoding="utf-8")
    return output_path
