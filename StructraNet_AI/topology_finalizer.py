"""
topology_finalizer.py — VLAN-Aware Switch Port Patcher for Structranet AI

Runs AFTER hw_config.inject_hardware_config() and BEFORE Phase 2 config
generation.  Its sole job is to rewrite the `ports_mapping` entries on
ethernet_switch nodes so that:

  • The port connected to the router (or core switch) is set to trunk / dot1q
  • The ports connected to access-segment endpoints (hosts, other switches)
    are set to the correct VLAN id for that segment

Without this step every switch port ships with type="access", vlan=1, and
all 802.1Q tagged frames from the router are silently dropped at the first
switch, making inter-VLAN routing completely non-functional.

Design contract
───────────────
  apply_switch_port_patches(project_dict) → project_dict (mutated in-place)

  The function uses context_builder.build_segments() to recompute the VLAN
  plan (same algorithm the brief uses, single source of truth).  It then
  iterates over every ethernet_switch node and rewrites each port entry in
  ports_mapping to match the VLAN plan.

  Important: this mutates the dict in-place AND returns it, so callers can
  either use the return value or rely on the mutation — both are safe.

  Links from the topology are used to map port_number → (node_id, segment).
  The port_number stored in link endpoints is 0-based (GNS3 server rewrites
  to 0-based internally; hw_config._make_switch_port now generates 0-based),
  so we match on port_number directly.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from hw_config import L2_CONCENTRATOR_TYPES, L3_ROUTER_TYPES

logger = logging.getLogger("structranet.topology_finalizer")

# Inline port-type constants — avoid circular import with hw_config
_SWITCH_TYPE = "ethernet_switch"


# ═══════════════════════════════════════════════════════════════════════════════
#  Port-type helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_trunk_port(index: int) -> Dict[str, Any]:
    """A dot1q trunk port.

    "vlan" sets the native VLAN (PVID): untagged frames arriving on this port
    are assigned VLAN 1; tagged frames pass through as-is.  For Router-on-a-Stick
    the router sends only tagged sub-interface frames, so native VLAN 1 is safe.
    port_number is 0-based — GNS3 server renumbers to 0-based regardless.
    """
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
        "type": "dot1q",
        "vlan": 1,         # native VLAN on the trunk
        "ethertype": "",
    }


def _make_access_port(index: int, vlan: int) -> Dict[str, Any]:
    """An access port assigned to a specific VLAN. port_number is 0-based."""
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
        "type": "access",
        "vlan": max(vlan, 1),   # vlan 0 is invalid; fall back to 1
        "ethertype": "",
    }


def _make_default_access_port(index: int) -> Dict[str, Any]:
    """Default access port when we have no VLAN context (flat networks). port_number is 0-based."""
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
        "type": "access",
        "vlan": 1,
        "ethertype": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  VLAN plan builder (thin wrapper around context_builder.build_segments)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_vlan_plan(topology: dict) -> tuple[Dict[str, int], Set[str]]:
    """Return ({access_switch_id: vlan_id}, core_switch_ids) for the topology.

    Delegates entirely to context_builder so the VLAN assignment algorithm
    has a single source of truth.

    Returns a tuple so apply_switch_port_patches can handle core switches
    separately without calling _identify_core_switches a second time.

    BUG FIX: The previous version iterated seg.concentrator_ids for every
    VLAN segment and assigned the VLAN to every switch it found there,
    including core switches.  Core switches appear in VLAN segments because
    the Core-SW ↔ F1-SW link is keyed to F1's VLAN segment, placing Core-SW
    in that segment's concentrator_ids.  Assigning VLAN 10 to the Core-SW
    and then patching all its ports as access/vlan=10 is wrong — the core
    switch carries ALL VLANs and every one of its linked ports must be dot1q
    trunk.  The fix is to exclude core switches from the VLAN plan here and
    handle them separately in _patch_core_switch_ports_mapping.
    """
    try:
        from context_builder import (
            build_segments, _build_node_map, _identify_core_switches,
        )
    except ImportError as e:
        logger.error("Cannot import context_builder: %s", e)
        return {}, set()

    node_map = _build_node_map(topology)
    segments = build_segments(topology, node_map)
    core_switch_ids = _identify_core_switches(topology, node_map)

    vlan_plan: Dict[str, int] = {}
    for seg in segments:
        if seg.vlan_id <= 0:
            continue
        for sw_id in seg.concentrator_ids:
            # Skip core switches — they are handled separately
            if sw_id in core_switch_ids:
                continue
            node = node_map.get(sw_id, {})
            if node.get("node_type") == _SWITCH_TYPE:
                if sw_id in vlan_plan and vlan_plan[sw_id] != seg.vlan_id:
                    logger.warning(
                        "Access switch '%s' appears in multiple VLAN segments "
                        "(%d and %d) — keeping first assignment",
                        sw_id, vlan_plan[sw_id], seg.vlan_id,
                    )
                else:
                    vlan_plan[sw_id] = seg.vlan_id

    logger.debug("VLAN plan (access switches only): %s", vlan_plan)
    logger.debug("Core switches (all-trunk): %s", core_switch_ids)
    return vlan_plan, core_switch_ids


# ═══════════════════════════════════════════════════════════════════════════════
#  Core switcher — per-switch ports_mapping rewrite
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_switch_ports(
    switch_id: str,
    links: List[dict],
    node_map: Dict[str, dict],
    vlan_id: int,
) -> Dict[int, str]:
    """For each port_number used on this switch, determine its role.

    Returns {port_number: role} where role is "trunk" or "access".

    A port is "trunk" if the neighbour is a router (L3), another switch (L2
    concentrator) or a core switch.  Everything else is "access".
    """
    role: Dict[int, str] = {}

    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue

        sw_ep: Optional[dict] = None
        other_ep: Optional[dict] = None

        for ep in eps:
            if ep.get("node_id") == switch_id:
                sw_ep = ep
            else:
                other_ep = ep

        if sw_ep is None or other_ep is None:
            continue

        port_num = sw_ep.get("port_number", 0)
        other_id = other_ep.get("node_id", "")
        other_type = node_map.get(other_id, {}).get("node_type", "")

        if other_type in L3_ROUTER_TYPES or other_type in L2_CONCENTRATOR_TYPES:
            role[port_num] = "trunk"
        else:
            role[port_num] = "access"

    return role


def _patch_switch_ports_mapping(
    switch_node: dict,
    links: List[dict],
    node_map: Dict[str, dict],
    vlan_id: int,
) -> None:
    """Rewrite ports_mapping on a single ethernet_switch node in-place.

    For VLAN-participating switches (vlan_id > 0):
      • Ports connected to routers / core switches → trunk (dot1q, native vlan 1)
      • Ports connected to hosts / access switches  → access, vlan=vlan_id

    For flat-network switches (vlan_id == 0):
      • All ports stay access, vlan=1 (no change needed — this is the default)
    """
    properties = switch_node.get("properties", {})
    ports_mapping: List[dict] = properties.get("ports_mapping")

    if not ports_mapping:
        logger.debug(
            "Switch '%s' has no ports_mapping — skipping patch",
            switch_node.get("node_id"),
        )
        return

    if vlan_id <= 0:
        # Flat network: no VLAN patching required
        return

    port_roles = _classify_switch_ports(
        switch_node["node_id"], links, node_map, vlan_id,
    )

    patched: List[dict] = []
    for i, port in enumerate(ports_mapping):
        port_num = port.get("port_number", i)
        role = port_roles.get(port_num, "access")

        if role == "trunk":
            patched.append(_make_trunk_port(i))
        else:
            patched.append(_make_access_port(i, vlan_id))

    properties["ports_mapping"] = patched
    logger.info(
        "Switch '%s' (VLAN %d): patched %d ports — trunk=%d, access=%d",
        switch_node.get("node_id"), vlan_id,
        len(patched),
        sum(1 for p in patched if p["type"] == "dot1q"),
        sum(1 for p in patched if p["type"] == "access"),
    )


def _patch_core_switch_ports_mapping(
    switch_node: dict,
    links: List[dict],
    node_map: Dict[str, dict],
) -> None:
    """Rewrite ports_mapping on a core switch so every linked port is dot1q trunk.

    Core switches sit between the router and access switches and carry tagged
    frames for ALL VLANs simultaneously.  Every port that has a link must
    therefore be a dot1q trunk.  Unlinked ports stay as default access/vlan=1
    (GNS3 ignores them anyway).

    This is intentionally separate from _patch_switch_ports_mapping because
    core switches have no single VLAN — they need the same trunk type on both
    their router-facing port AND every access-switch-facing port.
    """
    properties = switch_node.get("properties", {})
    ports_mapping: List[dict] = properties.get("ports_mapping")

    if not ports_mapping:
        logger.debug(
            "Core switch '%s' has no ports_mapping — skipping patch",
            switch_node.get("node_id"),
        )
        return

    # Collect port_numbers that have active links on this switch
    linked_port_nums: Set[int] = set()
    sw_id = switch_node["node_id"]
    for link in links:
        for ep in link.get("nodes", []):
            if ep.get("node_id") == sw_id:
                linked_port_nums.add(ep.get("port_number", 0))

    patched: List[dict] = []
    for i, port in enumerate(ports_mapping):
        port_num = port.get("port_number", i)
        if port_num in linked_port_nums:
            patched.append(_make_trunk_port(i))
        else:
            patched.append(_make_default_access_port(i))

    properties["ports_mapping"] = patched
    trunk_count = sum(1 for p in patched if p["type"] == "dot1q")
    logger.info(
        "Core switch '%s': patched %d ports — %d trunk (dot1q), %d unlinked (access/vlan=1)",
        sw_id, len(patched), trunk_count, len(patched) - trunk_count,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

def apply_switch_port_patches(project_dict: dict) -> dict:
    """Patch all ethernet_switch ports_mappings with correct VLAN assignments.

    Must be called AFTER hw_config.inject_hardware_config() (so that
    ports_mapping already exists on every switch node) and BEFORE
    context_builder.build_configuration_brief() or Phase 2 config generation
    (so the brief and configs see the correct trunk/access layout).

    Mutates project_dict in-place and also returns it for chaining:

        enriched = inject_hardware_config(raw)
        enriched = apply_switch_port_patches(enriched)

    Args:
        project_dict: Full GNS3Project dict with "name" + "topology" keys.

    Returns:
        The same dict with switch ports_mappings patched.
    """
    topo = project_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    # Build node_map for neighbour-type lookups
    node_map: Dict[str, dict] = {n["node_id"]: n for n in nodes if "node_id" in n}

    # Find all ethernet_switch nodes
    switch_nodes = [n for n in nodes if n.get("node_type") == _SWITCH_TYPE]
    if not switch_nodes:
        logger.debug("No ethernet_switch nodes found — nothing to patch")
        return project_dict

    # Build VLAN plan and core switch set once for the whole topology.
    # _build_vlan_plan now returns a tuple and explicitly excludes core switches
    # from the vlan_plan so they are not patched as single-VLAN access switches.
    vlan_plan, core_switch_ids = _build_vlan_plan(topo)

    access_patched = 0
    core_patched = 0

    for sw in switch_nodes:
        sw_id = sw.get("node_id", "")

        if sw_id in core_switch_ids:
            # Core switches carry ALL VLANs — every linked port must be dot1q trunk.
            _patch_core_switch_ports_mapping(sw, links, node_map)
            core_patched += 1
        else:
            # Access switches: trunk on the uplink port, access on host ports.
            vlan_id = vlan_plan.get(sw_id, 0)
            _patch_switch_ports_mapping(sw, links, node_map, vlan_id)
            if vlan_id > 0:
                access_patched += 1

    flat_count = len(switch_nodes) - core_patched - access_patched
    logger.info(
        "apply_switch_port_patches: %d switch(es) total — "
        "%d core (all-trunk), %d access (VLAN-assigned), %d flat (unchanged)",
        len(switch_nodes), core_patched, access_patched, flat_count,
    )
    return project_dict
