"""
Structranet AI — Topology Schema

Pydantic models defining the contract between the AI agent and the
port_assigner / hw_config / config_agent pipeline.

V3.2 changelog:
  - _DYNAMIPS_MAX_PORTS is now DERIVED from hw_config / constants/hardware.py
    (DYNAMIPS_BUILTIN_PORTS + ports_per_module * max_slots) instead of being
    a hardcoded ClassVar. This eliminates the drift between schema.py and
    the hardware constants that caused incorrect validation limits.
  - Added c3600 alias to _DYNAMIPS_MAX_PORTS (GNS3 uses platform="c3600"
    for all c36xx chassis).
  - Updated _DYNAMIPS_ADAPTER0_MAX_ETH_PORT to include c3600 alias.

V3.1 changelog:
  - FIX (Bug 6): no_duplicate_connections now keys on (frozenset({a,b}), link_type)
    instead of frozenset({a,b}) alone.
"""

from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Dict, Any, ClassVar
import logging

_schema_logger = logging.getLogger("structranet.schema")


# ═══════════════════════════════════════════════════════════════════════════════
#  Derived hardware limits (single source of truth)
# ═══════════════════════════════════════════════════════════════════════════════
# Import here to derive limits — done at module level so ClassVar assignments
# below can reference the computed values without circular import issues.

from constants.hardware import (
    DYNAMIPS_BUILTIN_PORTS,
    DYNAMIPS_BUILTIN_DEFAULT,
    DYNAMIPS_SLOT_MODULES,
)


def _compute_dynamips_max_ports() -> Dict[str, int]:
    """Derive max port count per platform from the hardware constants.

    Formula: builtin_ports + (ports_per_module * max_slots)

    This is the theoretical maximum; AI limits in constants/ai.py are more
    conservative (PCI bus, practical topology limits).
    """
    result: Dict[str, int] = {}
    for platform, cfg in DYNAMIPS_SLOT_MODULES.items():
        builtin = DYNAMIPS_BUILTIN_PORTS.get(platform, DYNAMIPS_BUILTIN_DEFAULT)
        expansion = cfg["ports_per_module"] * cfg["max_slots"]
        result[platform] = builtin + expansion
    return result


# Computed once at import time
_DYNAMIPS_MAX_PORTS_COMPUTED: Dict[str, int] = _compute_dynamips_max_ports()


# ═══════════════════════════════════════════════════════════════════════════════
#  Step-1 LLM output models (no port numbers — just nodes + connections)
# ═══════════════════════════════════════════════════════════════════════════════

class Connection(BaseModel):
    """A logical connection request produced by the LLM."""
    from_node: str = Field(..., description="node_id of one endpoint")
    to_node: str = Field(..., description="node_id of the other endpoint")
    link_type: Literal["ethernet", "serial"] = "ethernet"

    @model_validator(mode="after")
    def endpoints_must_differ(self):
        if self.from_node == self.to_node:
            raise ValueError("A connection cannot link a node to itself.")
        return self


class NodeRequest(BaseModel):
    """A device description produced by the LLM in step 1."""
    node_id: str = Field(..., description="Unique logical ID (e.g. 'R1', 'SW1')")
    name: str = Field(..., min_length=1, description="Display name (e.g. 'R1-Edge')")
    node_type: Literal[
        "cloud", "nat", "ethernet_hub", "ethernet_switch",
        "frame_relay_switch", "atm_switch", "docker", "dynamips",
        "vpcs", "traceng", "virtualbox", "vmware", "iou", "qemu",
    ]
    template_name: str = Field(..., description="Exact template name from GNS3 inventory")
    compute_id: str = Field(default="local")


class TopologyRequest(BaseModel):
    """Complete step-1 LLM output: device list + logical connections."""
    name: str = Field(..., min_length=1, description="GNS3 project name")
    nodes: List[NodeRequest] = Field(..., min_length=1)
    connections: List[Connection] = Field(default_factory=list)

    @model_validator(mode="after")
    def node_ids_must_be_unique(self):
        seen: set[str] = set()
        dupes: set[str] = set()
        for n in self.nodes:
            if n.node_id in seen:
                dupes.add(n.node_id)
            seen.add(n.node_id)
        if dupes:
            raise ValueError(f"Duplicate node_ids: {dupes}")
        return self

    @model_validator(mode="after")
    def connections_must_reference_existing_nodes(self):
        valid = {n.node_id for n in self.nodes}
        for c in self.connections:
            for nid in (c.from_node, c.to_node):
                if nid not in valid:
                    raise ValueError(
                        f"Connection references unknown node_id '{nid}'. "
                        f"Valid ids: {sorted(valid)}"
                    )
        return self

    @model_validator(mode="after")
    def no_duplicate_connections(self):
        seen: set[tuple] = set()
        for c in self.connections:
            key = (frozenset([c.from_node, c.to_node]), c.link_type)
            if key in seen:
                raise ValueError(
                    f"Duplicate {c.link_type} connection between "
                    f"'{c.from_node}' and '{c.to_node}'. "
                    f"Each pair may have at most one direct link per link type."
                )
            seen.add(key)
        return self

    @model_validator(mode="after")
    def single_port_nodes_must_not_exceed_one_connection(self):
        SINGLE_PORT = {"vpcs", "traceng", "nat"}
        counts: dict[str, int] = {}
        for c in self.connections:
            for nid in (c.from_node, c.to_node):
                counts[nid] = counts.get(nid, 0) + 1
        for node in self.nodes:
            if node.node_type in SINGLE_PORT:
                actual = counts.get(node.node_id, 0)
                if actual > 1:
                    raise ValueError(
                        f"Node '{node.node_id}' ({node.node_type}) has {actual} "
                        f"connections but is hard-locked to 1 port. "
                        f"Insert a switch as intermediary."
                    )
        return self

    @model_validator(mode="after")
    def topology_must_be_connected(self):
        if len(self.nodes) <= 1:
            return self

        parent = {n.node_id: n.node_id for n in self.nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for c in self.connections:
            union(c.from_node, c.to_node)

        roots = {find(n.node_id) for n in self.nodes}
        if len(roots) > 1:
            groups: dict[str, list[str]] = {}
            for n in self.nodes:
                groups.setdefault(find(n.node_id), []).append(n.node_id)
            raise ValueError(
                f"Topology is NOT fully connected! {len(roots)} isolated groups: "
                f"{list(groups.values())}. Every node must have a path to every other."
            )
        return self


# ═══════════════════════════════════════════════════════════════════════════════
#  Final topology models (port numbers assigned by port_assigner.py)
# ═══════════════════════════════════════════════════════════════════════════════

class LinkNode(BaseModel):
    node_id: str
    adapter_number: int = Field(..., ge=0)
    port_number: int = Field(..., ge=0)


class Link(BaseModel):
    nodes: List[LinkNode] = Field(..., min_length=2, max_length=2)
    link_type: Literal["ethernet", "serial"] = "ethernet"

    @model_validator(mode="after")
    def endpoints_must_differ(self):
        if self.nodes[0].node_id == self.nodes[1].node_id:
            raise ValueError("A link cannot connect a node to itself.")
        return self


class Node(BaseModel):
    node_id: str
    name: str = Field(..., min_length=1)
    node_type: Literal[
        "cloud", "nat", "ethernet_hub", "ethernet_switch",
        "frame_relay_switch", "atm_switch", "docker", "dynamips",
        "vpcs", "traceng", "virtualbox", "vmware", "iou", "qemu",
    ]
    template_name: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    compute_id: str = Field(default="local")


class Topology(BaseModel):
    """Validated topology with port numbers assigned."""

    SINGLE_PORT_TYPES: ClassVar[dict[str, int]] = {
        "vpcs": 1, "traceng": 1, "nat": 1,
    }

    # Adapter 0 max port number per Dynamips platform.
    # -1 means no built-in Ethernet on adapter 0 at all.
    _DYNAMIPS_ADAPTER0_MAX_ETH_PORT: ClassVar[dict[str, int]] = {
        "c7200": 0,    # C7200-IO-FE = 1 port → port 0 only
        "c3745": 1,    # GT96100-FE = 2 ports → port 0 and 1
        "c3725": 1,    # GT96100-FE = 2 ports
        "c3660": 1,    # Leopard-2FE = 2 ports
        "c3640": -1,   # no built-in → no port 0 available on adapter 0
        "c3620": -1,
        "c2691": 1,    # GT96100-FE = 2 ports
        "c2600": 0,    # 1 built-in FE → port 0 only
        "c1700": 0,    # C1700-MB-1FE = 1 port → port 0 only
        "c3600": 1,    # alias — c3660 spec (Leopard-2FE = 2 ports)
    }
    _DYNAMIPS_ADAPTER0_DEFAULT_MAX: ClassVar[int] = 0

    _SINGLE_PORT_PER_ADAPTER_TYPES: ClassVar[frozenset] = frozenset([
        "qemu", "docker", "virtualbox", "vmware",
    ])

    _MAX_EXPANDABLE_PORTS: ClassVar[dict[str, int]] = {
        "iou": 16, "qemu": 8, "docker": 8,
        "virtualbox": 8, "vmware": 10,
        "ethernet_switch": 128, "ethernet_hub": 128,
    }

    # Dynamips max ports derived from hardware constants at class definition
    # time — no more hardcoded dict that can drift from the real constants.
    _DYNAMIPS_MAX_PORTS: ClassVar[dict[str, int]] = _DYNAMIPS_MAX_PORTS_COMPUTED

    nodes: List[Node] = Field(..., min_length=1)
    links: List[Link] = Field(default_factory=list)

    @model_validator(mode="after")
    def node_ids_must_be_unique(self):
        seen: set[str] = set()
        dupes: set[str] = set()
        for n in self.nodes:
            if n.node_id in seen:
                dupes.add(n.node_id)
            seen.add(n.node_id)
        if dupes:
            raise ValueError(f"Duplicate node_ids: {dupes}")
        return self

    @model_validator(mode="after")
    def link_endpoints_must_reference_existing_nodes(self):
        valid_ids = {n.node_id for n in self.nodes}
        for i, link in enumerate(self.links):
            for ep in link.nodes:
                if ep.node_id not in valid_ids:
                    raise ValueError(
                        f"Link {i} references unknown node '{ep.node_id}'"
                    )
        return self

    @model_validator(mode="after")
    def no_duplicate_links(self):
        seen_pairs: set[tuple] = set()
        for link in self.links:
            key = (
                frozenset([link.nodes[0].node_id, link.nodes[1].node_id]),
                link.link_type,
            )
            if key in seen_pairs:
                raise ValueError(
                    f"Duplicate {link.link_type} link between "
                    f"'{link.nodes[0].node_id}' and '{link.nodes[1].node_id}'"
                )
            seen_pairs.add(key)
        return self

    @model_validator(mode="after")
    def single_port_endpoints_must_use_adapter0_port0(self):
        for link in self.links:
            for ep in link.nodes:
                node = next((n for n in self.nodes if n.node_id == ep.node_id), None)
                if node and node.node_type in self.SINGLE_PORT_TYPES:
                    if ep.adapter_number != 0 or ep.port_number != 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' ({node.node_type}) must use "
                            f"adapter=0, port=0 but got adapter={ep.adapter_number}, "
                            f"port={ep.port_number}. Bug in port_assigner.py."
                        )
        return self

    @model_validator(mode="after")
    def switch_endpoints_must_use_adapter0(self):
        for link in self.links:
            for ep in link.nodes:
                node = next((n for n in self.nodes if n.node_id == ep.node_id), None)
                if node and node.node_type in ("ethernet_switch", "ethernet_hub"):
                    if ep.adapter_number != 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' ({node.node_type}) must use "
                            f"adapter=0 but got adapter={ep.adapter_number}. "
                            f"Bug in port_assigner.py."
                        )
        return self

    @model_validator(mode="after")
    def port_assignments_must_not_collide(self):
        used: dict[str, set[tuple[int, int]]] = {}
        for link in self.links:
            for ep in link.nodes:
                key = (ep.adapter_number, ep.port_number)
                used.setdefault(ep.node_id, set())
                if key in used[ep.node_id]:
                    raise ValueError(
                        f"Port collision on '{ep.node_id}': "
                        f"adapter={ep.adapter_number}/port={ep.port_number} used twice. "
                        f"Bug in port_assigner.py."
                    )
                used[ep.node_id].add(key)
        return self

    @model_validator(mode="after")
    def single_port_nodes_must_not_exceed_one_link(self):
        link_counts: dict[str, int] = {}
        for link in self.links:
            for ep in link.nodes:
                link_counts[ep.node_id] = link_counts.get(ep.node_id, 0) + 1
        for node in self.nodes:
            max_links = self.SINGLE_PORT_TYPES.get(node.node_type)
            if max_links is not None:
                actual = link_counts.get(node.node_id, 0)
                if actual > max_links:
                    raise ValueError(
                        f"Node '{node.node_id}' ({node.node_type}) has {actual} links "
                        f"but is hard-locked to {max_links} port(s). Use a switch."
                    )
        return self

    @model_validator(mode="after")
    def link_count_must_not_exceed_max_ports(self):
        link_counts: dict[str, int] = {}
        for link in self.links:
            for ep in link.nodes:
                link_counts[ep.node_id] = link_counts.get(ep.node_id, 0) + 1

        for node in self.nodes:
            nid = node.node_id
            actual = link_counts.get(nid, 0)
            ntype = node.node_type

            if ntype in self.SINGLE_PORT_TYPES:
                continue

            max_ports = self._MAX_EXPANDABLE_PORTS.get(ntype)
            if ntype == "dynamips":
                platform = (
                    str(node.properties.get("platform", "")).lower()
                    or str(node.template_name).lower()
                )
                max_ports = self._DYNAMIPS_MAX_PORTS.get(
                    platform,
                    max(self._DYNAMIPS_MAX_PORTS.values()),
                )

            if max_ports is None:
                continue

            if actual > max_ports:
                raise ValueError(
                    f"Node '{nid}' ({ntype}) has {actual} links but max is "
                    f"{max_ports}. Use a core-switch pattern to reduce router links."
                )
        return self

    @model_validator(mode="after")
    def port_assignments_must_be_within_bounds(self):
        node_map = {n.node_id: n for n in self.nodes}
        for link in self.links:
            if link.link_type == "serial":
                for ep in link.nodes:
                    node = node_map.get(ep.node_id)
                    if node and node.node_type == "dynamips" and ep.adapter_number == 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' (dynamips): serial links cannot use "
                            f"adapter 0 (no built-in serial ports)."
                        )
                continue

            for ep in link.nodes:
                node = node_map.get(ep.node_id)
                if not node:
                    continue
                if node.node_type == "dynamips" and ep.adapter_number == 0:
                    platform = (
                        str(node.properties.get("platform", "")).lower()
                        or str(node.template_name).lower()
                        or "c7200"
                    )
                    max_port = self._DYNAMIPS_ADAPTER0_MAX_ETH_PORT.get(
                        platform, self._DYNAMIPS_ADAPTER0_DEFAULT_MAX
                    )
                    if ep.port_number > max_port:
                        hint = (
                            f"'{platform}' has NO built-in Ethernet on adapter 0"
                            if max_port < 0
                            else f"'{platform}' max port on adapter 0 is {max_port}"
                        )
                        raise ValueError(
                            f"Node '{ep.node_id}' (dynamips/{platform}): "
                            f"port_number={ep.port_number} on adapter 0 out of bounds. "
                            f"{hint}."
                        )
                if node.node_type in self._SINGLE_PORT_PER_ADAPTER_TYPES:
                    if ep.port_number != 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' ({node.node_type}): port_number "
                            f"must be 0 but got {ep.port_number}. Bug in port_assigner.py."
                        )
        return self

    @model_validator(mode="after")
    def topology_must_be_connected(self):
        if not self.nodes or not self.links:
            return self
        parent = {n.node_id: n.node_id for n in self.nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for link in self.links:
            union(link.nodes[0].node_id, link.nodes[1].node_id)

        roots = {find(n.node_id) for n in self.nodes}
        if len(roots) > 1:
            groups: dict[str, list[str]] = {}
            for n in self.nodes:
                groups.setdefault(find(n.node_id), []).append(n.node_id)
            raise ValueError(
                f"Topology is NOT fully connected! {len(roots)} isolated groups: "
                f"{list(groups.values())}"
            )
        return self


class GNS3Project(BaseModel):
    name: str = Field(..., min_length=1)
    topology: Topology


# ── Soft validation helpers ───────────────────────────────────────────────────

def validate_topology_request(data: dict) -> list[str]:
    errors: list[str] = []
    try:
        TopologyRequest.model_validate(data)
    except Exception as e:
        for line in str(e).splitlines():
            line = line.strip()
            if line and "validation error" not in line.lower():
                errors.append(line)
        if not errors:
            errors.append(str(e))
    return errors


def validate_topology(data: dict) -> list[str]:
    errors: list[str] = []
    try:
        GNS3Project.model_validate(data)
    except Exception as e:
        for line in str(e).splitlines():
            line = line.strip()
            if line and "validation error" not in line.lower():
                errors.append(line)
        if not errors:
            errors.append(str(e))
    return errors