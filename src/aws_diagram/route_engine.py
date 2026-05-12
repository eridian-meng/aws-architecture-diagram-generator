from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from aws_diagram.layout_engine import DiagramLayout, NodeLayout, Point, Rect
from aws_diagram.models import DiagramModel, Edge, Resource


@dataclass
class Route:
    source_id: str
    target_id: str
    exit_side: str
    entry_side: str
    waypoints: list[Point] = field(default_factory=list)


def _anchor(node: NodeLayout, side: str) -> Point:
    anchor_rect = node.icon if node.style in {"icon_label_below", "side_text_icon"} else node.box
    if side == "left":
        return Point(anchor_rect.x, anchor_rect.center_y)
    if side == "right":
        return Point(anchor_rect.right, anchor_rect.center_y)
    if side == "top":
        return Point(anchor_rect.center_x, anchor_rect.y)
    return Point(anchor_rect.center_x, anchor_rect.bottom)


def _is_left_target(node: NodeLayout, layout: DiagramLayout) -> bool:
    return node.box.center_x < layout.corridor.center_x


def _route_external_flow(layout: DiagramLayout) -> list[Route]:
    routes: list[Route] = []
    if "__user" in layout.node_layouts and "__route53" in layout.node_layouts:
        routes.append(Route("__user", "__route53", "right", "left"))
    if "__route53" in layout.node_layouts and "igw" in layout.node_layouts:
        routes.append(Route("__route53", "igw", "bottom", "top"))
    return routes


def _lb_source_order(source: NodeLayout, layout: DiagramLayout) -> int:
    if source.id in layout.public_lb_ids:
        return layout.public_lb_ids.index(source.id)
    if source.id in layout.service_ids:
        return len(layout.public_lb_ids) + layout.service_ids.index(source.id)
    return 0


def _lb_target_route(source: NodeLayout, target: NodeLayout, layout: DiagramLayout, route_index: int) -> Route:
    resource = target.resource
    entry_side = "right" if _is_left_target(target, layout) else "left"
    if not resource or not resource.subnet_id or resource.subnet_id not in layout.subnet_layouts:
        return Route(
            source.id,
            target.id,
            "bottom",
            entry_side,
            [Point(source.box.center_x, target.box.center_y)],
        )

    subnet_box = layout.subnet_layouts[resource.subnet_id].box
    source_order = _lb_source_order(source, layout)
    lane_offset = 18 + source_order * 16 + route_index * 8
    lane_x = subnet_box.right + lane_offset if entry_side == "right" else subnet_box.x - lane_offset
    branch_base = max(source.icon.bottom + 28, layout.public_lb_group_box.bottom + 22 if layout.public_lb_group_box else source.icon.bottom + 28)
    branch_y = branch_base + source_order * 28
    return Route(
        source.id,
        target.id,
        "bottom",
        entry_side,
        [
            Point(source.box.center_x, branch_y),
            Point(lane_x, branch_y),
            Point(lane_x, target.box.center_y),
        ],
    )


def _left_to_internal_route(source: NodeLayout, target: NodeLayout, layout: DiagramLayout) -> Route:
    lane_x = layout.vpc.x + 18
    entry_side = "right" if _is_left_target(target, layout) else "left"
    return Route(
        source.id,
        target.id,
        "right",
        entry_side,
        [
            Point(lane_x, source.box.center_y),
            Point(lane_x, target.box.center_y),
        ],
    )


def _edge_to_internal_route(source: NodeLayout, target: NodeLayout, layout: DiagramLayout) -> Route:
    entry_side = "right" if _is_left_target(target, layout) else "left"
    lane_x = source.box.right + 18
    return Route(
        source.id,
        target.id,
        "right",
        entry_side,
        [
            Point(lane_x, source.box.center_y),
            Point(lane_x, target.box.center_y),
        ],
    )


def _vertical_branch_route(source: NodeLayout, target: NodeLayout, branch_y: int) -> Route:
    return Route(
        source.id,
        target.id,
        "bottom",
        "top",
        [
            Point(source.icon.center_x, branch_y),
            Point(target.icon.center_x, branch_y),
        ],
    )


def _igw_direct_route(source: NodeLayout, target: NodeLayout, layout: DiagramLayout, route_index: int) -> Route:
    exit_side = "left" if target.icon.center_x < source.icon.center_x else "right"
    exit_x = source.icon.x if exit_side == "left" else source.icon.right
    branch_y = (layout.public_lb_group_box.y - 20 if layout.public_lb_group_box else layout.public_band.y - 20) - route_index * 10
    return Route(
        source.id,
        target.id,
        exit_side,
        "top",
        [
            Point(exit_x, branch_y),
            Point(target.icon.center_x, branch_y),
        ],
    )


def _waf_target_route(source: NodeLayout, target: NodeLayout, branch_y: int) -> Route:
    return Route(
        source.id,
        target.id,
        "bottom",
        "top",
        [
            Point(source.icon.center_x, branch_y),
            Point(target.icon.center_x, branch_y),
        ],
    )


def _same_lane_route(source: NodeLayout, target: NodeLayout) -> Route:
    exit_side = "right" if source.box.center_x <= target.box.center_x else "left"
    entry_side = "left" if source.box.center_x <= target.box.center_x else "right"
    return Route(source.id, target.id, exit_side, entry_side)


def _subnet_to_database_route(source: NodeLayout, target: NodeLayout) -> Route:
    return Route(source.id, target.id, "bottom", "top", [Point(source.box.center_x, target.box.y - 12)])


def _service_target_route(source: NodeLayout, target: NodeLayout, layout: DiagramLayout, route_index: int) -> Route:
    resource = target.resource
    entry_side = "right" if _is_left_target(target, layout) else "left"
    exit_side = "left" if entry_side == "right" else "right"
    if not resource or not resource.subnet_id or resource.subnet_id not in layout.subnet_layouts:
        return Route(source.id, target.id, exit_side, entry_side)

    subnet_box = layout.subnet_layouts[resource.subnet_id].box
    source_order = _lb_source_order(source, layout)
    lane_offset = 18 + source_order * 16 + route_index * 8
    lane_x = subnet_box.right + lane_offset if entry_side == "right" else subnet_box.x - lane_offset
    lane_y = source.box.bottom + 18 + source_order * 24
    return Route(
        source.id,
        target.id,
        exit_side,
        entry_side,
        [
            Point(lane_x, lane_y),
            Point(lane_x, target.box.center_y),
        ],
    )


def build_routes(model: DiagramModel, layout: DiagramLayout) -> list[Route]:
    routes = _route_external_flow(layout)
    nodes = layout.node_layouts
    resources = {resource.id: resource for resource in model.resources}
    outgoing: dict[str, int] = defaultdict(int)

    for edge in model.edges:
        source = nodes.get(edge.source)
        target = nodes.get(edge.target)
        if not source or not target:
            continue

        source_resource = resources.get(edge.source)
        target_resource = resources.get(edge.target)
        route_index = outgoing[edge.source]
        outgoing[edge.source] += 1

        if source.id == "igw" and target.kind == "waf":
            routes.append(Route(source.id, target.id, "bottom", "top"))
            continue

        if source.kind == "waf" and target.id in layout.ingress_lb_ids:
            branch_y = source.icon.bottom + 22
            routes.append(_waf_target_route(source, target, branch_y))
            continue

        if source.id == "igw" and target.id in layout.ingress_lb_ids:
            routes.append(_igw_direct_route(source, target, layout, route_index))
            continue

        if source.id == "igw" and target_resource and target_resource.subnet_id:
            routes.append(_igw_direct_route(source, target, layout, route_index))
            continue

        if source_resource and source_resource.placement == "left" and target_resource and target_resource.placement == "left":
            routes.append(_same_lane_route(source, target))
            continue

        if source_resource and source_resource.placement == "left" and target_resource and target_resource.placement == "edge":
            routes.append(_same_lane_route(source, target))
            continue

        if source_resource and source_resource.placement == "left":
            routes.append(_left_to_internal_route(source, target, layout))
            continue

        if source_resource and source_resource.placement == "edge":
            routes.append(_edge_to_internal_route(source, target, layout))
            continue

        if source.id in layout.public_lb_ids and target_resource and target_resource.subnet_id:
            routes.append(_lb_target_route(source, target, layout, route_index))
            continue

        if source.id in layout.service_ids and target_resource and target_resource.subnet_id:
            routes.append(_service_target_route(source, target, layout, route_index))
            continue

        if (
            source_resource
            and target_resource
            and source_resource.subnet_id
            and target_resource.subnet_id
            and source_resource.az == target_resource.az
        ):
            routes.append(_subnet_to_database_route(source, target))
            continue

        if source.box.center_y == target.box.center_y:
            routes.append(_same_lane_route(source, target))
            continue

        branch_y = min(source.box.bottom + 18, target.box.y - 16)
        routes.append(
            Route(
                source.id,
                target.id,
                "bottom",
                "top",
                [Point(source.box.center_x, branch_y), Point(target.box.center_x, branch_y)],
            )
        )

    return routes


def route_points(route: Route, layout: DiagramLayout) -> list[Point]:
    source = layout.node_layouts[route.source_id]
    target = layout.node_layouts[route.target_id]
    return [_anchor(source, route.exit_side), *route.waypoints, _anchor(target, route.entry_side)]
