from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Subnet:
    id: str
    name: str
    cidr: str
    az: str
    tier: str
    route_table_id: str | None = None


@dataclass
class Resource:
    id: str
    kind: str
    label: str
    details: list[str] = field(default_factory=list)
    az: str | None = None
    subnet_id: str | None = None
    group: str | None = None
    placement: str = "subnet"
    public: bool = False
    internal: bool = False
    security_group_ids: list[str] = field(default_factory=list)
    state: str | None = None
    listeners: list[str] = field(default_factory=list)


@dataclass
class Group:
    id: str
    label: str
    member_ids: list[str] = field(default_factory=list)
    kind: str = "group"


@dataclass
class Edge:
    source: str
    target: str
    label: str | None = None


@dataclass
class RouteRow:
    destination: str
    target: str
    note: str = ""


@dataclass
class RouteTable:
    id: str
    label: str
    scope: str
    associations: list[str] = field(default_factory=list)
    rows: list[RouteRow] = field(default_factory=list)


@dataclass
class SecurityGroupRule:
    direction: str
    protocol: str
    ports: str
    sources: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SecurityGroupSummary:
    id: str
    name: str
    description: str
    attached_to: list[str] = field(default_factory=list)
    inbound: list[SecurityGroupRule] = field(default_factory=list)
    outbound: list[SecurityGroupRule] = field(default_factory=list)


@dataclass
class DiagramModel:
    title: str
    region: str
    vpc_id: str
    vpc_name: str
    vpc_cidr: str
    azs: list[str]
    subnets: list[Subnet]
    resources: list[Resource]
    groups: list[Group]
    edges: list[Edge]
    route_tables: list[RouteTable] = field(default_factory=list)
    security_groups: list[SecurityGroupSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
