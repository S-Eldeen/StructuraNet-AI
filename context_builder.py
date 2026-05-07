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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

# Import hardware constants from the single source of truth in hw_config.
# This eliminates the dual-maintenance problem: if the Dynamips builtin port
# counts or IOU ports-per-slot values change, context_builder.py inherits
# the update automatically.
from hw_config import DYNAMIPS_BUILTIN_PORTS as _HW_DYNAMIPS_BUILTIN_PORTS
from hw_config import IOU_PORTS_PER_SLOT as _HW_IOU_PORTS_PER_SLOT

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

    vlan_id is set for Router-on-a-Stick segments: each access switch that
    hangs off a core switch gets its own VLAN ID so the brief tells the LLM
    which sub-interface to configure (e.g., Fa0/0.10 for VLAN 10).
    A value of 0 means "untagged / no VLAN" (simple flat topology).
    """
    segment_id: int
    seg_type: str  # "multi-access" or "point-to-point"
    link_pairs: List[Tuple[ResolvedPort, ResolvedPort]]
    concentrator_ids: Set[str] = field(default_factory=set)
    vlan_id: int = 0                 # 0 = untagged; >0 = 802.1Q VLAN
    access_switch_name: str = ""     # human name of the access switch for this segment


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
    """Enumerate all interface names for a Dynamips router.

    Port COUNT comes from _HW_DYNAMIPS_BUILTIN_PORTS (imported from hw_config —
    single source of truth shared with the slot-injection logic).
    Interface PREFIX comes from DYNAMIPS_BUILTIN_INTERFACES (local dict) because
    hw_config only tracks counts, not IOS naming prefixes.  These two concerns
    are intentionally split: if the port count in hw_config changes, this
    function inherits it automatically without a separate edit here.
    """
    platform = _identify_platform(node)
    props = node.get("properties", {})
    interfaces: List[str] = []

    # Built-in (slot 0) — count from hw_config, prefix from local dict
    builtin_count = _HW_DYNAMIPS_BUILTIN_PORTS.get(platform, 1)
    builtin_prefix_entry = DYNAMIPS_BUILTIN_INTERFACES.get(
        platform, {"prefix": "FastEthernet", "count": 1}
    )
    prefix = builtin_prefix_entry.get("prefix")
    if prefix and builtin_count > 0:
        for p in range(builtin_count):
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
    """Enumerate all interface names for an IOU device.

    Uses _HW_IOU_PORTS_PER_SLOT imported from hw_config (single source of truth)
    instead of a hardcoded literal so changes to the constant propagate here
    automatically.
    """
    props = node.get("properties", {})
    interfaces: List[str] = []

    for slot_num in range(16):
        slot_key = f"slot{slot_num}"
        module_val = props.get(slot_key)
        if module_val is None:
            continue
        # L3 IOU: module is an integer (typically 0–3), N interfaces per slot
        # L2 IOU: module is "l2", also N interfaces per slot
        if isinstance(module_val, int) or (
            isinstance(module_val, str) and module_val != ""
        ):
            for p in range(_HW_IOU_PORTS_PER_SLOT):
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


def _infer_vlan_for_access_switch(
    switch_name: str,
    vlan_counter: List[int],
    used_vlans: Set[int],
) -> int:
    """Assign a unique VLAN ID to an access switch.

    Priority order:
      1. Explicit ``vlan`` property on the switch node — handled by the caller
         before this function is called.
      2. Name-encoded VLAN: if the switch name matches ``<prefix><N>-SW``
         (e.g. F1-SW, Floor2-SW), extract N and return N*10 — IF that value
         has not already been claimed by another switch.
      3. Sequential allocation: walk the counter from its current position,
         incrementing by 10, skipping any already-used value.

    Parameters
    ----------
    switch_name:
        Human-readable name of the switch node (e.g. "F1-SW", "Admin-SW").
    vlan_counter:
        Single-element list holding the next candidate VLAN for sequential
        allocation.  Mutated in place so all callers share the same counter.
    used_vlans:
        Set of VLAN IDs already assigned in this topology.  Every ID returned
        by this function is added to the set by the caller so subsequent calls
        see the full picture.  Both the regex and the sequential strategy check
        this set before committing to a candidate.

    The ``used_vlans`` parameter is what Z AI flagged: without it, strategy 2
    (regex) can return VLAN 10 for "F1-SW" while strategy 3 (sequential)
    independently returns VLAN 10 for "Admin-SW" (which has no digit suffix),
    producing two access switches sharing the same VLAN ID.  That causes the
    GNS3 switch to merge their broadcast domains silently — hosts from Floor 1
    and Admin would be in the same VLAN and could communicate unintentionally.
    """
    # ── Strategy 2: name-encoded VLAN ────────────────────────────────
    # Pattern: one or more letters, followed by digits, followed by "-SW"
    # Examples: F1-SW→10, F2-SW→20, Floor3-SW→30, Lab12-SW→120
    m = re.match(r"^[A-Za-z]+(\d+)-SW$", switch_name, re.IGNORECASE)
    if m:
        suffix = int(m.group(1))
        candidate = suffix * 10
        if 1 <= candidate <= 4094 and candidate not in used_vlans:
            return candidate
        # Candidate collides or is out of range — fall through to sequential

    # ── Strategy 3: sequential allocation ────────────────────────────
    # Walk forward from vlan_counter[0] until we find a free slot.
    # The counter starts at 10 and increments by 10, but we skip any
    # value already used so the step is not always exactly 10.
    while vlan_counter[0] in used_vlans or vlan_counter[0] < 1:
        vlan_counter[0] += 10
        if vlan_counter[0] > 4094:
            # Exhausted the VLAN space — should never happen in practice
            # (would require >409 access switches) but we must not loop forever.
            raise ValueError(
                f"VLAN space exhausted while assigning VLAN for switch "
                f"'{switch_name}'.  All VLAN IDs 10–4094 (step 10) are in use."
            )

    result = vlan_counter[0]
    vlan_counter[0] += 10   # advance for the next caller
    return result


def _identify_core_switches(
    topology: dict,
    node_map: Dict[str, dict],
) -> Set[str]:
    """Return the node_ids of switches that act as distribution/core switches.

    A switch is classified as a "core" switch if ANY of these conditions hold:
      1. Its name contains "core" (case-insensitive) — explicit naming convention.
      2. It is directly connected to BOTH a router AND at least one other switch.
         This is the structural definition: a core switch is the one that bridges
         the router to the access layer.

    All other switches are "access" switches that serve end-devices.
    """
    links = topology.get("links", [])
    core_ids: Set[str] = set()

    for node in topology.get("nodes", []):
        if node.get("node_type") not in L2_CONCENTRATOR_TYPES:
            continue
        nid = node["node_id"]
        name = node.get("name", "").lower()

        # Condition 1: explicit "core" in name
        if "core" in name:
            core_ids.add(nid)
            continue

        # Condition 2: connected to a router AND at least one other switch
        has_router_neighbor = False
        has_switch_neighbor = False
        for link in links:
            eps = link.get("nodes", [])
            if len(eps) < 2:
                continue
            a_id = eps[0].get("node_id", "")
            b_id = eps[1].get("node_id", "")
            other_id = b_id if a_id == nid else (a_id if b_id == nid else None)
            if other_id is None:
                continue
            other_type = node_map.get(other_id, {}).get("node_type", "")
            if other_type in L3_ROUTER_TYPES:
                has_router_neighbor = True
            elif other_type in L2_CONCENTRATOR_TYPES:
                has_switch_neighbor = True

        if has_router_neighbor and has_switch_neighbor:
            core_ids.add(nid)

    return core_ids


def build_segments(
    topology: dict, node_map: Dict[str, dict]
) -> List[Segment]:
    """Group links into network segments, respecting Layer 3 boundaries.

    KEY INSIGHT: A router is a Layer 3 boundary. Each router interface
    defines a separate broadcast domain, even if switches are daisy-chained
    on Layer 2. Two switches connected to DIFFERENT router interfaces are
    in DIFFERENT segments, even if a switch-to-switch uplink exists.

    ROUTER-ON-A-STICK FIX (the critical change from the original):
    In a Router-on-a-Stick topology, ALL access switches share a single
    physical router interface (Fa0/0).  The original code collapsed every
    link that could trace back to Fa0/0 into a single segment, producing
    a brief that told the LLM there was one flat network with 25 hosts —
    exactly wrong.

    The fix introduces VLAN-aware segment splitting:
      - Identify "core" switches (those connected to BOTH a router and other
        switches) via _identify_core_switches().
      - For each access switch hanging off a core switch, assign a unique
        VLAN ID via _infer_vlan_for_access_switch().
      - Segment keys for access-switch-connected links use the form
        "router:R1:FastEthernet0/0:vlan:10" instead of the bare physical
        interface key, so each access switch produces its own distinct segment.

    This means the brief now tells the LLM:
      Segment 1 (VLAN 10, F1-SW): router sub-if Fa0/0.10
      Segment 2 (VLAN 20, F2-SW): router sub-if Fa0/0.20
      Segment 3 (VLAN 30, Admin-SW): router sub-if Fa0/0.30

    Algorithm:
      1. Identify concentrators, core switches, and access switches.
      2. Assign VLAN IDs to access switches.
      3. For each link, compute a segment key:
         - Router ↔ router: point-to-point
         - Router ↔ core switch: the trunk link — keyed to router interface
           (no VLAN suffix; the trunk itself is not a routed segment)
         - Access switch or its hosts: keyed by (router_iface + vlan_id)
         - Isolated switch groups: keyed by Union-Find root
      4. Group links by key; build Segment objects with vlan_id set.
    """
    links = topology.get("links", [])

    # ── Identify structural roles ─────────────────────────────────────
    concentrator_ids: Set[str] = set()
    for node in topology.get("nodes", []):
        if node.get("node_type") in L2_CONCENTRATOR_TYPES:
            concentrator_ids.add(node["node_id"])

    core_switch_ids = _identify_core_switches(topology, node_map)
    access_switch_ids = concentrator_ids - core_switch_ids

    logger.debug(
        "build_segments: core_switches=%s  access_switches=%s",
        core_switch_ids, access_switch_ids,
    )

    # ── Union-Find for concentrator groups (switch-to-switch only) ──
    # NOTE: we intentionally union ALL switch-to-switch pairs here so that
    # _find_router_segment_key_vlan can traverse the full L2 domain.
    # The VLAN-aware segment splitting happens at key assignment time, not
    # at the union-find level.
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")
        if a_type in L2_CONCENTRATOR_TYPES and b_type in L2_CONCENTRATOR_TYPES:
            union(a_id, b_id)

    # ── Assign VLAN IDs to access switches ───────────────────────────
    # IMPORTANT: only access switches that are children of a core switch
    # (i.e., true Router-on-a-Stick participants) get VLAN IDs.  A switch
    # that connects DIRECTLY to a router without a core switch in between
    # is part of a flat network and should remain untagged (vlan_id = 0).
    #
    # COUNTER DESIGN: The sequential fallback counter starts at 100, not 10.
    # This isolates two non-overlapping VLAN spaces:
    #   • Regex space  (strategy 2): 10, 20, 30, ... 4090  — name-encoded
    #   • Sequential space (strategy 3): 100, 110, 120, ...  — unnamed switches
    # Starting at 100 means an unnamed switch (Admin-SW, Mgmt-SW, etc.) that
    # has no digit suffix can never steal VLAN 10 or 20 from a named switch
    # simply because it happened to be iterated first.  The naming convention
    # F1→10, F2→20, F3→30 is always honoured for switches that carry it;
    # unnamed switches fall into the high range and do not interfere.
    #
    # used_vlans tracks every committed ID so both strategies can detect and
    # avoid collisions even across the two spaces.  Explicit node-property
    # VLANs are registered in Pass 1 before any inference runs.
    vlan_counter = [100]   # sequential fallback space: 100, 110, 120, ...
    used_vlans: Set[int] = set()
    access_switch_vlan: Dict[str, int] = {}          # node_id → vlan_id
    access_switch_name_map: Dict[str, str] = {}      # node_id → human name

    # Determine which access switches are actually children of a core switch
    # (a switch whose parent in the L2 domain is a core switch, not a router)
    access_sw_has_core_parent: Set[str] = set()
    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        if a_id in core_switch_ids and b_id in access_switch_ids:
            access_sw_has_core_parent.add(b_id)
        elif b_id in core_switch_ids and a_id in access_switch_ids:
            access_sw_has_core_parent.add(a_id)

    # ── Pass 1: register explicit vlan properties first ──────────────
    # Do this before any inference so the inference strategies can see
    # all "taken" VLANs when they run in pass 2.
    for node in topology.get("nodes", []):
        nid = node.get("node_id", "")
        if nid not in access_switch_ids or nid not in access_sw_has_core_parent:
            continue
        explicit_vlan = node.get("properties", {}).get("vlan", 0)
        if explicit_vlan and 1 <= int(explicit_vlan) <= 4094:
            vid = int(explicit_vlan)
            access_switch_vlan[nid] = vid
            used_vlans.add(vid)

    # ── Pass 2: infer VLANs for switches without an explicit property ─
    for node in topology.get("nodes", []):
        nid = node.get("node_id", "")
        if nid not in access_switch_ids:
            continue
        sw_name = node.get("name", nid)
        access_switch_name_map[nid] = sw_name

        if nid not in access_sw_has_core_parent:
            # Directly router-connected switch — flat/untagged, no VLAN
            access_switch_vlan[nid] = 0
            continue

        if nid in access_switch_vlan:
            # Already assigned from pass 1 (explicit property)
            continue

        vid = _infer_vlan_for_access_switch(sw_name, vlan_counter, used_vlans)
        access_switch_vlan[nid] = vid
        used_vlans.add(vid)     # register immediately so the next switch sees it

    logger.debug("Access switch VLAN assignments: %s", access_switch_vlan)

    # ── Build a lookup: access_switch_id → router segment base key ───
    # For each access switch, find which router interface its core switch
    # connects to.  This is the "base" segment key; VLAN ID is appended
    # to produce the final per-access-switch segment key.
    access_sw_router_key: Dict[str, str] = {}
    for sw_id in access_switch_ids:
        base_key = _find_router_segment_key_vlan(
            sw_id, links, node_map, concentrator_ids, core_switch_ids, find
        )
        access_sw_router_key[sw_id] = base_key

    # ── Assign segment keys to every link ────────────────────────────
    link_segment_keys: List[str] = []
    # Also track which access switch each link belongs to (for Segment metadata)
    link_access_sw: List[Optional[str]] = []

    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            link_segment_keys.append("")
            link_access_sw.append(None)
            continue

        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        a_is_router = a_type in L3_ROUTER_TYPES
        b_is_router = b_type in L3_ROUTER_TYPES
        a_is_conc = a_type in L2_CONCENTRATOR_TYPES
        b_is_conc = b_type in L2_CONCENTRATOR_TYPES
        a_is_access = a_id in access_switch_ids
        b_is_access = b_id in access_switch_ids
        a_is_core = a_id in core_switch_ids
        b_is_core = b_id in core_switch_ids

        assigned_access_sw: Optional[str] = None

        if a_is_router and b_is_router:
            # True point-to-point between two routers
            key = f"p2p:{a_id}:{eps[0].get('adapter_number',0)}:{eps[0].get('port_number',0)}"

        elif a_is_router and b_is_core:
            # Router ↔ core switch: the 802.1Q trunk link itself.
            # This link is not a routed segment — it carries tagged frames for
            # multiple VLANs.  Key it to the physical router interface but mark
            # it as a trunk so the brief can describe it correctly.
            resolved = resolve_port_name(
                node_map[a_id],
                eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0),
            )
            key = f"trunk:{a_id}:{resolved}"

        elif b_is_router and a_is_core:
            resolved = resolve_port_name(
                node_map[b_id],
                eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0),
            )
            key = f"trunk:{b_id}:{resolved}"

        elif a_is_router:
            # Router directly connected to an access switch (no core sw) or host
            resolved = resolve_port_name(
                node_map[a_id],
                eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0),
            )
            if b_is_access:
                vlan = access_switch_vlan.get(b_id, 0)
                key = f"router:{a_id}:{resolved}:vlan:{vlan}"
                assigned_access_sw = b_id
            else:
                key = f"router:{a_id}:{resolved}:vlan:0"

        elif b_is_router:
            resolved = resolve_port_name(
                node_map[b_id],
                eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0),
            )
            if a_is_access:
                vlan = access_switch_vlan.get(a_id, 0)
                key = f"router:{b_id}:{resolved}:vlan:{vlan}"
                assigned_access_sw = a_id
            else:
                key = f"router:{b_id}:{resolved}:vlan:0"

        elif a_is_core and b_is_access:
            # Core switch ↔ access switch: classify under the access switch's
            # VLAN segment so this uplink appears in the right segment in the brief
            base = access_sw_router_key.get(b_id, f"switch_group:{find(b_id)}")
            vlan = access_switch_vlan.get(b_id, 0)
            key = f"{base}:vlan:{vlan}" if ":vlan:" not in base else base
            assigned_access_sw = b_id

        elif b_is_core and a_is_access:
            base = access_sw_router_key.get(a_id, f"switch_group:{find(a_id)}")
            vlan = access_switch_vlan.get(a_id, 0)
            key = f"{base}:vlan:{vlan}" if ":vlan:" not in base else base
            assigned_access_sw = a_id

        elif a_is_access:
            # Access switch ↔ host
            base = access_sw_router_key.get(a_id, f"switch_group:{find(a_id)}")
            vlan = access_switch_vlan.get(a_id, 0)
            key = f"{base}:vlan:{vlan}" if ":vlan:" not in base else base
            assigned_access_sw = a_id

        elif b_is_access:
            base = access_sw_router_key.get(b_id, f"switch_group:{find(b_id)}")
            vlan = access_switch_vlan.get(b_id, 0)
            key = f"{base}:vlan:{vlan}" if ":vlan:" not in base else base
            assigned_access_sw = b_id

        elif a_is_conc and b_is_conc:
            # Two core switches or two hub/switch concentrators with no access sw
            root = find(a_id)
            key = f"switch_group:{root}"

        elif a_is_conc:
            key = _find_router_segment_key_vlan(
                a_id, links, node_map, concentrator_ids, core_switch_ids, find
            )

        elif b_is_conc:
            key = _find_router_segment_key_vlan(
                b_id, links, node_map, concentrator_ids, core_switch_ids, find
            )

        else:
            # Host-to-host (schema validator should have caught this)
            key = f"p2p:{a_id}:{eps[0].get('adapter_number',0)}:{eps[0].get('port_number',0)}"

        link_segment_keys.append(key)
        link_access_sw.append(assigned_access_sw)

    # ── Group links by segment key ────────────────────────────────────
    grouped: Dict[str, List[dict]] = {}
    grouped_access_sw: Dict[str, Optional[str]] = {}  # key → access_switch_id
    for i, key in enumerate(link_segment_keys):
        if key:
            grouped.setdefault(key, []).append(links[i])
            # Record whichever access switch we found for this key
            if link_access_sw[i] is not None:
                grouped_access_sw[key] = link_access_sw[i]

    # ── Build Segment objects ─────────────────────────────────────────
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

        # Determine segment type and VLAN metadata
        if key.startswith("p2p:"):
            seg_type = "point-to-point"
            vlan_id = 0
            sw_name = ""
        elif key.startswith("trunk:"):
            seg_type = "trunk"
            vlan_id = 0
            sw_name = ""
        else:
            seg_type = "multi-access"
            # Extract VLAN id from key suffix ":vlan:N"
            m = re.search(r":vlan:(\d+)$", key)
            vlan_id = int(m.group(1)) if m else 0
            # Look up the human name of the access switch for this segment
            access_sw_id = grouped_access_sw.get(key)
            sw_name = access_switch_name_map.get(access_sw_id, "") if access_sw_id else ""

        segments.append(Segment(
            segment_id=seg_id,
            seg_type=seg_type,
            link_pairs=pair_list,
            concentrator_ids=conc_ids,
            vlan_id=vlan_id,
            access_switch_name=sw_name,
        ))
        seg_id += 1

    return segments


def _find_router_segment_key_vlan(
    switch_id: str,
    all_links: List[dict],
    node_map: Dict[str, dict],
    concentrator_ids: Set[str],
    core_switch_ids: Set[str],
    find_func,
) -> str:
    """Find the router interface that this switch's L2 domain connects to.

    Traverses the switch group (via union-find) to locate a router uplink.
    Returns a "router:R_ID:iface_name" base key (without the :vlan: suffix —
    callers append that themselves so the same base key can be shared across
    all access switches that connect to the same router interface).

    If no router uplink is found, falls back to a switch_group key.
    """
    for link in all_links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id = eps[0].get("node_id", "")
        b_id = eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

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


def _find_router_iface_in_segment(seg: "Segment") -> str:
    """Return the router's canonical interface name if the router endpoint
    appears directly in this segment's link_pairs.

    This works for simple flat topologies (Router ↔ SW ↔ hosts) where the
    router IS present in the multi-access segment.  For Router-on-a-Stick
    topologies the router link lives in the *trunk* segment, not in the VLAN
    multi-access segments — use _extract_trunk_router_iface() for those.

    Returns an empty string when no router endpoint is found.
    """
    for ep_a, ep_b in seg.link_pairs:
        for ep in (ep_a, ep_b):
            if ep.node_type in L3_ROUTER_TYPES:
                return ep.canonical_name
    return ""


def _extract_trunk_router_iface(segments: List["Segment"]) -> str:
    """Scan all segments for a trunk segment and return the router's physical
    interface name from that trunk link.

    In a Router-on-a-Stick topology the router ↔ core-switch link is classified
    as seg_type='trunk'.  Its router endpoint carries the physical interface name
    (e.g. "FastEthernet0/0") that is the parent for all 802.1Q sub-interfaces.

    This is the correct source for the sub-interface hint in VLAN segments,
    because the router never appears in those segments' link_pairs directly —
    its physical cable terminates at the core switch, not at the access switches.

    Returns an empty string if no trunk segment is found (flat topology).
    """
    for seg in segments:
        if seg.seg_type != "trunk":
            continue
        for ep_a, ep_b in seg.link_pairs:
            for ep in (ep_a, ep_b):
                if ep.node_type in L3_ROUTER_TYPES:
                    return ep.canonical_name
    return ""



# ── GNS3 port type constants ─────────────────────────────────────────────────
# Values accepted by the GNS3 ethernet_switch ports_mapping "type" field.
_PM_ACCESS = "access"   # strips VLAN tags; forwards only frames for one VLAN
_PM_DOT1Q  = "dot1q"   # carries 802.1Q tagged frames for multiple VLANs


def patch_switch_ports_mapping(
    topology: dict,
    segments: List[Segment],
    node_map: Dict[str, dict],
) -> Dict[str, List[Dict[str, int]]]:
    """Rewrite GNS3 ethernet_switch ports_mapping to match the RoaS VLAN plan.

    This function fixes the critical GNS3 deployment bug where every switch
    port starts as ``"type": "access", "vlan": 1``.  With that default, the
    GNS3 software switch strips the 802.1Q tags that the router sends, so
    tagged frames never reach the access switches and the network is dead.

    Decision table (derived purely from the link graph and segment metadata —
    no heuristics, no name matching):

    ┌─────────────────────────────────────────────┬──────────┬────────────┐
    │ Link                                        │ type     │ vlan       │
    ├─────────────────────────────────────────────┼──────────┼────────────┤
    │ Router  ↔  core switch  (trunk)             │ dot1q    │ (ignored)  │
    │ Core SW ↔  access switch (inter-switch)     │ dot1q    │ (ignored)  │
    │ Access SW uplink port   (to core)           │ dot1q    │ (ignored)  │
    │ Access SW host port     (to VPCS/host)      │ access   │ segment ID │
    │ Unlinked / unused port                      │ (unchanged)            │
    └─────────────────────────────────────────────┴──────────┴────────────┘

    For ``dot1q`` ports the ``vlan`` field is set to 0; GNS3 ignores the vlan
    field for dot1q ports but we zero it explicitly to avoid confusing diffs.

    Parameters
    ----------
    topology:
        The Phase 1 / Phase 2 topology dict (mutated in place).
    segments:
        The Segment list produced by ``build_segments()`` for this topology.
    node_map:
        The node_id → node dict index produced by ``_build_node_map()``.

    Returns
    -------
    Dict[str, List[Dict]]
        A log of every change made, keyed by node_id.  Each entry is a list
        of ``{"port": N, "old_type": "...", "new_type": "...", "vlan": V}``
        dicts — useful for audit logging and tests.
    """
    # ── Step 1: build a (node_id, port_number) → action map ──────────────────
    # action = ("dot1q", 0) | ("access", vlan_id)
    #
    # We drive this entirely from the links array and the segment VLAN map —
    # no name heuristics here.  Each link tells us the port numbers on both
    # endpoints; the segment map tells us which VLAN those ports belong to.
    #
    # Build the access-switch → VLAN lookup from the segments list so we
    # don't have to re-run the VLAN assignment logic.
    access_sw_vlan: Dict[str, int] = {}   # node_id → assigned vlan_id
    for seg in segments:
        if seg.vlan_id > 0:
            for sw_id in seg.concentrator_ids:
                if sw_id not in access_sw_vlan:
                    access_sw_vlan[sw_id] = seg.vlan_id

    # Identify core and access switch sets from node_map + segment data
    # (mirrors _identify_core_switches without re-running it)
    core_sw_ids = _identify_core_switches(topology, node_map)

    # (node_id, port_number) → ("dot1q"|"access", vlan_id)
    PortAction = Tuple[str, int]
    port_actions: Dict[Tuple[str, int], PortAction] = {}

    links = topology.get("links", [])
    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id  = eps[0].get("node_id", "")
        a_port = eps[0].get("port_number", 0)
        b_id  = eps[1].get("node_id", "")
        b_port = eps[1].get("port_number", 0)
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        a_is_sw   = a_type in L2_CONCENTRATOR_TYPES
        b_is_sw   = b_type in L2_CONCENTRATOR_TYPES
        a_is_rtr  = a_type in L3_ROUTER_TYPES
        b_is_rtr  = b_type in L3_ROUTER_TYPES
        a_is_core = a_id in core_sw_ids
        b_is_core = b_id in core_sw_ids
        a_is_acc  = a_is_sw and not a_is_core
        b_is_acc  = b_is_sw and not b_is_core

        if a_is_rtr and b_is_sw:
            # Router → any switch port: trunk on the switch side
            port_actions[(b_id, b_port)] = (_PM_DOT1Q, 0)

        elif b_is_rtr and a_is_sw:
            # Any switch → router: trunk on the switch side
            port_actions[(a_id, a_port)] = (_PM_DOT1Q, 0)

        elif a_is_core and b_is_sw:
            # Core → any switch (access or another core): both ends dot1q
            port_actions[(a_id, a_port)] = (_PM_DOT1Q, 0)
            port_actions[(b_id, b_port)] = (_PM_DOT1Q, 0)

        elif b_is_core and a_is_sw:
            # Any switch → core: both ends dot1q
            port_actions[(a_id, a_port)] = (_PM_DOT1Q, 0)
            port_actions[(b_id, b_port)] = (_PM_DOT1Q, 0)

        elif a_is_acc and not b_is_sw:
            # Access switch → host: access port with the segment's VLAN
            vlan = access_sw_vlan.get(a_id, 1)
            port_actions[(a_id, a_port)] = (_PM_ACCESS, vlan)

        elif b_is_acc and not a_is_sw:
            # Host → access switch: access port with the segment's VLAN
            vlan = access_sw_vlan.get(b_id, 1)
            port_actions[(b_id, b_port)] = (_PM_ACCESS, vlan)

    logger.debug(
        "patch_switch_ports_mapping: %d port actions computed", len(port_actions)
    )

    # ── Step 2: apply actions to ports_mapping arrays ─────────────────────────
    change_log: Dict[str, List[dict]] = {}

    for node in topology.get("nodes", []):
        nid = node.get("node_id", "")
        if node.get("node_type") not in L2_CONCENTRATOR_TYPES:
            continue

        props = node.setdefault("properties", {})
        pm = props.get("ports_mapping")
        if not pm:
            logger.debug("Node %s: no ports_mapping, skipping", nid)
            continue

        node_changes: List[dict] = []

        for port_entry in pm:
            pnum = port_entry.get("port_number", -1)
            action = port_actions.get((nid, pnum))
            if action is None:
                continue  # unlinked port — leave unchanged

            new_type, new_vlan = action
            old_type = port_entry.get("type", "")
            old_vlan = port_entry.get("vlan", 1)

            if new_type == old_type and (new_type == _PM_DOT1Q or new_vlan == old_vlan):
                continue  # already correct — no-op

            port_entry["type"] = new_type
            if new_type == _PM_DOT1Q:
                port_entry["vlan"] = 0   # explicit zero for dot1q ports
            else:
                port_entry["vlan"] = new_vlan

            node_changes.append({
                "port":     pnum,
                "old_type": old_type,
                "old_vlan": old_vlan,
                "new_type": new_type,
                "new_vlan": port_entry["vlan"],
            })
            logger.debug(
                "  %s port %d: %s/vlan=%d → %s/vlan=%d",
                nid, pnum, old_type, old_vlan, new_type, port_entry["vlan"],
            )

        if node_changes:
            change_log[nid] = node_changes
            logger.info(
                "patch_switch_ports_mapping: %s — %d port(s) updated",
                node.get("name", nid), len(node_changes),
            )

    return change_log


def generate_brief(topology: dict) -> str:
    """Generate the human-readable Configuration Brief from a Phase 1 topology.

    This is the core function. Returns a formatted string ready to be
    injected into the LLM system prompt for Phase 2 config generation.

    Side-effect: mutates ``topology`` in place to fix GNS3 switch
    ``ports_mapping`` entries (dot1q trunk ports and correct access VLAN IDs).
    This is intentional — the corrected topology is what gets deployed.
    """
    node_map = _build_node_map(topology)
    segments = build_segments(topology, node_map)

    # ── Patch switch ports_mapping BEFORE rendering the brief ────────
    # This must run here (after segments are known, before deployment)
    # because the VLAN IDs assigned by build_segments are the ground truth
    # that the ports_mapping must reflect.  Running it here ensures the
    # topology object the caller holds is already deployment-ready.
    patch_log = patch_switch_ports_mapping(topology, segments, node_map)
    if patch_log:
        logger.info(
            "ports_mapping patched for %d switch(es): %s",
            len(patch_log),
            {nid: len(changes) for nid, changes in patch_log.items()},
        )

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

    # Pre-compute the router's physical interface name from the trunk segment
    # (if one exists).  This is the parent interface for all 802.1Q
    # sub-interfaces in a Router-on-a-Stick topology.
    #
    # WHY HERE and not inside the loop: the trunk segment may appear at any
    # position in `segments` relative to the VLAN multi-access segments.
    # Pre-computing it once ensures the hint is available for every VLAN
    # segment regardless of iteration order.
    trunk_router_iface: str = _extract_trunk_router_iface(segments)

    for seg in segments:
        hosts = _collect_segment_hosts(seg)
        host_count = len(hosts)

        if seg.seg_type == "trunk":
            # The Router-Core-SW 802.1Q trunk: not a routed segment itself,
            # but we surface it so the LLM knows the physical interface to use
            # as the sub-interface parent.
            lines.append(f"  Segment {seg.segment_id} (802.1Q trunk — NOT a routed segment):")
            for ep_a, ep_b in seg.link_pairs:
                lines.append(
                    f"    {ep_a.node_id:6s} {ep_a.canonical_name:20s}"
                    f"  <->  {ep_b.node_id} {ep_b.canonical_name}"
                )
            lines.append(
                f"    → Configure 802.1Q sub-interfaces on the router side "
                f"of this link, one per VLAN below."
            )

        elif seg.seg_type == "multi-access":
            vlan_label = f"VLAN {seg.vlan_id}" if seg.vlan_id else "untagged"
            sw_label = f", access-sw: {seg.access_switch_name}" if seg.access_switch_name else ""
            lines.append(
                f"  Segment {seg.segment_id} "
                f"(multi-access, {vlan_label}{sw_label}, {host_count} host(s)):"
            )
            if seg.vlan_id:
                # Resolve the parent physical interface for the sub-interface hint.
                # Priority:
                #   1. trunk_router_iface  — set when a trunk segment exists
                #      (RoaS topology: router is NOT in this segment's link_pairs)
                #   2. _find_router_iface_in_segment — flat topology fallback
                #      (router IS directly connected to this switch segment)
                parent_iface = trunk_router_iface or _find_router_iface_in_segment(seg)
                if parent_iface:
                    lines.append(
                        f"    → Router sub-interface: {parent_iface}.{seg.vlan_id} "
                        f"(encapsulation dot1Q {seg.vlan_id})"
                    )
                else:
                    # No router interface found anywhere — emit a generic hint
                    # so the LLM still knows to create a sub-interface
                    lines.append(
                        f"    → Router sub-interface: <parent-iface>.{seg.vlan_id} "
                        f"(encapsulation dot1Q {seg.vlan_id})"
                    )
            for ep_a, ep_b in seg.link_pairs:
                if ep_a.node_type in L2_CONCENTRATOR_TYPES:
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
    lines.append("  1. Assign one unique subnet per segment (no overlaps).")
    lines.append("  2. Use /24 for multi-access segments, /30 for point-to-point.")
    lines.append("  3. For each router: generate a full Cisco IOS startup config.")
    lines.append("     - If VLAN segments exist: configure 802.1Q sub-interfaces")
    lines.append("       on the trunk physical interface, one per VLAN.")
    lines.append("       Use the EXACT sub-interface numbers shown above (e.g., Fa0/0.10).")
    lines.append("     - Each VLAN segment's subnet must be assigned to its sub-interface.")
    lines.append("  4. For each VPCS host: generate a startup_script with 'ip' command.")
    lines.append("     The gateway IP MUST be the router's sub-interface IP for that VLAN.")
    lines.append("  5. For each Docker container: set 'environment' and 'start_command'.")
    lines.append("  6. Skip switches, hubs, and NAT nodes — they need no IP config.")
    lines.append(
        "  7. Include routing protocols (OSPF or static) for multi-segment routers."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

def build_configuration_brief(phase1_json_path: str) -> Tuple[str, Dict[str, Any]]:
    """Load a Phase 1 JSON file, patch its switch ports_mapping, and return
    both the Configuration Brief string and the mutated topology dict.

    This is the main entry point for context_builder.py.

    WHY A TUPLE: ``generate_brief`` calls ``patch_switch_ports_mapping``
    internally, which rewrites every GNS3 ethernet_switch port from the
    default ``"type": "access", "vlan": 1`` to the correct dot1q/access
    settings derived from the VLAN segment plan.  Those mutations live on
    the in-memory ``topology`` dict.  If the caller only received the brief
    string, the patched ports_mapping would be silently discarded and the
    unpatched disk copy would flow into ``safe_merge_configs`` — meaning the
    deployed switches would still have all ports as ``access/vlan 1`` and
    every 802.1Q tagged frame from the router would be dropped immediately.

    The caller (``config_agent.run_phase2``) MUST use the returned
    ``mutated_topology`` as the base dict for ``safe_merge_configs``, NOT
    the raw JSON re-read from disk.

    Parameters
    ----------
    phase1_json_path : str
        Path to the Phase 1 output JSON (e.g. ``output/_topology.json``)

    Returns
    -------
    Tuple[str, Dict[str, Any]]
        ``(brief, mutated_topology)`` where:
        - ``brief`` is the formatted Configuration Brief string ready to
          inject into the LLM system prompt for Phase 2 config generation.
        - ``mutated_topology`` is the full project dict (``{"name": ...,
          "topology": {...}}``) with switch ``ports_mapping`` already patched.
          Pass this directly to ``safe_merge_configs`` as ``phase1_dict``.
    """
    path = Path(phase1_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Phase 1 JSON not found: {phase1_json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Unwrap from the GNS3Project structure  { "name": ..., "topology": {…} }
    # generate_brief mutates topology in place (patch_switch_ports_mapping).
    # We hold a reference to `data` so those mutations are visible through it.
    topology = data.get("topology", data)

    brief = generate_brief(topology)   # ← patches topology.nodes[*].properties.ports_mapping
    logger.info("Configuration brief generated (%d chars)", len(brief))

    # Return the brief AND the mutated project dict.
    # `data` now contains the patched ports_mapping because `topology` is a
    # reference into `data`, not a copy.
    return brief, data


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
