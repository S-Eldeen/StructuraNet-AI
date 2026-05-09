"""
hw_config.py — Hardware Configuration Injector for Structranet AI

Dynamically expands port/adapter counts for GNS3 nodes based on
the number of links the AI topology assigns to each node, preventing
the dreaded "No available port" deployment error.

Tier classification
───────────────────
  Tier 1 — Expandable via `properties` payload:
    dynamips / iou           → slot-based modules  (PA-8E, NM-4E, PA-4T+, NM-4T, …)
    qemu / docker / vbox     → `adapters` integer
      / vmware
    ethernet_switch / hub    → `ports_mapping` array

  Tier 2 — Hard-locked to 1 port (cannot expand):
    vpcs / traceng / nat     → constrain the LLM + Pydantic validator

  Tier 3 — Different paradigm (mappings, not port counts):
    frame_relay_switch       → `mappings` object
    atm_switch               → `mappings` object

Source: GNS3 server v2 source code (github.com/GNS3/gns3-server)
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("structranet.hw_config")


# ═══════════════════════════════════════════════════════════════════════════════
#  Constants — adapter limits, module mappings, built-in port counts
# ═══════════════════════════════════════════════════════════════════════════════

# ── Tier 1b: Max adapters per virtualisation engine ──────────────────────────
# Source: gns3server/schemas/{qemu,docker,virtualbox,vmware}_template.py
MAX_ADAPTERS: Dict[str, int] = {
    "qemu": 275,        # PCI bus limit (4 default + disks + adapters + bridges)
    "docker": 99,       # practical Docker limit
    "virtualbox": 8,    # safe default (PIIX3 chipset); ICH9 allows up to 36
    "vmware": 10,       # VMware VM hard limit
}

# ── Tier 1a: Dynamips Ethernet slot-module catalogue ──────────────────────────
# Each entry maps a platform identifier to the expansion module we inject.
#
#   module              — GNS3 module identifier written to the slotN property
#   ports_per_module    — how many Ethernet ports that module provides
#   first_configurable  — the first user-configurable slot (slot0 is built-in)
#   max_slots           — total configurable slots available on the platform
#
# Ref: gns3server/compute/dynamips/nodes/c7200.py et al.
DYNAMIPS_SLOT_MODULES: Dict[str, Dict[str, Any]] = {
    # ── c7200 series: Port Adapters ──
    "c7200": {
        "module": "PA-8E",             # 8 Ethernet ports per PA
        "ports_per_module": 8,
        "first_configurable": 1,       # slot0 is NPE built-in
        "max_slots": 6,                # slot1–slot6
    },
    # ── c3700 series: Network Modules ──
    "c3745": {
        "module": "NM-4E",             # 4 Ethernet ports per NM
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 4,                # slot1–slot4
    },
    "c3725": {
        "module": "NM-4E",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 2,                # slot1–slot2
    },
    # ── c3600 series: Network Modules ──
    "c3660": {
        "module": "NM-4E",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 6,
    },
    "c3640": {
        "module": "NM-4E",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 4,
    },
    "c3620": {
        "module": "NM-4E",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 2,
    },
    # ── c2600 / c1700 series ──
    "c2691": {
        "module": "NM-4E",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 1,                # slot1 only
    },
    "c2600": {
        "module": "NM-1E",            # 1 Ethernet port (limited platform)
        "ports_per_module": 1,
        "first_configurable": 1,
        "max_slots": 1,
    },
    "c1700": {
        "module": "NM-1E",
        "ports_per_module": 1,
        "first_configurable": 1,
        "max_slots": 1,
    },
}

# Fallback for any unrecognised Dynamips platform
DYNAMIPS_FALLBACK: Dict[str, Any] = {
    "module": "PA-8E",
    "ports_per_module": 8,
    "first_configurable": 1,
    "max_slots": 4,
}

# ── Tier 1a (serial): Dynamips serial module catalogue ────────────────────────
# Serial modules provide WAN interfaces (Serial0/0, Serial1/0, etc.)
# Used when link_type == "serial" in the topology.
#
# Same structure as DYNAMIPS_SLOT_MODULES but for serial (WAN) interfaces.
# Injected into slotN when the adapter's links are serial rather than Ethernet.
DYNAMIPS_SERIAL_MODULES: Dict[str, Dict[str, Any]] = {
    "c7200": {
        "module": "PA-4T+",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 6,
    },
    "c3745": {
        "module": "NM-4T",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 4,
    },
    "c3725": {
        "module": "NM-4T",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 2,
    },
    "c3660": {
        "module": "NM-4T",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 6,
    },
    "c3640": {
        "module": "NM-4T",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 4,
    },
    "c3620": {
        "module": "NM-1T",
        "ports_per_module": 1,
        "first_configurable": 1,
        "max_slots": 2,
    },
    "c2691": {
        "module": "NM-4T",
        "ports_per_module": 4,
        "first_configurable": 1,
        "max_slots": 1,
    },
    "c2600": {
        "module": "NM-1T",
        "ports_per_module": 1,
        "first_configurable": 1,
        "max_slots": 1,
    },
    "c1700": {
        "module": "NM-1T",
        "ports_per_module": 1,
        "first_configurable": 1,
        "max_slots": 1,
    },
}

DYNAMIPS_SERIAL_FALLBACK: Dict[str, Any] = {
    "module": "PA-4T+",
    "ports_per_module": 4,
    "first_configurable": 1,
    "max_slots": 4,
}

# Built-in Serial interfaces per Dynamips platform
# (Most platforms have 0 built-in serial — serial requires expansion modules)
DYNAMIPS_BUILTIN_SERIAL_PORTS: Dict[str, int] = {
    "c7200": 0,
    "c3745": 0,
    "c3725": 0,
    "c3660": 0,
    "c3640": 0,
    "c3620": 0,
    "c2691": 0,
    "c2600": 0,
    "c1700": 0,
}

# Serial module interface mapping for context_builder port resolution.
# Maps module name → {prefix, count} so resolve_port_name() can produce
# "Serial1/0" instead of "Ethernet1/0" for serial modules.
DYNAMIPS_SERIAL_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    "PA-4T+":  {"prefix": "Serial", "count": 4},
    "PA-8T":   {"prefix": "Serial", "count": 8},
    "NM-4T":   {"prefix": "Serial", "count": 4},
    "NM-1T":   {"prefix": "Serial", "count": 1},
}

# Built-in Ethernet interfaces that ship with each Dynamips platform
# (integrated ports on the NPE / motherboard, NOT in a slot).
# Conservative: under-estimating here is safe (extra slot is harmless);
#               over-estimating would be dangerous (missing a needed slot).
DYNAMIPS_BUILTIN_PORTS: Dict[str, int] = {
    "c7200": 1,   # FastEthernet0/0 on NPE
    "c3745": 2,   # FastEthernet0/0, FastEthernet0/1
    "c3725": 2,
    "c3660": 1,
    "c3640": 0,   # NM-only, no built-in Ethernet
    "c3620": 0,
    "c2691": 2,
    "c2600": 1,
    "c1700": 1,
}
DYNAMIPS_BUILTIN_DEFAULT = 1  # assume at least 1 if platform unknown

# ── Cross-catalogue module → ports_per_module lookup ─────────────────────────
# Used by _inject_dynamips_slots to determine the actual port count of an
# existing module when a slot is already occupied.  Combines both Ethernet
# and serial catalogues so we never miscount ports from a pre-set slot.
_MODULE_PORT_COUNT: Dict[str, int] = {}
for _plat, _cfg in DYNAMIPS_SLOT_MODULES.items():
    _MODULE_PORT_COUNT[_cfg["module"]] = _cfg["ports_per_module"]
for _plat, _cfg in DYNAMIPS_SERIAL_MODULES.items():
    _MODULE_PORT_COUNT[_cfg["module"]] = _cfg["ports_per_module"]
# Add entries from DYNAMIPS_SERIAL_MODULE_INTERFACES for completeness
for _mod, _info in DYNAMIPS_SERIAL_MODULE_INTERFACES.items():
    if _mod not in _MODULE_PORT_COUNT:
        _MODULE_PORT_COUNT[_mod] = _info["count"]

# ── Tier 1a: IOU slot configuration ─────────────────────────────────────────
IOU_L3_DEFAULT_MODULE = 2
IOU_L2_MODULE = "l2"
IOU_PORTS_PER_SLOT = 4
IOU_FIRST_CONFIGURABLE_SLOT = 1
IOU_MAX_SLOTS = 15
IOU_BUILTIN_PORTS = 4

# NOTE — cross-module contract:
# context_builder.py imports DYNAMIPS_BUILTIN_PORTS and IOU_PORTS_PER_SLOT
# from this module so there is a single source of truth for both constants.
# If you change the values above, context_builder.py inherits the change
# automatically without needing a separate edit.

# ── Tier 1c: Built-in ports for switch / hub ────────────────────────────────
SWITCH_HUB_DEFAULT_PORTS = 8

# ── Tier 2: Immutable single-port nodes ─────────────────────────────────────
IMMUTABLE_PORT_COUNT: Dict[str, int] = {
    "vpcs": 1,
    "traceng": 1,
    "nat": 1,
}
IMMUTABLE_TYPES = frozenset(IMMUTABLE_PORT_COUNT.keys())

# ── Tier 3: Mapping-based nodes ─────────────────────────────────────────────
MAPPING_BASED_TYPES = frozenset(["frame_relay_switch", "atm_switch"])


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper: count how many links attach to each node
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_link_stats(links: List[Dict[str, Any]]) -> tuple:
    """Single pass: link count, max port number, max adapter per node.

    Replaces three separate O(N) passes over the same links list with a
    single O(N) pass that computes all three stats simultaneously.

    Returns:
        (link_counts, max_port_map, max_adapters) tuple
    """
    counts: Dict[str, int] = {}
    max_ports: Dict[str, int] = {}
    max_adapters: Dict[str, int] = {}
    for link in links:
        for ep in link.get("nodes", []):
            nid = ep.get("node_id")
            if not nid:
                continue
            counts[nid] = counts.get(nid, 0) + 1
            port = ep.get("port_number", 0)
            max_ports[nid] = max(max_ports.get(nid, 0), port + 1)
            adapter = ep.get("adapter_number", 0)
            max_adapters[nid] = max(max_adapters.get(nid, 0), adapter)
    return counts, max_ports, max_adapters


def _count_links_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    counts, _, _ = _compute_link_stats(links)
    return counts


def _max_port_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    _, max_ports, _ = _compute_link_stats(links)
    return max_ports


def _max_adapter_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    _, _, max_adapters = _compute_link_stats(links)
    return max_adapters


def _count_links_per_node_by_type(links: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}
    for link in links:
        link_type = link.get("link_type", "ethernet")
        for ep in link.get("nodes", []):
            nid = ep.get("node_id")
            if nid:
                nc = counts.setdefault(nid, {"ethernet": 0, "serial": 0})
                lt = link_type if link_type in nc else "ethernet"
                nc[lt] += 1
    return counts


def _classify_adapter_link_types(links: List[Dict[str, Any]]) -> Dict[str, Dict[int, str]]:
    result: Dict[str, Dict[int, str]] = {}
    for link in links:
        link_type = link.get("link_type", "ethernet")
        for ep in link.get("nodes", []):
            nid = ep.get("node_id")
            adapter = ep.get("adapter_number", 0)
            if nid is not None:
                adapter_map = result.setdefault(nid, {})
                if adapter in adapter_map and adapter_map[adapter] != link_type:
                    logger.warning(
                        "Node %s adapter %d has mixed link types "
                        "(%s and %s) — using %s",
                        nid, adapter, adapter_map[adapter], link_type,
                        adapter_map[adapter],
                    )
                elif adapter not in adapter_map:
                    adapter_map[adapter] = link_type
    return result


def _max_adapter_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    max_adapters: Dict[str, int] = {}
    for link in links:
        for ep in link.get("nodes", []):
            nid = ep.get("node_id")
            adapter = ep.get("adapter_number", 0)
            if nid:
                current = max_adapters.get(nid, 0)
                max_adapters[nid] = max(current, adapter)
    return max_adapters


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 1a — Slot-based expansion  (dynamips, iou)
# ═══════════════════════════════════════════════════════════════════════════════

def _inject_slots(
    node: Dict[str, Any], required_ports: int, min_adapter_slots: int = 0,
    adapter_link_types: Optional[Dict[int, str]] = None,
    link_counts_by_type: Optional[Dict[str, int]] = None,
) -> None:
    properties = node.setdefault("properties", {})
    node_type = node["node_type"]

    if node_type == "dynamips":
        _inject_dynamips_slots(
            node, properties, required_ports, min_adapter_slots,
            adapter_link_types, link_counts_by_type,
        )
    elif node_type == "iou":
        _inject_iou_slots(node, properties, required_ports, min_adapter_slots)


def _identify_dynamips_platform(
    node: Dict[str, Any], properties: Dict[str, Any]
) -> str:
    platform = properties.get("platform")
    if platform:
        return str(platform).lower()

    template_name = node.get("template_name", "")
    if template_name:
        return str(template_name).lower()

    logger.debug(
        "Node %s: could not determine dynamips platform, defaulting to c7200",
        node.get("node_id"),
    )
    return "c7200"


def _inject_dynamips_slots(
    node: Dict[str, Any], properties: Dict[str, Any],
    required_ports: int, min_adapter_slots: int = 0,
    adapter_link_types: Optional[Dict[int, str]] = None,
    link_counts_by_type: Optional[Dict[str, int]] = None,
) -> None:
    """Expand Dynamips slots based on the platform's module catalogue.

    V2.0 BUG FIX: When a slot is already occupied, the port count is
    looked up from the _MODULE_PORT_COUNT cross-catalogue (which combines
    both Ethernet and serial module port counts), NOT from the would-be-
    injected module config.  This prevents miscounting when a pre-existing
    module has a different port count than the default for the current
    link_type.
    """
    platform = _identify_dynamips_platform(node, properties)
    eth_config = DYNAMIPS_SLOT_MODULES.get(platform, DYNAMIPS_FALLBACK)
    ser_config = DYNAMIPS_SERIAL_MODULES.get(platform, DYNAMIPS_SERIAL_FALLBACK)

    builtin_eth = DYNAMIPS_BUILTIN_PORTS.get(platform, DYNAMIPS_BUILTIN_DEFAULT)
    builtin_ser = DYNAMIPS_BUILTIN_SERIAL_PORTS.get(platform, 0)

    first_slot = eth_config["first_configurable"]
    max_slots = eth_config["max_slots"]
    last_slot = first_slot + max_slots - 1

    last_required_slot = min(min_adapter_slots, last_slot)

    alt = adapter_link_types or {}
    lt_counts = link_counts_by_type or {}

    eth_required = lt_counts.get("ethernet", required_ports)
    ser_required = lt_counts.get("serial", 0)

    eth_remaining = max(0, eth_required - builtin_eth)
    ser_remaining = max(0, ser_required - builtin_ser)

    if eth_remaining <= 0 and ser_remaining <= 0 and min_adapter_slots < first_slot:
        logger.debug(
            "Node %s (%s): built-in ports sufficient "
            "(eth_required=%d, ser_required=%d, builtin_eth=%d, builtin_ser=%d)",
            node.get("node_id"), platform,
            eth_required, ser_required, builtin_eth, builtin_ser,
        )
        return

    slots_injected = 0
    eth_covered = 0
    ser_covered = 0
    slot_idx = first_slot

    while slot_idx <= last_slot and (
        eth_covered < eth_remaining or ser_covered < ser_remaining
        or slot_idx <= last_required_slot
    ):
        slot_key = f"slot{slot_idx}"

        link_type = alt.get(slot_idx, "ethernet")
        if link_type == "serial":
            mod_config = ser_config
        else:
            mod_config = eth_config

        module_name = mod_config["module"]
        ports_per = mod_config["ports_per_module"]

        if slot_key in properties:
            # ── BUG FIX (V2.0): Use the ACTUAL existing module's port count ──
            # The old code used `ports_per` from mod_config (the module that
            # WOULD be injected), which was wrong when the existing module
            # has a different port count.  Now we look up the actual count
            # from the cross-catalogue _MODULE_PORT_COUNT.
            existing_module = properties[slot_key]
            actual_ports = _MODULE_PORT_COUNT.get(existing_module, ports_per)
            is_serial_module = existing_module in DYNAMIPS_SERIAL_MODULE_INTERFACES
            if is_serial_module:
                ser_covered += actual_ports
            else:
                eth_covered += actual_ports
            logger.debug(
                "Node %s (%s): %s already set to '%s', counting %d %s ports "
                "(actual_ports from catalogue, not from mod_config)",
                node.get("node_id"), platform,
                slot_key, existing_module, actual_ports,
                "serial" if is_serial_module else "Ethernet",
            )
        else:
            properties[slot_key] = module_name
            if link_type == "serial":
                ser_covered += ports_per
            else:
                eth_covered += ports_per
            slots_injected += 1
            logger.debug(
                "Node %s (%s): injected %s = %s (%d %s ports)",
                node.get("node_id"), platform,
                slot_key, module_name, ports_per,
                "serial" if link_type == "serial" else "Ethernet",
            )

        slot_idx += 1

    total_eth = builtin_eth + eth_covered
    total_ser = builtin_ser + ser_covered
    total_after = total_eth + total_ser
    logger.info(
        "Node %s (%s): %d links (eth=%d, ser=%d), max_adapter=%d → "
        "injected %d slot(s) → %d total ports (eth=%d + ser=%d)",
        node.get("node_id"), platform,
        required_ports, eth_required, ser_required, min_adapter_slots,
        slots_injected, total_after, total_eth, total_ser,
    )

    if total_eth < eth_required or total_ser < ser_required:
        logger.warning(
            "Node %s (%s): could only provide %d/%d Ethernet + %d/%d serial "
            "ports — platform slot limit reached! Topology may fail to deploy.",
            node.get("node_id"), platform,
            total_eth, eth_required, total_ser, ser_required,
        )


def _inject_iou_slots(
    node: Dict[str, Any], properties: Dict[str, Any],
    required_ports: int, min_adapter_slots: int = 0,
) -> None:
    is_l2 = "l2" in str(properties.get("slot0", "")).lower()
    module_value: Any = IOU_L2_MODULE if is_l2 else IOU_L3_DEFAULT_MODULE
    ports_per_slot = IOU_PORTS_PER_SLOT

    builtin = IOU_BUILTIN_PORTS
    remaining = max(0, required_ports - builtin)

    slots_for_ports = (remaining + ports_per_slot - 1) // ports_per_slot
    slots_for_adapters = max(0, min_adapter_slots - IOU_FIRST_CONFIGURABLE_SLOT + 1)
    slots_needed = max(slots_for_ports, slots_for_adapters)
    slots_needed = min(slots_needed, IOU_MAX_SLOTS)

    if slots_needed <= 0:
        logger.debug(
            "Node %s (iou): slot0 sufficient (%d required, %d in slot0)",
            node.get("node_id"), required_ports, builtin,
        )
        return

    slots_injected = 0
    for i in range(slots_needed):
        slot_key = f"slot{IOU_FIRST_CONFIGURABLE_SLOT + i}"
        if slot_key not in properties:
            properties[slot_key] = module_value
            slots_injected += 1
            logger.debug(
                "Node %s (iou): injected %s = %s",
                node.get("node_id"), slot_key, module_value,
            )
        else:
            logger.debug(
                "Node %s (iou): %s already set to '%s', skipping",
                node.get("node_id"), slot_key, properties[slot_key],
            )

    total_after = builtin + slots_needed * ports_per_slot
    logger.info(
        "Node %s (iou): %d links, max_adapter=%d → injected %d slot(s) → %d total ports",
        node.get("node_id"), required_ports, min_adapter_slots, slots_injected, total_after,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 1b — Adapter count expansion  (qemu, docker, virtualbox, vmware)
# ═══════════════════════════════════════════════════════════════════════════════

def _inject_adapter_count(node: Dict[str, Any], required_ports: int) -> None:
    node_type = node["node_type"]
    cap = MAX_ADAPTERS.get(node_type, 1)
    needed = min(required_ports, cap)

    properties = node.setdefault("properties", {})
    current = properties.get("adapters", 1)

    if needed <= current:
        logger.debug(
            "Node %s (%s): current adapters (%d) ≥ required (%d), no change",
            node.get("node_id"), node_type, current, needed,
        )
        return

    properties["adapters"] = needed
    logger.info(
        "Node %s (%s): %d links → adapters %d → %d (cap=%d)",
        node.get("node_id"), node_type, required_ports, current, needed, cap,
    )

    if required_ports > cap:
        logger.warning(
            "Node %s (%s): needs %d ports but %s max adapters is %d — "
            "topology may fail to deploy!",
            node.get("node_id"), node_type, required_ports, node_type, cap,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 1c — Ports mapping expansion  (ethernet_switch, ethernet_hub)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_switch_port(index: int) -> Dict[str, Any]:
    # GNS3 API v2 requires port_number >= 1 for ethernet_switch ports_mapping.
    # Name stays 0-based ("Ethernet0") to match GNS3 display convention,
    # but port_number is 1-based to satisfy the API schema constraint.
    return {
        "name": f"Ethernet{index}",
        "port_number": index + 1,
        "type": "access",
        "vlan": 1,
        "ethertype": "",
    }


def _make_hub_port(index: int) -> Dict[str, Any]:
    # GNS3 API v2 requires port_number >= 1 for ethernet_hub ports_mapping.
    # Same convention as _make_switch_port: name=0-based, port_number=1-based.
    return {
        "name": f"Ethernet{index}",
        "port_number": index + 1,
    }


def _inject_ports_mapping(node: Dict[str, Any], required_ports: int) -> None:
    node_type = node["node_type"]
    properties = node.setdefault("properties", {})

    target_ports = max(required_ports, SWITCH_HUB_DEFAULT_PORTS)

    existing_raw = properties.get("ports_mapping")

    if existing_raw is not None:
        existing: List[Dict[str, Any]] = list(existing_raw)

        # Normalize: GNS3 API v2 requires port_number >= 1.
        # If any existing entries have port_number < 1 (e.g., 0-indexed
        # from a previous version or AI-generated), renumber from 1.
        if any(p.get("port_number", 0) < 1 for p in existing):
            for i, port in enumerate(existing):
                port["port_number"] = i + 1
            logger.info(
                "Node %s (%s): normalized ports_mapping port_numbers "
                "to 1-based (GNS3 requires port_number >= 1)",
                node.get("node_id"), node_type,
            )

        # Normalize: GNS3 API v2 requires vlan >= 1 for ALL port types,
        # including dot1q/trunk. A vlan of 0 causes 400 Bad Request on PUT.
        # This is a defense-in-depth safety net — upstream code (context_builder)
        # should already set vlan >= 1, but we guard against any future source
        # of vlan: 0 here.
        if any(p.get("vlan", 0) < 1 for p in existing):
            for port in existing:
                if port.get("vlan", 0) < 1:
                    port["vlan"] = 1
            logger.info(
                "Node %s (%s): normalized ports_mapping vlan values "
                "to >= 1 (GNS3 requires vlan >= 1 for all port types)",
                node.get("node_id"), node_type,
            )

        current_count = len(existing)

        if target_ports <= current_count:
            logger.debug(
                "Node %s (%s): explicit ports_mapping has %d ports, "
                "%d target — no change",
                node.get("node_id"), node_type, current_count, target_ports,
            )
            return

        for i in range(current_count, target_ports):
            if node_type == "ethernet_switch":
                existing.append(_make_switch_port(i))
            elif node_type == "ethernet_hub":
                existing.append(_make_hub_port(i))

        properties["ports_mapping"] = existing
        logger.info(
            "Node %s (%s): %d links → ports_mapping expanded %d → %d "
            "(target=max(%d links, %d default))",
            node.get("node_id"), node_type,
            required_ports, current_count, len(existing),
            required_ports, SWITCH_HUB_DEFAULT_PORTS,
        )
    else:
        full_mapping: List[Dict[str, Any]] = []
        for i in range(target_ports):
            if node_type == "ethernet_switch":
                full_mapping.append(_make_switch_port(i))
            elif node_type == "ethernet_hub":
                full_mapping.append(_make_hub_port(i))

        properties["ports_mapping"] = full_mapping
        logger.info(
            "Node %s (%s): %d links → explicit ports_mapping created "
            "(%d ports = max(%d links, %d default))",
            node.get("node_id"), node_type,
            required_ports, len(full_mapping),
            required_ports, SWITCH_HUB_DEFAULT_PORTS,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Master Dispatcher
# ═══════════════════════════════════════════════════════════════════════════════

def inject_hardware_config(topology_dict: Dict[str, Any]) -> Dict[str, Any]:
    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    link_counts, max_port_map, max_adapters = _compute_link_stats(links)
    logger.info("Link counts per node: %s", link_counts)
    adapter_link_types = _classify_adapter_link_types(links)
    link_counts_by_type = _count_links_per_node_by_type(links)

    for node in nodes:
        node_id = node.get("node_id", "?")
        node_type = node.get("node_type", "")
        required = link_counts.get(node_id, 0)

        if required == 0:
            logger.debug("Node %s (%s): no links, skipping", node_id, node_type)
            continue

        if node_type in ("dynamips", "iou"):
            _inject_slots(
                node, required,
                min_adapter_slots=max_adapters.get(node_id, 0),
                adapter_link_types=adapter_link_types.get(node_id),
                link_counts_by_type=link_counts_by_type.get(node_id),
            )

        elif node_type in MAX_ADAPTERS:
            _inject_adapter_count(node, required)

        elif node_type in ("ethernet_switch", "ethernet_hub"):
            # For switches, the link count (required) IS the exact number of
            # ports needed because autofix_switch_adapter_assignments() in
            # schema.py guarantees sequential 1-based port_number assignment.
            # Using max_port_map would overcount by 1 because it assumes
            # 0-based port_number (computes highest_port + 1).
            _inject_ports_mapping(node, required)

        elif node_type in IMMUTABLE_TYPES:
            max_ports = IMMUTABLE_PORT_COUNT[node_type]
            if required > max_ports:
                logger.warning(
                    "Node %s (%s): %d links requested but %s is "
                    "hard-locked to %d port(s) — deployment WILL fail. "
                    "Constrain the LLM prompt or add a Pydantic validator "
                    "to reject multi-link %s nodes.",
                    node_id, node_type, required, node_type, max_ports,
                    node_type,
                )

        elif node_type in MAPPING_BASED_TYPES:
            logger.warning(
                "Node %s (%s): uses the `mappings` paradigm, not port "
                "counts — hardware injection not supported. If this node "
                "has links, manual `mappings` configuration may be required.",
                node_id, node_type,
            )

        else:
            logger.debug(
                "Node %s (%s): no injection rule defined, skipping",
                node_id, node_type,
            )

    return topology_dict
