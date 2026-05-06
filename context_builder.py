"""
context_builder.py — Phase 2 Context Builder for Structranet AI

Transforms Phase 1 topology JSON into a human-readable Configuration Brief
that the LLM can use to generate accurate software configurations.

Steps handled:
  1. Parse the Phase 1 JSON
  2. Resolve canonical port names  (adapter/port → FastEthernet0/0, eth0, etc.)
  3. Group links into Segments     (broadcast domains vs point-to-point)
  4. Generate the Configuration Brief string

The brief deliberately hides hardware noise (slots, adapters, ports_mapping)
and presents only what the LLM needs: device roles, interface names, and
which interfaces share a subnet.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger("structranet.context_builder")


# ═══════════════════════════════════════════════════════════════════════════════
#  Constants — Dynamips module → interface mapping
# ═══════════════════════════════════════════════════════════════════════════════

# Each Dynamips expansion module defines what kind of interfaces it provides.
#   prefix  → Cisco IOS interface prefix (Ethernet, FastEthernet, etc.)
#   count   → number of ports on that module
#
# Source: Dynamips source code + GNS3 port_factory.py naming conventions
DYNAMIPS_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    # Port Adapters (c7200)
    "PA-8E":      {"prefix": "Ethernet",        "count": 8},
    "PA-4E":      {"prefix": "Ethernet",        "count": 4},
    "PA-FE-TX":   {"prefix": "FastEthernet",    "count": 2},
    "PA-2FE-TX":  {"prefix": "FastEthernet",    "count": 2},
    "PA-GE":      {"prefix": "GigabitEthernet", "count": 1},
    # Network Modules (c3700 / c3600 / c2600 / c1700)
    "NM-4E":      {"prefix": "Ethernet",        "count": 4},
    "NM-1E":      {"prefix": "Ethernet",        "count": 1},
    "NM-1FE-TX":  {"prefix": "FastEthernet",    "count": 1},
    "NM-16ESW":   {"prefix": "FastEthernet",    "count": 16},
    "GT96100-FE": {"prefix": "FastEthernet",    "count": 2},
}

# Built-in interfaces per Dynamips platform (slot 0, before any expansion)
DYNAMIPS_BUILTIN_INTERFACES: Dict[str, Dict[str, Any]] = {
    "c7200":  {"prefix": "FastEthernet", "count": 1},   # Fa0/0 on NPE
    "c3745":  {"prefix": "FastEthernet", "count": 2},   # Fa0/0, Fa0/1
    "c3725":  {"prefix": "FastEthernet", "count": 2},   # Fa0/0, Fa0/1
    "c3660":  {"prefix": "FastEthernet", "count": 1},
    "c3640":  {"prefix": None,           "count": 0},   # NM-only, no built-in
    "c3620":  {"prefix": None,           "count": 0},
    "c2691":  {"prefix": "FastEthernet", "count": 2},
    "c2600":  {"prefix": "FastEthernet", "count": 1},
    "c1700":  {"prefix": "FastEthernet", "count": 1},
}

# ── Node classification ─────────────────────────────────────────────────────

# Node types that create broadcast domains (concentrators)
L2_CONCENTRATOR_TYPES: FrozenSet[str] = frozenset(["ethernet_switch", "ethernet_hub"])

# Node types that act as Layer 3 boundaries (routers, appliances)
L3_ROUTER_TYPES: FrozenSet[str] = frozenset([
    "dynamips", "iou", "qemu", "docker", "virtualbox", "vmware",
])

# Node types that don't need IP configuration
NO_CONFIG_TYPES: FrozenSet[str] = frozenset([
    "ethernet_switch", "ethernet_hub", "nat", "cloud",
    "frame_relay_switch", "atm_switch",
])

# Human-readable role labels for the brief
NODE_ROLE_MAP: Dict[str, str] = {
    "dynamips":         "router",
    "iou":              "router",
    "qemu":             "appliance",
    "docker":           "container",
    "vpcs":             "host",
    "traceng":          "host",
    "ethernet_switch":  "switch",
    "ethernet_hub":     "hub",
    "cloud":            "cloud",
    "nat":              "nat",
    "virtualbox":       "appliance",
    "vmware":           "appliance",
}

# Software config key per node type — included in the brief so the LLM
# knows exactly which property name to use (avoids the startup_script vs
# startup_script_content mistake we caught in the audit)
CONFIG_KEY_MAP: Dict[str, List[str]] = {
    "dynamips": ["startup_config_content"],
    "iou":      ["startup_config_content"],
    "qemu":     ["startup_config_content"],
    "vpcs":     ["startup_script"],
    "docker":   ["start_command", "environment"],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResolvedPort:
    """A link endpoint with its canonical interface name resolved."""
    node_id: str
    node_name: str
    node_type: str
    adapter_number: int
    port_number: int
    canonical_name: str  # e.g. "FastEthernet0/0", "eth0", "Ethernet3"


@dataclass
class Segment:
    """A network segment — either a broadcast domain or point-to-point link.

    link_pairs stores each link as a (endpoint_a, endpoint_b) tuple so the
    brief can show connections as "R1 Fa0/0 ↔ SW1 Eth0".
    """
    segment_id: int
    seg_type: str  # "multi-access" or "point-to-point"
    link_pairs: List[Tuple[ResolvedPort, ResolvedPort]]
    concentrator_ids: Set[str] = field(default_factory=set)


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 2: Port Name Resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _identify_platform(node: dict) -> str:
    """Identify the Dynamips platform from node properties or template_name."""
    props = node.get("properties", {})
    platform = props.get("platform")
    if platform:
        return str(platform).lower()
    template = node.get("template_name", "")
    if template:
        return str(template).lower()
    return "c7200"


def resolve_port_name(node: dict, adapter_number: int, port_number: int) -> str:
    """Translate (adapter_number, port_number) into a canonical interface name.

    This is the critical translation that makes Phase 2 configs actually work.
    Without it, the LLM would guess interface names and get them wrong.

    Examples::

        dynamips/c7200  adapter=0  port=0 → "FastEthernet0/0"
        dynamips/c7200  adapter=1  port=3 → "Ethernet1/3"
        iou             adapter=1  port=2 → "Ethernet1/2"
        qemu            adapter=2  port=0 → "eth2"
        docker          adapter=1  port=0 → "eth1"
        vpcs            adapter=0  port=0 → "eth0"
        ethernet_switch adapter=0  port=5 → "Ethernet5"
    """
    node_type = node.get("node_type", "")

    if node_type == "dynamips":
        return _resolve_dynamips_port(node, adapter_number, port_number)
    if node_type == "iou":
        return f"Ethernet{adapter_number}/{port_number}"
    if node_type in ("qemu", "docker", "virtualbox", "vmware"):
        return f"eth{adapter_number}"
    if node_type in ("vpcs", "traceng"):
        return "eth0"
    if node_type in ("ethernet_switch", "ethernet_hub"):
        return f"Ethernet{port_number}"
    if node_type == "nat":
        return "nat0"
    if node_type == "cloud":
        return f"Cloud{port_number}"

    # Fallback for unknown types
    return f"adapter{adapter_number}/port{port_number}"


def _resolve_dynamips_port(
    node: dict, adapter_number: int, port_number: int
) -> str:
    """Resolve a Dynamips (slot, port) to a Cisco IOS interface name.

    Logic:
      1. Adapter 0 = built-in interfaces (platform-specific count + prefix)
      2. Adapter N (N≥1) = expansion module in slot N (read from properties.slotN)
      3. The module type determines the interface prefix and port count
    """
    platform = _identify_platform(node)
    props = node.get("properties", {})

    # ── Adapter 0: built-in interfaces ──
    if adapter_number == 0:
        builtin = DYNAMIPS_BUILTIN_INTERFACES.get(
            platform, {"prefix": "FastEthernet", "count": 1}
        )
        prefix = builtin.get("prefix") or "FastEthernet"
        return f"{prefix}0/{port_number}"

    # ── Adapter N ≥ 1: expansion module ──
    slot_key = f"slot{adapter_number}"
    module_name = props.get(slot_key, "")

    if module_name and module_name in DYNAMIPS_MODULE_INTERFACES:
        mod = DYNAMIPS_MODULE_INTERFACES[module_name]
        return f"{mod['prefix']}{adapter_number}/{port_number}"

    # Fallback: unknown module → assume Ethernet
    logger.debug(
        "Unknown module '%s' in %s slot %d — defaulting to Ethernet",
        module_name, platform, adapter_number,
    )
    return f"Ethernet{adapter_number}/{port_number}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 2b: Enumerate all interfaces on a node (for the brief)
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_all_interfaces(node: dict) -> List[str]:
    """List all canonical interface names for a node.

    Used in the brief to show the LLM what interfaces exist, even if not
    all of them are connected by a link.
    """
    node_type = node.get("node_type", "")
    props = node.get("properties", {})

    if node_type == "dynamips":
        return _list_dynamips_interfaces(node)
    if node_type == "iou":
        return _list_iou_interfaces(node)
    if node_type in ("qemu", "docker", "virtualbox", "vmware"):
        adapters = props.get("adapters", 1)
        return [f"eth{i}" for i in range(adapters)]
    if node_type in ("vpcs", "traceng"):
        return ["eth0"]
    if node_type in ("ethernet_switch", "ethernet_hub"):
        pm = props.get("ports_mapping")
        count = len(pm) if pm else 8
        return [f"Ethernet{i}" for i in range(count)]
    if node_type == "nat":
        return ["nat0"]
    if node_type == "cloud":
        return ["Cloud0"]
    return []


def _list_dynamips_interfaces(node: dict) -> List[str]:
    """Enumerate all interface names for a Dynamips router."""
    platform = _identify_platform(node)
    props = node.get("properties", {})
    interfaces: List[str] = []

    # Built-in (slot 0)
    builtin = DYNAMIPS_BUILTIN_INTERFACES.get(
        platform, {"prefix": "FastEthernet", "count": 1}
    )
    prefix = builtin.get("prefix")
    if prefix and builtin["count"] > 0:
        for p in range(builtin["count"]):
            interfaces.append(f"{prefix}0/{p}")

    # Expansion slots (slot1 through slot6)
    for slot_num in range(1, 7):
        slot_key = f"slot{slot_num}"
        module_name = props.get(slot_key, "")
        if not module_name:
            continue
        mod = DYNAMIPS_MODULE_INTERFACES.get(module_name)
        if mod:
            for p in range(mod["count"]):
                interfaces.append(f"{mod['prefix']}{slot_num}/{p}")
        else:
            # Unknown module — assume 1 Ethernet port as fallback
            interfaces.append(f"Ethernet{slot_num}/0")

    return interfaces


def _list_iou_interfaces(node: dict) -> List[str]:
    """Enumerate all interface names for an IOU device."""
    props = node.get("properties", {})
    interfaces: List[str] = []

    for slot_num in range(16):
        slot_key = f"slot{slot_num}"
        module_val = props.get(slot_key)
        if module_val is None:
            continue
        # L3 IOU: module is an integer (typically 0–3), 4 interfaces per slot
        # L2 IOU: module is "l2", also 4 interfaces per slot
        if isinstance(module_val, int) or (
            isinstance(module_val, str) and module_val != ""
        ):
            for p in range(4):
                interfaces.append(f"Ethernet{slot_num}/{p}")

    return interfaces


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1: Parse + Step 3: Segment Building
# ═══════════════════════════════════════════════════════════════════════════════

def _build_node_map(topology: dict) -> Dict[str, dict]:
    """Index nodes by node_id for O(1) lookup."""
    return {n["node_id"]: n for n in topology.get("nodes", [])}


def _resolve_endpoint(ep: dict, node_map: Dict[str, dict]) -> ResolvedPort:
    """Convert a raw link endpoint dict into a ResolvedPort."""
    nid = ep.get("node_id", "")
    node = node_map.get(nid, {})
    adapter = ep.get("adapter_number", 0)
    port = ep.get("port_number", 0)

    return ResolvedPort(
        node_id=nid,
        node_name=node.get("name", nid),
        node_type=node.get("node_type", ""),
        adapter_number=adapter,
        port_number=port,
        canonical_name=resolve_port_name(node, adapter, port),
    )


def build_segments(
    topology: dict, node_map: Dict[str, dict]
) -> List[Segment]:
    """Group links into network segments, respecting Layer 3 boundaries.

    KEY INSIGHT: A router is a Layer 3 boundary. Each router interface
    defines a separate broadcast domain, even if switches are daisy-chained
    on Layer 2. Two switches connected to DIFFERENT router interfaces are
    in DIFFERENT segments, even if a switch-to-switch uplink exists.

    Algorithm:
      1. For each link, determine its "segment key":
         - If a router is involved: key = (router_id, router_interface)
         - If only switches/hubs: key = the concentrator group (Union-Find)
      2. Group links by segment key
      3. Each group becomes one Segment (multi-access or point-to-point)
    """
    links = topology.get("links", [])

    # Identify concentrator nodes
    concentrator_ids: Set[str] = set()
    for node in topology.get("nodes", []):
        if node.get("node_type") in L2_CONCENTRATOR_TYPES:
            concentrator_ids.add(node["node_id"])

    # ── Union-Find for concentrator groups (switch-to-switch only) ──
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])  # path compression
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Union concentrators that are directly connected (switch-to-switch links)
    # BUT NOT through a router — a router is a Layer 3 boundary
    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        # Only union two concentrators if NEITHER endpoint is a router
        if (a_type in L2_CONCENTRATOR_TYPES and
                b_type in L2_CONCENTRATOR_TYPES):
            # Both are switches/hubs — same L2 domain
            union(a_id, b_id)

    # ── Assign segment keys ──────────────────────────────────────────
    # For each link, compute a segment key that respects L3 boundaries.
    # Key format: "router:R1:FastEthernet0/0" or "switch:SW_root_id"
    link_segment_keys: List[str] = []

    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            link_segment_keys.append("")
            continue

        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        a_is_router = a_type in L3_ROUTER_TYPES
        b_is_router = b_type in L3_ROUTER_TYPES
        a_is_conc = a_type in L2_CONCENTRATOR_TYPES
        b_is_conc = b_type in L2_CONCENTRATOR_TYPES

        if a_is_router and b_is_router:
            # Router-to-router: true point-to-point
            key = f"p2p:{a_id}:{eps[0].get('adapter_number',0)}:{eps[0].get('port_number',0)}"
        elif a_is_router:
            # Router to switch/host — router interface is the L3 boundary
            resolved = resolve_port_name(
                node_map[a_id],
                eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0),
            )
            key = f"router:{a_id}:{resolved}"
        elif b_is_router:
            # Switch/host to router — router interface is the L3 boundary
            resolved = resolve_port_name(
                node_map[b_id],
                eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0),
            )
            key = f"router:{b_id}:{resolved}"
        elif a_is_conc and b_is_conc:
            # Switch-to-switch (same L2 domain, no router between them)
            root = find(a_id)
            key = f"switch_group:{root}"
        elif a_is_conc:
            # Switch to host — group under the switch's root
            root = find(a_id)
            # If this switch is also connected to a router, use the
            # router's segment key instead (find the router link)
            key = _find_router_segment_key(
                a_id, links, node_map, concentrator_ids, find
            )
        elif b_is_conc:
            root = find(b_id)
            key = _find_router_segment_key(
                b_id, links, node_map, concentrator_ids, find
            )
        else:
            # Neither router nor switch (e.g., VPCS-to-VPCS — shouldn't happen)
            key = f"p2p:{a_id}:{eps[0].get('adapter_number',0)}:{eps[0].get('port_number',0)}"

        link_segment_keys.append(key)

    # ── Group links by segment key ───────────────────────────────────
    grouped: Dict[str, List[dict]] = {}
    for i, key in enumerate(link_segment_keys):
        if key:
            grouped.setdefault(key, []).append(links[i])

    # ── Build Segment objects ────────────────────────────────────────
    segments: List[Segment] = []
    seg_id = 1

    for key, links_in in grouped.items():
        pair_list: List[Tuple[ResolvedPort, ResolvedPort]] = []
        conc_ids: Set[str] = set()

        for link in links_in:
            eps = link.get("nodes", [])
            if len(eps) < 2:
                continue
            rp_a = _resolve_endpoint(eps[0], node_map)
            rp_b = _resolve_endpoint(eps[1], node_map)
            pair_list.append((rp_a, rp_b))

            if rp_a.node_id in concentrator_ids:
                conc_ids.add(rp_a.node_id)
            if rp_b.node_id in concentrator_ids:
                conc_ids.add(rp_b.node_id)

        seg_type = "point-to-point" if key.startswith("p2p:") else "multi-access"

        segments.append(Segment(
            segment_id=seg_id,
            seg_type=seg_type,
            link_pairs=pair_list,
            concentrator_ids=conc_ids,
        ))
        seg_id += 1

    return segments


def _find_router_segment_key(
    switch_id: str,
    all_links: List[dict],
    node_map: Dict[str, dict],
    concentrator_ids: Set[str],
    find_func,
) -> str:
    """Find which router interface a switch is connected to (directly or
    via other switches) and return a router-based segment key.

    If the switch group has NO router uplink, fall back to switch_group key.
    """
    # Check direct links from this switch (or its union group) to a router
    for link in all_links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        # If one endpoint is a router and the other is in the same
        # concentrator group as our switch_id
        if a_type in L3_ROUTER_TYPES and b_type in L2_CONCENTRATOR_TYPES:
            if find_func(b_id) == find_func(switch_id):
                resolved = resolve_port_name(
                    node_map[a_id],
                    eps[0].get("adapter_number", 0),
                    eps[0].get("port_number", 0),
                )
                return f"router:{a_id}:{resolved}"

        if b_type in L3_ROUTER_TYPES and a_type in L2_CONCENTRATOR_TYPES:
            if find_func(a_id) == find_func(switch_id):
                resolved = resolve_port_name(
                    node_map[b_id],
                    eps[1].get("adapter_number", 0),
                    eps[1].get("port_number", 0),
                )
                return f"router:{b_id}:{resolved}"

    # No router uplink found — isolated switch group
    root = find_func(switch_id)
    return f"switch_group:{root}"

# ═══════════════════════════════════════════════════════════════════════════════
#  Step 4: Configuration Brief Generation
# ═══════════════════════════════════════════════════════════════════════════════

def _compact_interface_list(interfaces: List[str]) -> str:
    """Compress interface lists for readability.

    ["Ethernet0", "Ethernet1", ..., "Ethernet7"] → "Ethernet0..Ethernet7"
    """
    if not interfaces:
        return "(none)"
    if len(interfaces) <= 4:
        return ", ".join(interfaces)
    return f"{interfaces[0]}..{interfaces[-1]}"


def _collect_segment_hosts(seg: Segment) -> List[ResolvedPort]:
    """Return the non-concentrator endpoints in a segment (devices that need IPs)."""
    hosts: List[ResolvedPort] = []
    seen: Set[str] = set()
    for ep_a, ep_b in seg.link_pairs:
        for ep in (ep_a, ep_b):
            if ep.node_type not in L2_CONCENTRATOR_TYPES:
                # Deduplicate by (node_id, canonical_name)
                key = f"{ep.node_id}:{ep.canonical_name}"
                if key not in seen:
                    seen.add(key)
                    hosts.append(ep)
    return hosts


def generate_brief(topology: dict) -> str:
    """Generate the human-readable Configuration Brief from a Phase 1 topology.

    This is the core function. Returns a formatted string ready to be
    injected into the LLM system prompt for Phase 2 config generation.
    """
    node_map = _build_node_map(topology)
    segments = build_segments(topology, node_map)
    nodes = topology.get("nodes", [])

    lines: List[str] = []

    # ── Header ──
    lines.append("NETWORK TOPOLOGY — CONFIGURATION BRIEF")
    lines.append("=" * 45)
    lines.append("")

    # ── NODES section ──
    lines.append("NODES:")
    for node in nodes:
        nid = node.get("node_id", "?")
        ntype = node.get("node_type", "")
        template = node.get("template_name", "")
        role = NODE_ROLE_MAP.get(ntype, ntype)

        interfaces = _resolve_all_interfaces(node)
        iface_str = _compact_interface_list(interfaces)

        lines.append(f"  {nid} ({ntype}/{template}, {role})")
        lines.append(f"    Interfaces: {iface_str}")
    lines.append("")

    # ── SEGMENTS section ──
    lines.append("SEGMENTS:")
    for seg in segments:
        hosts = _collect_segment_hosts(seg)
        host_count = len(hosts)

        if seg.seg_type == "multi-access":
            lines.append(
                f"  Segment {seg.segment_id} (multi-access, {host_count} host(s)):"
            )
            # Show each link as:  host_iface  ↔  switch_port
            for ep_a, ep_b in seg.link_pairs:
                if ep_a.node_type in L2_CONCENTRATOR_TYPES:
                    # Switch on the A side → swap for readability
                    lines.append(
                        f"    {ep_b.node_id:6s} {ep_b.canonical_name:20s}"
                        f"  <->  {ep_a.node_id} {ep_a.canonical_name}"
                    )
                elif ep_b.node_type in L2_CONCENTRATOR_TYPES:
                    lines.append(
                        f"    {ep_a.node_id:6s} {ep_a.canonical_name:20s}"
                        f"  <->  {ep_b.node_id} {ep_b.canonical_name}"
                    )
                else:
                    # Both are non-switch (e.g. router-router via switch)
                    lines.append(
                        f"    {ep_a.node_id:6s} {ep_a.canonical_name:20s}"
                        f"  <->  {ep_b.node_id} {ep_b.canonical_name}"
                    )
        else:
            lines.append(f"  Segment {seg.segment_id} (point-to-point):")
            for ep_a, ep_b in seg.link_pairs:
                lines.append(
                    f"    {ep_a.node_id:6s} {ep_a.canonical_name:20s}"
                    f"  <->  {ep_b.node_id:6s} {ep_b.canonical_name}"
                )

        lines.append("")

    # ── CONFIG KEY MAPPING section ──
    lines.append("CONFIG KEY MAPPING (use these exact property names):")
    present_types = {n.get("node_type") for n in nodes}
    for ntype in sorted(present_types):
        keys = CONFIG_KEY_MAP.get(ntype)
        if keys:
            lines.append(f"  {ntype} -> {', '.join(keys)}")
        elif ntype in NO_CONFIG_TYPES:
            lines.append(f"  {ntype} -> No config needed (Layer 1/2)")
    lines.append("")

    # ── ARCHITECTURAL ADVICE section ──
    lines.append("ARCHITECTURAL ADVICE:")

    # Count access switches: any ethernet_switch whose name does NOT
    # contain "Core" (case-insensitive).  Access switches serve end-devices
    # in distinct departments/floors/zones and SHOULD be on separate
    # broadcast domains.  Core switches are L2 concentrators that
    # interconnect access switches and the router.
    access_switches = [
        n for n in nodes
        if n.get("node_type") == "ethernet_switch"
        and "core" not in n.get("name", "").lower()
    ]
    access_count = len(access_switches)

    if access_count > 1:
        # Multi-department topology — requires L3 segmentation
        access_names = ", ".join(n.get("name", n.get("node_id", "?")) for n in access_switches)
        lines.append(
            f"  This is a MULTI-DEPARTMENT network with {access_count} access "
            f"switch(es): [{access_names}]."
        )
        lines.append(
            "  You MUST implement Router-on-a-Stick (802.1Q sub-interfaces) "
            "so each access switch operates in its OWN VLAN with its OWN "
            "unique subnet."
        )
        lines.append(
            "  Pattern: Router sub-if N → VLAN N → Access Switch N → "
            "end-devices in VLAN N's subnet."
        )
        lines.append(
            "  NEVER place all access switches / end-devices in a single "
            "flat subnet — that defeats the purpose of having separate "
            "switches per department."
        )
    elif access_count == 1:
        lines.append(
            "  This is a simple single-department network. A flat subnet "
            "is acceptable."
        )
    else:
        # No access switches at all (only core, or no switches)
        lines.append(
            "  No access switches detected. Assign one subnet per segment "
            "as usual."
        )
    lines.append("")

    # ── TASK section ──
    lines.append("TASK:")
    lines.append("  1. Assign one subnet per segment (no overlaps).")
    lines.append("  2. Use /24 for multi-access segments, /30 for point-to-point.")
    lines.append("  3. For each router: generate a full Cisco IOS startup config.")
    lines.append("  4. For each VPCS host: generate a startup_script with 'ip' command.")
    lines.append("  5. For each Docker container: set 'environment' and 'start_command'.")
    lines.append("  6. Skip switches, hubs, and NAT nodes — they need no IP config.")
    lines.append(
        "  7. Include routing protocols (OSPF or static) for multi-segment routers."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

def build_configuration_brief(phase1_json_path: str) -> str:
    """Load a Phase 1 JSON file and return the Configuration Brief string.

    This is the main entry point for context_builder.py.

    Parameters
    ----------
    phase1_json_path : str
        Path to the Phase 1 output JSON (e.g. ``output/_topology.json``)

    Returns
    -------
    str
        The formatted Configuration Brief, ready to inject into the LLM prompt
    """
    path = Path(phase1_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Phase 1 JSON not found: {phase1_json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Unwrap from the GNS3Project structure  { "name": ..., "topology": {…} }
    topology = data.get("topology", data)

    brief = generate_brief(topology)
    logger.info("Configuration brief generated (%d chars)", len(brief))
    return brief


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point (for testing)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s"
    )

    # Accept path as CLI arg, or use default
    json_path = sys.argv[1] if len(sys.argv) > 1 else "output/_topology.json"

    try:
        brief = build_configuration_brief(json_path)
        print(brief)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Usage: python context_builder.py [path_to_phase1_json]")
        sys.exit(1)
