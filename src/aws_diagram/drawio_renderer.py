from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from aws_diagram.layout_engine import DiagramLayout, GroupLayout, NodeLayout, Rect, build_layout
from aws_diagram.models import DiagramModel, SecurityGroupRule, SecurityGroupSummary
from aws_diagram.route_engine import build_routes


DRAWIO_ICON_STYLE = {
    "route53": "sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.route_53;",
    "waf": "sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.waf;",
    "ec2_instance": "sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.ec2;",
    "transit_gateway": "sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.transit_gateway;",
    "internet_gateway": "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.internet_gateway;",
    "nat_gateway": "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.nat_gateway;",
    "alb": "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.application_load_balancer;",
    "nlb": "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.network_load_balancer;",
}

FALLBACK_ICON_STYLE = "ellipse;whiteSpace=wrap;html=1;aspect=fixed;strokeWidth=2;strokeColor=#8b5cf6;fillColor=#f5f3ff;"


def _box_style(stroke: str = "#374151", fill: str = "#ffffff", width: float = 1.8) -> str:
    return f"rounded=1;whiteSpace=wrap;html=1;arcSize=8;strokeWidth={width};strokeColor={stroke};fillColor={fill};"


def _text_style(size: int, bold: bool = False, align: str = "left", color: str = "#374151") -> str:
    style = f"text;html=1;strokeColor=none;fillColor=none;align={align};verticalAlign=middle;fontSize={size};fontColor={color};whiteSpace=wrap;"
    if bold:
        style += "fontStyle=1;"
    return style


def _prefers_vertical_label(node: NodeLayout, label_only: bool) -> bool:
    if not label_only:
        return False
    if len(node.label) >= 22:
        return True
    return len(node.label) >= 18 and node.label.count("-") >= 3


def _stacked_label_value(text: str) -> str:
    parts = [part for part in text.replace("_", "-").split("-") if part]
    if len(parts) <= 1:
        parts = [text[index : index + 10] for index in range(0, len(text), 10)]
    return "<br>".join(parts[:4])


def _edge_style(exit_side: str, entry_side: str) -> str:
    exit_map = {
        "left": ("0", "0.5"),
        "right": ("1", "0.5"),
        "top": ("0.5", "0"),
        "bottom": ("0.5", "1"),
    }
    entry_map = exit_map
    exit_x, exit_y = exit_map[exit_side]
    entry_x, entry_y = entry_map[entry_side]
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
        "endArrow=block;strokeColor=#374151;strokeWidth=2;"
        f"exitX={exit_x};exitY={exit_y};exitDx=0;exitDy=0;exitPerimeter=0;"
        f"entryX={entry_x};entryY={entry_y};entryDx=0;entryDy=0;entryPerimeter=0;"
    )


class _Builder:
    def __init__(self, layout: DiagramLayout) -> None:
        self.mxfile = Element("mxfile", host="app.diagrams.net", agent="Codex", version="24.7.17")
        self.diagram = SubElement(self.mxfile, "diagram", id="aws-diagram-page", name="Reference")
        self.model = SubElement(
            self.diagram,
            "mxGraphModel",
            dx=str(layout.canvas_width),
            dy=str(layout.canvas_height),
            grid="0",
            gridSize="10",
            guides="1",
            tooltips="1",
            connect="1",
            arrows="1",
            fold="1",
            page="0",
            pageScale="1",
            pageWidth=str(layout.canvas_width + 100),
            pageHeight=str(layout.canvas_height + 100),
            math="0",
            shadow="0",
        )
        self.root = SubElement(self.model, "root")
        SubElement(self.root, "mxCell", id="0")
        SubElement(self.root, "mxCell", id="1", parent="0")
        self._next_id = 2

    def _id(self) -> str:
        value = str(self._next_id)
        self._next_id += 1
        return value

    def vertex(self, value: str, style: str, rect: Rect, parent: str = "1") -> str:
        cell_id = self._id()
        cell = SubElement(
            self.root,
            "mxCell",
            id=cell_id,
            parent=parent,
            style=style,
            value=value,
            vertex="1",
        )
        SubElement(
            cell,
            "mxGeometry",
            x=str(rect.x),
            y=str(rect.y),
            width=str(rect.width),
            height=str(rect.height),
            **{"as": "geometry"},
        )
        return cell_id

    def edge(self, source: str, target: str, style: str, points: list[tuple[int, int]] | None = None) -> str:
        cell_id = self._id()
        cell = SubElement(
            self.root,
            "mxCell",
            id=cell_id,
            parent="1",
            source=source,
            target=target,
            style=style,
            edge="1",
        )
        geometry = SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        if points:
            array = SubElement(geometry, "Array", **{"as": "points"})
            for x, y in points:
                SubElement(array, "mxPoint", x=str(x), y=str(y))
        return cell_id

    def render(self) -> str:
        return tostring(self.mxfile, encoding="unicode")


def _icon_style(node: NodeLayout) -> str:
    return DRAWIO_ICON_STYLE.get(node.kind, FALLBACK_ICON_STYLE)


def _icon_cell(builder: _Builder, node: NodeLayout) -> str:
    return builder.vertex("", _icon_style(node), node.icon)


def _add_text_cell(builder: _Builder, value: str, x: int, y: int, width: int, height: int, *, size: int, bold: bool = False, align: str = "left", color: str = "#374151") -> str:
    return builder.vertex(value, _text_style(size, bold=bold, align=align, color=color), Rect(x, y, width, height))


def _draw_frame(builder: _Builder, model: DiagramModel, layout: DiagramLayout) -> None:
    builder.vertex("", _box_style(stroke="#111827", fill="#ffffff", width=2), layout.outer)
    builder.vertex("", "outlineConnect=0;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;shape=mxgraph.aws3.cloud_2;fillColor=#F58534;gradientColor=none;", layout.aws_cloud_icon)
    _add_text_cell(builder, layout.title_text, layout.title_pos.x, layout.title_pos.y - 22, 360, 30, size=30, bold=True, color="#111827")
    _add_text_cell(builder, layout.subtitle_text, layout.subtitle_pos.x, layout.subtitle_pos.y - 28, 360, 44, size=18, bold=True)
    builder.vertex("", _box_style(stroke="#111827", fill="#ffffff", width=2), layout.vpc)
    _add_text_cell(
        builder,
        layout.footer_vpc_text.replace("\n", "<br>"),
        layout.footer_vpc_pos.x - 150,
        layout.footer_vpc_pos.y - 20,
        300,
        40,
        size=18,
        bold=True,
        align="center",
    )
    _add_text_cell(
        builder,
        layout.footer_region_text,
        layout.footer_region_pos.x - 150,
        layout.footer_region_pos.y - 12,
        300,
        24,
        size=18,
        bold=True,
        align="center",
    )
    if layout.flow_label_text and layout.flow_label_pos:
        _add_text_cell(builder, layout.flow_label_text, layout.flow_label_pos.x, layout.flow_label_pos.y - 14, 100, 22, size=12, align="center")
    for az, box in layout.az_boxes.items():
        builder.vertex("", "whiteSpace=wrap;html=1;rounded=1;arcSize=8;dashed=1;dashPattern=10 8;strokeWidth=2;strokeColor=#f59e0b;fillColor=none;", box)
        _add_text_cell(builder, az.upper(), box.center_x - 60, box.bottom - 18, 120, 20, size=15, bold=True, align="center", color="#111827")


def _draw_subnets(builder: _Builder, layout: DiagramLayout) -> None:
    for subnet_layout in layout.subnet_layouts.values():
        box = subnet_layout.box
        builder.vertex("", _box_style(), box)
        builder.vertex("", f"rounded=0;whiteSpace=wrap;html=1;strokeColor=none;fillColor={subnet_layout.header_color};", Rect(box.x, box.y, box.width, 28))
        builder.vertex("", f"rounded=0;whiteSpace=wrap;html=1;strokeColor=none;fillColor={subnet_layout.header_color};", Rect(box.x + 4, box.y + 4, 20, 20))
        _add_text_cell(builder, subnet_layout.subnet.name, subnet_layout.title_x, subnet_layout.title_y - 12, box.width - 60, 20, size=15, bold=True, color="#111827")
        _add_text_cell(builder, subnet_layout.subnet.cidr, subnet_layout.cidr_x - 70, subnet_layout.cidr_y - 12, 140, 20, size=12, align="center")


def _draw_groups(builder: _Builder, layout: DiagramLayout) -> None:
    if layout.public_lb_group_box:
        builder.vertex("", _box_style(stroke="#374151", fill="#ffffff", width=1.6), layout.public_lb_group_box)
        if layout.public_lb_caption and layout.public_lb_caption_pos:
            _add_text_cell(
                builder,
                layout.public_lb_caption,
                layout.public_lb_caption_pos.x - 120,
                layout.public_lb_caption_pos.y - 10,
                240,
                18,
                size=12,
                align="center",
            )
    for subnet_layout in layout.subnet_layouts.values():
        for group in subnet_layout.group_layouts:
            builder.vertex("", "whiteSpace=wrap;html=1;rounded=1;arcSize=8;dashed=1;dashPattern=10 7;strokeWidth=2;strokeColor=#dc2626;fillColor=none;", group.box)
            _add_text_cell(builder, group.group.label, group.box.center_x - 110, group.box.bottom - 24, 220, 18, size=11, align="center", color="#4b5563")


def _draw_node(builder: _Builder, node: NodeLayout, public_lb_ids: set[str]) -> str:
    if node.style == "user":
        anchor = builder.vertex("", _box_style(stroke="#374151", fill="#ffffff", width=1.8), node.box)
        builder.vertex("", "rounded=1;whiteSpace=wrap;html=1;arcSize=6;strokeWidth=2;strokeColor=#374151;fillColor=none;", Rect(node.box.x + 10, node.box.y + 8, node.box.width - 20, 22))
        builder.vertex("", "ellipse;whiteSpace=wrap;html=1;aspect=fixed;strokeWidth=2;strokeColor=#374151;fillColor=none;", Rect(node.box.x + node.box.width // 2 - 7, node.box.y + 39, 14, 14))
        builder.vertex("", "shape=line;strokeWidth=2;strokeColor=#374151;verticalLabelPosition=bottom;verticalAlign=top;", Rect(node.box.x + node.box.width // 2 - 10, node.box.y + 33, 20, 1))
        builder.vertex("", "shape=line;strokeWidth=2;strokeColor=#374151;verticalLabelPosition=bottom;verticalAlign=top;", Rect(node.box.x + node.box.width // 2 - 1, node.box.y + 33, 1, 6))
        builder.vertex("", "shape=line;strokeWidth=2;strokeColor=#374151;verticalLabelPosition=bottom;verticalAlign=top;", Rect(node.box.x + node.box.width // 2 - 14, node.box.y + 61, 28, 1))
        _add_text_cell(builder, node.label, node.text_x - 40, node.text_y - 10, 80, 18, size=12, align="center")
        return anchor

    if node.style == "card":
        anchor = builder.vertex("", _box_style(stroke="#cbd5e1", fill="#ffffff", width=1.4), node.box)
        _icon_cell(builder, node)
        _add_text_cell(builder, node.label, node.text_x, node.text_y - 10, node.box.width - 66, 18, size=12)
        if node.details:
            _add_text_cell(builder, node.details[0], node.text_x, node.text_y + 6, node.box.width - 66, 18, size=11, color="#4b5563")
        if len(node.details) > 1:
            _add_text_cell(builder, node.details[1], node.text_x, node.text_y + 20, node.box.width - 66, 18, size=11, color="#4b5563")
        return anchor

    if node.style == "service_card":
        anchor = builder.vertex("", _box_style(stroke="#111827", fill="#ffffff", width=1.6), node.box)
        _icon_cell(builder, node)
        _add_text_cell(builder, node.label, node.box.x + 20, node.icon.bottom + 10, node.box.width - 40, 20, size=15, bold=True, align="center", color="#111827")
        if node.details:
            _add_text_cell(builder, node.details[0], node.box.x + 30, node.icon.bottom + 28, node.box.width - 60, 18, size=11, align="center", color="#4b5563")
        caption = {
            "nlb": "Network Load Balancers",
            "alb": "Application Load Balancers",
            "privatelink": "PrivateLink Endpoints",
        }.get(node.kind)
        if caption:
            _add_text_cell(builder, caption, node.box.x + 20, node.box.bottom - 22, node.box.width - 40, 18, size=12, align="center")
        return anchor

    icon_id = _icon_cell(builder, node)
    if node.style == "side_text_icon":
        _add_text_cell(builder, node.label, node.text_x, node.text_y - 10, 220, 18, size=15, bold=True, color="#111827")
        if node.details:
            _add_text_cell(builder, node.details[0], node.text_x, node.text_y + 8, 220, 18, size=11, color="#4b5563")
        if len(node.details) > 1:
            _add_text_cell(builder, node.details[1], node.text_x, node.text_y + 22, 220, 18, size=11, color="#4b5563")
    else:
        vertical_label = _prefers_vertical_label(node, node.id in public_lb_ids)
        label_value = _stacked_label_value(node.label) if vertical_label else node.label
        _add_text_cell(
            builder,
            label_value,
            node.box.x,
            node.icon.bottom + 2 if vertical_label else node.text_y - 10,
            node.box.width,
            54 if vertical_label else 18,
            size=12,
            bold=node.id in public_lb_ids,
            align="center" if node.text_anchor == "middle" else "left",
            color="#111827" if node.id in public_lb_ids else "#374151",
        )
        if node.details and node.id not in public_lb_ids:
            _add_text_cell(
                builder,
                node.details[0],
                node.box.x,
                node.text_y + 8,
                node.box.width,
                18,
                size=11,
                align="center" if node.text_anchor == "middle" else "left",
                color="#4b5563",
            )
        if node.details and len(node.details) > 1 and node.id not in public_lb_ids:
            _add_text_cell(
                builder,
                node.details[1],
                node.box.x,
                node.text_y + 22,
                node.box.width,
                18,
                size=11,
                align="center" if node.text_anchor == "middle" else "left",
                color="#4b5563",
            )
    return icon_id


def _draw_nodes(builder: _Builder, layout: DiagramLayout) -> dict[str, str]:
    public_lb_ids = set(layout.public_lb_ids)
    anchor_cells: dict[str, str] = {}
    for node in sorted(layout.node_layouts.values(), key=lambda item: (item.box.y, item.box.x)):
        anchor_cells[node.id] = _draw_node(builder, node, public_lb_ids)
    return anchor_cells


def _draw_route_tables(builder: _Builder, layout: DiagramLayout) -> None:
    for table_layout in layout.route_table_layouts:
        box = table_layout.box
        table = table_layout.table
        builder.vertex("", _box_style(stroke="#111827", fill="#ffffff", width=1.4), box)
        builder.vertex("", "rounded=0;whiteSpace=wrap;html=1;strokeColor=#d1d5db;fillColor=#f3f4f6;", Rect(box.x, box.y, box.width, 28))
        _add_text_cell(builder, table.label, box.x + 12, box.y + 6, box.width - 24, 18, size=15, bold=True, color="#111827")
        _add_text_cell(builder, table.scope, box.x + 12, box.y + 34, box.width - 24, 18, size=12)
        header_y = box.y + 78
        destination_x = box.x + 12
        target_x = box.x + 175
        note_x = box.x + 360
        _add_text_cell(builder, "Destination", destination_x, header_y, 150, 18, size=12)
        _add_text_cell(builder, "Target", target_x, header_y, 165, 18, size=12)
        _add_text_cell(builder, "Note", note_x, header_y, 70, 18, size=12)
        row_y = header_y + 18
        for row in table.rows[:18]:
            _add_text_cell(builder, row.destination, destination_x, row_y, 170, 18, size=11, color="#4b5563")
            _add_text_cell(builder, row.target, target_x, row_y, 165, 22, size=11, color="#4b5563")
            _add_text_cell(builder, row.note, note_x, row_y, 70, 18, size=11, color="#4b5563")
            row_y += 24


def _source_lines(sources: list[str], width: int = 72) -> list[str]:
    lines: list[str] = []
    current = ""
    for source in sources:
        candidate = source if not current else f"{current}, {source}"
        if current and len(candidate) > width:
            lines.append(current)
            current = source
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _rule_height(rule: SecurityGroupRule) -> int:
    return max(22, len(_source_lines(rule.sources)) * 14 + 8)


def _security_group_card_height(group: SecurityGroupSummary) -> int:
    return max(128, 78 + sum(_rule_height(rule) for rule in group.inbound + group.outbound))


def _draw_sg_rule(builder: _Builder, box: Rect, y: int, rule: SecurityGroupRule) -> None:
    fill = "#ecfdf5" if rule.direction == "inbound" else "#eff6ff"
    source_lines = _source_lines(rule.sources)
    height = _rule_height(rule)
    builder.vertex("", f"rounded=1;arcSize=3;whiteSpace=wrap;html=1;strokeColor=none;fillColor={fill};", Rect(box.x + 10, y - 13, box.width - 20, height - 4))
    _add_text_cell(builder, "IN" if rule.direction == "inbound" else "OUT", box.x + 16, y - 13, 36, 18, size=11, color="#4b5563")
    _add_text_cell(builder, rule.protocol, box.x + 58, y - 13, 42, 18, size=11, color="#4b5563")
    _add_text_cell(builder, rule.ports, box.x + 105, y - 13, 58, 18, size=11, color="#4b5563")
    _add_text_cell(builder, "<br>".join(source_lines), box.x + 172, y - 13, box.width - 190, height - 4, size=11, color="#4b5563")


def _draw_security_groups(builder: _Builder, model: DiagramModel, layout: DiagramLayout) -> None:
    if not model.security_groups:
        return

    start_y = layout.outer.bottom + 92
    card_width = max(420, (layout.canvas_width - 140 - 28) // 2)
    left_x = 70
    right_x = left_x + card_width + 28
    column_y = [start_y + 54, start_y + 54]
    _add_text_cell(builder, "Security Groups", left_x, start_y - 24, 300, 30, size=22, bold=True, color="#111827")
    _add_text_cell(
        builder,
        "Rules for security groups attached to resources shown in this diagram",
        left_x,
        start_y + 6,
        600,
        22,
        size=12,
    )
    for index, group in enumerate(model.security_groups):
        column = index % 2
        x = left_x if column == 0 else right_x
        height = _security_group_card_height(group)
        box = Rect(x, column_y[column], card_width, height)
        builder.vertex("", _box_style(stroke="#111827", fill="#ffffff", width=1.3), box)
        builder.vertex("", "rounded=0;whiteSpace=wrap;html=1;strokeColor=#d1d5db;fillColor=#eef2f7;", Rect(box.x, box.y, box.width, 30))
        _add_text_cell(builder, f"{group.name} ({group.id})", box.x + 12, box.y + 5, box.width - 24, 20, size=15, bold=True, color="#111827")
        attached = ", ".join(group.attached_to[:3])
        if len(group.attached_to) > 3:
            attached += f" +{len(group.attached_to) - 3}"
        _add_text_cell(builder, f"Attached: {attached}", box.x + 12, box.y + 36, box.width - 24, 18, size=12)
        _add_text_cell(builder, "Dir", box.x + 16, box.y + 58, 36, 18, size=11)
        _add_text_cell(builder, "Proto", box.x + 58, box.y + 58, 42, 18, size=11)
        _add_text_cell(builder, "Ports", box.x + 105, box.y + 58, 58, 18, size=11)
        _add_text_cell(builder, "Sources / CIDRs", box.x + 172, box.y + 58, box.width - 190, 18, size=11)
        y = box.y + 92
        for rule in group.inbound + group.outbound:
            _draw_sg_rule(builder, box, y, rule)
            y += _rule_height(rule)
        column_y[column] += height + 18


def render_drawio(model: DiagramModel) -> str:
    layout = build_layout(model)
    builder = _Builder(layout)
    _draw_frame(builder, model, layout)
    _draw_subnets(builder, layout)
    _draw_groups(builder, layout)
    anchor_cells = _draw_nodes(builder, layout)
    _draw_route_tables(builder, layout)
    _draw_security_groups(builder, model, layout)

    for route in build_routes(model, layout):
        source = anchor_cells.get(route.source_id)
        target = anchor_cells.get(route.target_id)
        if not source or not target:
            continue
        builder.edge(
            source,
            target,
            _edge_style(route.exit_side, route.entry_side),
            [(point.x, point.y) for point in route.waypoints],
        )
    return builder.render()


def render_to_file(model: DiagramModel, output_path: Path) -> Path:
    output_path.write_text(render_drawio(model), encoding="utf-8")
    return output_path
