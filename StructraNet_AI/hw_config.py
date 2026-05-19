"""
hw_config.py — Hardware Configuration Injector for Structranet AI

Dynamically expands port/adapter counts for GNS3 nodes based on
the number of links the AI topology assigns to each node.

V3.1 corrections:
  - C1700-MB-1ETH → C1700-MB-1FE (correct GNS3/Dynamips module name)
  - c3640/c3620 first_configurable = 0 (no fixed slot 0 on these platforms;
    all slots are user-configurable)
  - Added c3600 platform alias so GNS3-exported topologies with
    platform="c3600" are handled instead of falling to the fallback
  - serial_nm selection: NM-4T for all NM-based platforms (c3745, c3725,
    c2691, c3660, c3640, c3620); PA-4T+ only for c7200
    c2600 has NO serial NM slots (C2600_NMS has no serial modules)
  - DYNAMIPS_SERIAL_MODULE_INTERFACES now correctly contains only
    Serial-prefix modules (PA-4T+, PA-8T, NM-4T)
    NM-1T has been ERADICATED — it does not exist in GNS3

This module is the SINGLE SOURCE OF TRUTH for all hardware constants
used across the pipeline. Other modules import from here.
"""

import logging
import math
from typing import Any, Dict, List, Optional

from constants.hardware import (
    DYNAMIPS_BUILTIN_DEFAULT,
    DYNAMIPS_BUILTIN_INTERFACE_DETAILS,
    DYNAMIPS_BUILTIN_PORTS,
    DYNAMIPS_BUILTIN_SERIAL_PORTS,
    DYNAMIPS_FALLBACK,
    DYNAMIPS_MODULE_INTERFACES,
    DYNAMIPS_SERIAL_FALLBACK,
    DYNAMIPS_SERIAL_MODULES,
    DYNAMIPS_SLOT_MODULES,
    IMMUTABLE_PORT_COUNT,
    IMMUTABLE_TYPES,
    IOU_DEFAULT_ETH_ADAPTERS,
    IOU_DEFAULT_SER_ADAPTERS,
    IOU_MAX_ADAPTERS,
    IOU_PORTS_PER_ADAPTER,
    L2_CONCENTRATOR_TYPES,
    L3_ROUTER_TYPES,
    MAPPING_BASED_TYPES,
    MAX_ADAPTERS,
    NO_CONFIG_TYPES,
    SWITCH_HUB_DEFAULT_PORTS,
)

logger = logging.getLogger("structranet.hw_config")


# ═══════════════════════════════════════════════════════════════════════════════
#  Derived constants — exported for use by context_builder and port_assigner
# ═══════════════════════════════════════════════════════════════════════════════

# Serial module interfaces — subset of DYNAMIPS_MODULE_INTERFACES where
# the interface prefix is "Serial". Used by context_builder for port naming.
DYNAMIPS_SERIAL_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    name: info
    for name, info in DYNAMIPS_MODULE_INTERFACES.items()
    if info["prefix"] == "Serial"
}

DYNAMIPS_SERIAL_MODULE_NAMES: frozenset = frozenset(DYNAMIPS_SERIAL_MODULE_INTERFACES.keys())

# Cross-catalogue module → ports_per_module lookup
_MODULE_PORT_COUNT: Dict[str, int] = {}
for _plat, _cfg in DYNAMIPS_SLOT_MODULES.items():
    _MODULE_PORT_COUNT[_cfg["module"]] = _cfg["ports_per_module"]
for _plat, _cfg in DYNAMIPS_SERIAL_MODULES.items():
    _MODULE_PORT_COUNT[_cfg["module"]] = _cfg["ports_per_module"]
for _mod, _info in DYNAMIPS_MODULE_INTERFACES.items():
    if _mod not in _MODULE_PORT_COUNT:
        _MODULE_PORT_COUNT[_mod] = _info["count"]


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper: link statistics per node
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_link_stats(links: List[Dict[str, Any]]) -> tuple:
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


def _count_links_per_node_by_type(
    links: List[Dict[str, Any]]
) -> Dict[str, Dict[str, int]]:
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


def _classify_adapter_link_types(
    links: List[Dict[str, Any]]
) -> Dict[str, Dict[int, str]]:
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 1a — Slot-based expansion (dynamips, iou)
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
        _inject_iou_slots(
            node, properties, required_ports, min_adapter_slots,
            link_counts_by_type=link_counts_by_type,
        )


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

    Corrections vs previous version:
    - c3640/c3620: first_configurable = 0 (no fixed motherboard slot)
    - c3600 alias handled (same as c3660 spec)
    - serial_nm: uses NM-4T for all NM-based platforms; PA-4T+ for c7200 only
    """
    platform = _identify_dynamips_platform(node, properties)
    eth_config = DYNAMIPS_SLOT_MODULES.get(platform, DYNAMIPS_FALLBACK)
    ser_config = DYNAMIPS_SERIAL_MODULES.get(platform, DYNAMIPS_SERIAL_FALLBACK)

    builtin_eth = DYNAMIPS_BUILTIN_PORTS.get(platform, DYNAMIPS_BUILTIN_DEFAULT)
    builtin_ser = DYNAMIPS_BUILTIN_SERIAL_PORTS.get(platform, 0)

    first_slot = eth_config["first_configurable"]
    max_slots = eth_config["max_slots"]

    # c1700 has no NM slots — nothing to inject
    if max_slots == 0:
        logger.debug(
            "Node %s (%s): no NM slots available, skipping slot injection",
            node.get("node_id"), platform,
        )
        return

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
        eth_covered < eth_remaining
        or ser_covered < ser_remaining
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
            existing_module = properties[slot_key]
            actual_ports = _MODULE_PORT_COUNT.get(existing_module, ports_per)
            is_serial_module = existing_module in DYNAMIPS_SERIAL_MODULE_NAMES
            if is_serial_module:
                ser_covered += actual_ports
            else:
                eth_covered += actual_ports
            logger.debug(
                "Node %s (%s): %s already set to '%s', counting %d %s ports",
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
    link_counts_by_type: Optional[Dict[str, int]] = None,
) -> None:
    lt_counts = link_counts_by_type or {}
    eth_required = lt_counts.get("ethernet", required_ports)
    ser_required = lt_counts.get("serial", 0)

    current_eth = int(properties.get("ethernet_adapters", IOU_DEFAULT_ETH_ADAPTERS))
    current_ser = int(properties.get("serial_adapters", IOU_DEFAULT_SER_ADAPTERS))

    needed_eth = min(math.ceil(eth_required / IOU_PORTS_PER_ADAPTER), IOU_MAX_ADAPTERS)
    needed_ser = min(math.ceil(ser_required / IOU_PORTS_PER_ADAPTER), IOU_MAX_ADAPTERS)

    new_eth = max(current_eth, needed_eth)
    new_ser = max(current_ser, needed_ser)

    properties["ethernet_adapters"] = new_eth
    properties["serial_adapters"] = new_ser

    logger.info(
        "Node %s (iou): %d links (eth=%d, ser=%d) → "
        "ethernet_adapters %d→%d, serial_adapters %d→%d",
        node.get("node_id"), required_ports,
        eth_required, ser_required,
        current_eth, new_eth, current_ser, new_ser,
    )

    total_eth_ports = new_eth * IOU_PORTS_PER_ADAPTER
    total_ser_ports = new_ser * IOU_PORTS_PER_ADAPTER
    if total_eth_ports < eth_required:
        logger.warning(
            "Node %s (iou): could only provide %d/%d Ethernet ports "
            "(max %d adapters) — topology may fail to deploy.",
            node.get("node_id"), total_eth_ports, eth_required, IOU_MAX_ADAPTERS,
        )
    if total_ser_ports < ser_required:
        logger.warning(
            "Node %s (iou): could only provide %d/%d Serial ports "
            "(max %d adapters) — topology may fail to deploy.",
            node.get("node_id"), total_ser_ports, ser_required, IOU_MAX_ADAPTERS,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 1b — Adapter count expansion (qemu, docker, virtualbox, vmware)
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
#  Tier 1c — Ports mapping expansion (ethernet_switch, ethernet_hub)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_switch_port(index: int) -> Dict[str, Any]:
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
        "type": "access",
        "vlan": 1,
        "ethertype": "",
    }


def _make_hub_port(index: int) -> Dict[str, Any]:
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
    }


def _inject_ports_mapping(node: Dict[str, Any], required_ports: int) -> None:
    node_type = node["node_type"]
    properties = node.setdefault("properties", {})

    target_ports = max(required_ports, SWITCH_HUB_DEFAULT_PORTS)

    existing_raw = properties.get("ports_mapping")

    if existing_raw is not None:
        existing: List[Dict[str, Any]] = list(existing_raw)

        if any(p.get("vlan", 0) < 1 for p in existing):
            for port in existing:
                if port.get("vlan", 0) < 1:
                    port["vlan"] = 1
            logger.info(
                "Node %s (%s): normalized ports_mapping vlan values to >= 1",
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
            "Node %s (%s): %d links → ports_mapping expanded %d → %d",
            node.get("node_id"), node_type,
            required_ports, current_count, len(existing),
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
            "Node %s (%s): %d links → explicit ports_mapping created (%d ports)",
            node.get("node_id"), node_type,
            required_ports, len(full_mapping),
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
            _inject_ports_mapping(node, required)

        elif node_type in IMMUTABLE_TYPES:
            max_ports = IMMUTABLE_PORT_COUNT[node_type]
            if required > max_ports:
                logger.warning(
                    "Node %s (%s): %d links requested but %s is "
                    "hard-locked to %d port(s) — deployment WILL fail.",
                    node_id, node_type, required, node_type, max_ports,
                )

        elif node_type in MAPPING_BASED_TYPES:
            logger.warning(
                "Node %s (%s): uses the `mappings` paradigm, not port "
                "counts — hardware injection not supported.",
                node_id, node_type,
            )

        else:
            logger.debug(
                "Node %s (%s): no injection rule defined, skipping",
                node_id, node_type,
            )

    return topology_dict