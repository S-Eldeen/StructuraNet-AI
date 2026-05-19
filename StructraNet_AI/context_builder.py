"""
context_builder.py — Phase 2 Context Builder for Structranet AI

Transforms a Phase 1 topology dict into a human-readable Configuration Brief
that the LLM uses to generate software configurations (IPs, routing, startup).

V3.1 changes:
  - REMOVED patch_switch_ports_mapping from this module.
    It now lives in topology_finalizer.py and runs during hardware injection,
    not as a side effect of reading the topology for a brief.
  - build_configuration_brief() now returns ONLY a string (no mutation, no tuple).
    The caller is responsible for passing a topology that has already been
    patched by topology_finalizer.apply_switch_port_patches().
  - All segment/VLAN logic is preserved.

V3.2 changes:
  - REMOVED duplicate DYNAMIPS_MODULE_INTERFACES table — now imported from
    constants/hardware.py (single source of truth).
  - REMOVED duplicate DYNAMIPS_BUILTIN_INTERFACES table — now imported from
    constants/hardware.py as DYNAMIPS_BUILTIN_INTERFACE_DETAILS.
  - C1700-MB-1ETH → C1700-MB-1FE (correct GNS3/Dynamips module name).
  - Added c3600 platform alias to interface resolution.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from constants.hardware import (
    NO_CONFIG_TYPES,
    DYNAMIPS_BUILTIN_INTERFACE_DETAILS as _HW_BUILTIN_IFACE,
    DYNAMIPS_MODULE_INTERFACES as _HW_MODULE_INTERFACES,
    DYNAMIPS_BUILTIN_PORTS as _HW_DYNAMIPS_BUILTIN_PORTS,
    IOU_PORTS_PER_ADAPTER as _HW_IOU_PORTS_PER_ADAPTER,
)
from hw_config import (
    DYNAMIPS_SERIAL_MODULE_INTERFACES as _HW_SERIAL_MOD_INTERFACES,
)

logger = logging.getLogger("structranet.context_builder")


# ═══════════════════════════════════════════════════════════════════════════════
#  Module / interface tables
#  Previously duplicated inline — now imported from constants/hardware.py.
#  Local aliases kept so the rest of this file needs no other changes.
# ═══════════════════════════════════════════════════════════════════════════════

# Full module → (prefix, count) map (Ethernet + Serial)
DYNAMIPS_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = _HW_MODULE_INTERFACES

# Built-in (adapter 0) interface details per platform
DYNAMIPS_BUILTIN_INTERFACES: Dict[str, Dict[str, Any]] = _HW_BUILTIN_IFACE


# ═══════════════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════════════

L2_CONCENTRATOR_TYPES: FrozenSet[str] = frozenset(["ethernet_switch", "ethernet_hub"])
L3_ROUTER_TYPES: FrozenSet[str] = frozenset([
    "dynamips", "iou", "qemu", "docker", "virtualbox", "vmware",
])
NODE_ROLE_MAP: Dict[str, str] = {
    "dynamips": "router", "iou": "router", "qemu": "appliance",
    "docker": "container", "vpcs": "host", "traceng": "host",
    "ethernet_switch": "switch", "ethernet_hub": "hub",
    "cloud": "cloud", "nat": "nat",
    "virtualbox": "appliance", "vmware": "appliance",
}

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
    node_id: str
    node_name: str
    node_type: str
    adapter_number: int
    port_number: int
    canonical_name: str


@dataclass
class Segment:
    segment_id: int
    seg_type: str
    link_pairs: List[Tuple[ResolvedPort, ResolvedPort]]
    concentrator_ids: Set[str] = field(default_factory=set)
    vlan_id: int = 0
    access_switch_name: str = ""
    link_type: str = "ethernet"


# ═══════════════════════════════════════════════════════════════════════════════
#  Port Name Resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _identify_platform(node: dict) -> str:
    props = node.get("properties", {})
    platform = props.get("platform")
    if platform:
        return str(platform).lower()
    return str(node.get("template_name", "")).lower()


def resolve_port_name(
    node: dict, adapter_number: int, port_number: int, link_type: str = "ethernet"
) -> str:
    node_type = node.get("node_type", "")
    if node_type == "dynamips":
        return _resolve_dynamips_port(node, adapter_number, port_number)
    if node_type == "iou":
        props = node.get("properties", {})
        eth_adapters = int(props.get("ethernet_adapters", 2))
        if adapter_number < eth_adapters:
            return f"Ethernet{adapter_number}/{port_number}"
        else:
            ser_adapter = adapter_number - eth_adapters
            return f"Serial{ser_adapter}/{port_number}"
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
    return f"adapter{adapter_number}/port{port_number}"


def _resolve_dynamips_port(node: dict, adapter_number: int, port_number: int) -> str:
    platform = _identify_platform(node)
    props = node.get("properties", {})

    if adapter_number == 0:
        # Use the imported builtin interface details — single source of truth.
        builtin = DYNAMIPS_BUILTIN_INTERFACES.get(
            platform, {"prefix": "FastEthernet", "count": 1}
        )
        prefix = builtin.get("prefix") or "FastEthernet"
        return f"{prefix}0/{port_number}"

    slot_key = f"slot{adapter_number}"
    module_name = props.get(slot_key, "")
    if module_name and module_name in DYNAMIPS_MODULE_INTERFACES:
        mod = DYNAMIPS_MODULE_INTERFACES[module_name]
        return f"{mod['prefix']}{adapter_number}/{port_number}"
    if module_name and module_name in _HW_SERIAL_MOD_INTERFACES:
        mod = _HW_SERIAL_MOD_INTERFACES[module_name]
        return f"{mod['prefix']}{adapter_number}/{port_number}"

    return f"Ethernet{adapter_number}/{port_number}"


def _resolve_all_interfaces(node: dict) -> List[str]:
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
    platform = _identify_platform(node)
    props = node.get("properties", {})
    interfaces: List[str] = []

    builtin_count = _HW_DYNAMIPS_BUILTIN_PORTS.get(platform, 1)
    builtin_entry = DYNAMIPS_BUILTIN_INTERFACES.get(
        platform, {"prefix": "FastEthernet", "count": 1}
    )
    prefix = builtin_entry.get("prefix")
    if prefix and builtin_count > 0:
        for p in range(builtin_count):
            interfaces.append(f"{prefix}0/{p}")

    for slot_num in range(1, 7):
        module_name = props.get(f"slot{slot_num}", "")
        if not module_name:
            continue
        mod = DYNAMIPS_MODULE_INTERFACES.get(module_name)
        if mod:
            for p in range(mod["count"]):
                interfaces.append(f"{mod['prefix']}{slot_num}/{p}")
        else:
            smod = _HW_SERIAL_MOD_INTERFACES.get(module_name)
            if smod:
                for p in range(smod["count"]):
                    interfaces.append(f"{smod['prefix']}{slot_num}/{p}")
            else:
                interfaces.append(f"Ethernet{slot_num}/0")

    return interfaces


def _list_iou_interfaces(node: dict) -> List[str]:
    props = node.get("properties", {})
    interfaces: List[str] = []
    eth_adapters = int(props.get("ethernet_adapters", 2))
    ser_adapters = int(props.get("serial_adapters", 2))
    for adapter in range(eth_adapters):
        for port in range(_HW_IOU_PORTS_PER_ADAPTER):
            interfaces.append(f"Ethernet{adapter}/{port}")
    for adapter in range(ser_adapters):
        for port in range(_HW_IOU_PORTS_PER_ADAPTER):
            interfaces.append(f"Serial{adapter}/{port}")
    return interfaces


# ═══════════════════════════════════════════════════════════════════════════════
#  Segment Building
# ═══════════════════════════════════════════════════════════════════════════════

def _build_node_map(topology: dict) -> Dict[str, dict]:
    return {n["node_id"]: n for n in topology.get("nodes", [])}


def _resolve_endpoint(
    ep: dict, node_map: Dict[str, dict], link_type: str = "ethernet"
) -> ResolvedPort:
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
        canonical_name=resolve_port_name(node, adapter, port, link_type=link_type),
    )


def _infer_vlan_for_access_switch(
    switch_name: str, vlan_counter: List[int], used_vlans: Set[int],
) -> int:
    m = re.match(r"^[A-Za-z]+(\d+)-SW$", switch_name, re.IGNORECASE)
    if m:
        suffix = int(m.group(1))
        candidate = suffix * 10
        if 1 <= candidate <= 4094 and candidate not in used_vlans:
            return candidate

    while vlan_counter[0] in used_vlans or vlan_counter[0] < 1:
        vlan_counter[0] += 10
        if vlan_counter[0] > 4094:
            raise ValueError(f"VLAN space exhausted for switch '{switch_name}'.")
    result = vlan_counter[0]
    vlan_counter[0] += 10
    return result


def _identify_core_switches(topology: dict, node_map: Dict[str, dict]) -> Set[str]:
    links = topology.get("links", [])
    core_ids: Set[str] = set()

    for node in topology.get("nodes", []):
        if node.get("node_type") not in L2_CONCENTRATOR_TYPES:
            continue
        nid = node["node_id"]
        name = node.get("name", "").lower()

        if "core" in name:
            core_ids.add(nid)
            continue

        has_router = False
        has_switch = False
        for link in links:
            eps = link.get("nodes", [])
            if len(eps) < 2:
                continue
            a_id = eps[0].get("node_id", "")
            b_id = eps[1].get("node_id", "")
            other = b_id if a_id == nid else (a_id if b_id == nid else None)
            if other is None:
                continue
            otype = node_map.get(other, {}).get("node_type", "")
            if otype in L3_ROUTER_TYPES:
                has_router = True
            elif otype in L2_CONCENTRATOR_TYPES:
                has_switch = True

        if has_router and has_switch:
            core_ids.add(nid)

    return core_ids


def build_segments(topology: dict, node_map: Dict[str, dict]) -> List[Segment]:
    links = topology.get("links", [])

    concentrator_ids: Set[str] = {
        n["node_id"] for n in topology.get("nodes", [])
        if n.get("node_type") in L2_CONCENTRATOR_TYPES
    }
    core_switch_ids = _identify_core_switches(topology, node_map)
    access_switch_ids = concentrator_ids - core_switch_ids

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
        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")
        if a_type in L2_CONCENTRATOR_TYPES and b_type in L2_CONCENTRATOR_TYPES:
            union(a_id, b_id)

    access_sw_has_core_parent: Set[str] = set()
    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
        if a_id in core_switch_ids and b_id in access_switch_ids:
            access_sw_has_core_parent.add(b_id)
        elif b_id in core_switch_ids and a_id in access_switch_ids:
            access_sw_has_core_parent.add(a_id)

    vlan_counter = [100]
    used_vlans: Set[int] = set()
    access_switch_vlan: Dict[str, int] = {}
    access_switch_name_map: Dict[str, str] = {}

    for node in topology.get("nodes", []):
        nid = node.get("node_id", "")
        if nid not in access_switch_ids or nid not in access_sw_has_core_parent:
            continue
        explicit_vlan = node.get("properties", {}).get("vlan", 0)
        if explicit_vlan and 1 <= int(explicit_vlan) <= 4094:
            vid = int(explicit_vlan)
            access_switch_vlan[nid] = vid
            used_vlans.add(vid)

    for node in topology.get("nodes", []):
        nid = node.get("node_id", "")
        if nid not in access_switch_ids:
            continue
        sw_name = node.get("name", nid)
        access_switch_name_map[nid] = sw_name

        if nid not in access_sw_has_core_parent:
            access_switch_vlan[nid] = 0
            continue
        if nid in access_switch_vlan:
            continue

        vid = _infer_vlan_for_access_switch(sw_name, vlan_counter, used_vlans)
        access_switch_vlan[nid] = vid
        used_vlans.add(vid)

    access_sw_router_key: Dict[str, str] = {}
    for sw_id in access_switch_ids:
        access_sw_router_key[sw_id] = _find_router_segment_key(
            sw_id, links, node_map, concentrator_ids, core_switch_ids, find
        )

    link_segment_keys: List[str] = []
    link_access_sw: List[Optional[str]] = []
    link_link_types: List[str] = []

    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            link_segment_keys.append("")
            link_access_sw.append(None)
            link_link_types.append("ethernet")
            continue

        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
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
            key = f"p2p:{a_id}:{eps[0].get('adapter_number',0)}:{eps[0].get('port_number',0)}"
        elif a_is_router and b_is_core:
            resolved = resolve_port_name(
                node_map[a_id], eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0), link_type=link.get("link_type", "ethernet")
            )
            key = f"trunk:{a_id}:{resolved}"
        elif b_is_router and a_is_core:
            resolved = resolve_port_name(
                node_map[b_id], eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0), link_type=link.get("link_type", "ethernet")
            )
            key = f"trunk:{b_id}:{resolved}"
        elif a_is_router:
            resolved = resolve_port_name(
                node_map[a_id], eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0), link_type=link.get("link_type", "ethernet")
            )
            vlan = access_switch_vlan.get(b_id, 0) if b_is_access else 0
            key = f"router:{a_id}:{resolved}:vlan:{vlan}"
            if b_is_access:
                assigned_access_sw = b_id
        elif b_is_router:
            resolved = resolve_port_name(
                node_map[b_id], eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0), link_type=link.get("link_type", "ethernet")
            )
            vlan = access_switch_vlan.get(a_id, 0) if a_is_access else 0
            key = f"router:{b_id}:{resolved}:vlan:{vlan}"
            if a_is_access:
                assigned_access_sw = a_id
        elif a_is_core and b_is_access:
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
            key = f"switch_group:{find(a_id)}"
        elif a_is_conc:
            key = _find_router_segment_key(
                a_id, links, node_map, concentrator_ids, core_switch_ids, find
            )
        elif b_is_conc:
            key = _find_router_segment_key(
                b_id, links, node_map, concentrator_ids, core_switch_ids, find
            )
        else:
            key = f"p2p:{a_id}:{eps[0].get('adapter_number',0)}:{eps[0].get('port_number',0)}"

        link_segment_keys.append(key)
        link_access_sw.append(assigned_access_sw)
        link_link_types.append(link.get("link_type", "ethernet"))

    grouped: Dict[str, List[dict]] = {}
    grouped_access_sw: Dict[str, Optional[str]] = {}
    grouped_link_type: Dict[str, str] = {}

    for i, key in enumerate(link_segment_keys):
        if key:
            grouped.setdefault(key, []).append(links[i])
            if link_access_sw[i] is not None:
                grouped_access_sw[key] = link_access_sw[i]
            lt = link_link_types[i] if i < len(link_link_types) else "ethernet"
            if key not in grouped_link_type or lt == "serial":
                grouped_link_type[key] = lt

    segments: List[Segment] = []
    seg_id = 1

    for key, links_in in grouped.items():
        pair_list: List[Tuple[ResolvedPort, ResolvedPort]] = []
        conc_ids: Set[str] = set()

        for link in links_in:
            eps = link.get("nodes", [])
            if len(eps) < 2:
                continue
            link_lt = link.get("link_type", "ethernet")
            rp_a = _resolve_endpoint(eps[0], node_map, link_type=link_lt)
            rp_b = _resolve_endpoint(eps[1], node_map, link_type=link_lt)
            pair_list.append((rp_a, rp_b))
            if rp_a.node_id in concentrator_ids:
                conc_ids.add(rp_a.node_id)
            if rp_b.node_id in concentrator_ids:
                conc_ids.add(rp_b.node_id)

        if key.startswith("p2p:"):
            seg_type, vlan_id, sw_name = "point-to-point", 0, ""
        elif key.startswith("trunk:"):
            seg_type, vlan_id, sw_name = "trunk", 0, ""
        else:
            seg_type = "multi-access"
            m = re.search(r":vlan:(\d+)$", key)
            vlan_id = int(m.group(1)) if m else 0
            access_sw_id = grouped_access_sw.get(key)
            sw_name = access_switch_name_map.get(access_sw_id, "") if access_sw_id else ""

        segments.append(Segment(
            segment_id=seg_id,
            seg_type=seg_type,
            link_pairs=pair_list,
            concentrator_ids=conc_ids,
            vlan_id=vlan_id,
            access_switch_name=sw_name,
            link_type=grouped_link_type.get(key, "ethernet"),
        ))
        seg_id += 1

    return segments


def _find_router_segment_key(
    switch_id: str, all_links: List[dict], node_map: Dict[str, dict],
    concentrator_ids: Set[str], core_switch_ids: Set[str], find_func,
) -> str:
    for link in all_links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        if a_type in L3_ROUTER_TYPES and b_type in L2_CONCENTRATOR_TYPES:
            if find_func(b_id) == find_func(switch_id):
                resolved = resolve_port_name(
                    node_map[a_id], eps[0].get("adapter_number", 0),
                    eps[0].get("port_number", 0),
                    link_type=link.get("link_type", "ethernet")
                )
                return f"router:{a_id}:{resolved}"
        if b_type in L3_ROUTER_TYPES and a_type in L2_CONCENTRATOR_TYPES:
            if find_func(a_id) == find_func(switch_id):
                resolved = resolve_port_name(
                    node_map[b_id], eps[1].get("adapter_number", 0),
                    eps[1].get("port_number", 0),
                    link_type=link.get("link_type", "ethernet")
                )
                return f"router:{b_id}:{resolved}"

    return f"switch_group:{find_func(switch_id)}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Brief Generation (read-only — no topology mutation)
# ═══════════════════════════════════════════════════════════════════════════════

def _compact_interface_list(interfaces: List[str]) -> str:
    if not interfaces:
        return "(none)"
    if len(interfaces) <= 4:
        return ", ".join(interfaces)
    return f"{interfaces[0]}..{interfaces[-1]}"


def _collect_segment_hosts(seg: Segment) -> List[ResolvedPort]:
    hosts: List[ResolvedPort] = []
    seen: Set[str] = set()
    for ep_a, ep_b in seg.link_pairs:
        for ep in (ep_a, ep_b):
            if ep.node_type not in L2_CONCENTRATOR_TYPES:
                key = f"{ep.node_id}:{ep.canonical_name}"
                if key not in seen:
                    seen.add(key)
                    hosts.append(ep)
    return hosts


def _find_router_iface_in_segment(seg: Segment) -> str:
    for ep_a, ep_b in seg.link_pairs:
        for ep in (ep_a, ep_b):
            if ep.node_type in L3_ROUTER_TYPES:
                return ep.canonical_name
    return ""


def _extract_trunk_router_iface(segments: List[Segment]) -> str:
    for seg in segments:
        if seg.seg_type != "trunk":
            continue
        for ep_a, ep_b in seg.link_pairs:
            for ep in (ep_a, ep_b):
                if ep.node_type in L3_ROUTER_TYPES:
                    return ep.canonical_name
    return ""


def _detect_nat_role(
    nat_node_id: str, links: List[dict],
    node_map: Dict[str, dict], concentrator_ids: Set[str]
) -> str:
    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
        other_id = b_id if a_id == nat_node_id else (a_id if b_id == nat_node_id else None)
        if other_id is None:
            continue
        other_type = node_map.get(other_id, {}).get("node_type", "")
        if other_type in L3_ROUTER_TYPES:
            return "outside"
        if other_type in L2_CONCENTRATOR_TYPES:
            return "inside"
    return ""


def _detect_router_nat_interfaces(
    nodes: List[dict], links: List[dict],
    node_map: Dict[str, dict], concentrator_ids: Set[str],
) -> Dict[str, Dict[str, str]]:
    nat_ids = {n["node_id"] for n in nodes if n.get("node_type") == "nat"}
    if not nat_ids:
        return {}

    router_ifaces: Dict[str, Dict[str, str]] = {}
    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        if a_type in L3_ROUTER_TYPES and b_id in nat_ids:
            iface = resolve_port_name(
                node_map[a_id], eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0),
                link_type=link.get("link_type", "ethernet")
            )
            router_ifaces.setdefault(a_id, {})[iface] = "outside"
        elif b_type in L3_ROUTER_TYPES and a_id in nat_ids:
            iface = resolve_port_name(
                node_map[b_id], eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0),
                link_type=link.get("link_type", "ethernet")
            )
            router_ifaces.setdefault(b_id, {})[iface] = "outside"

    for link in links:
        eps = link.get("nodes", [])
        if len(eps) < 2:
            continue
        a_id, b_id = eps[0].get("node_id", ""), eps[1].get("node_id", "")
        a_type = node_map.get(a_id, {}).get("node_type", "")
        b_type = node_map.get(b_id, {}).get("node_type", "")

        if a_type in L3_ROUTER_TYPES and a_id in router_ifaces:
            iface = resolve_port_name(
                node_map[a_id], eps[0].get("adapter_number", 0),
                eps[0].get("port_number", 0),
                link_type=link.get("link_type", "ethernet")
            )
            is_inside = (
                b_type in L2_CONCENTRATOR_TYPES or
                (b_type in L3_ROUTER_TYPES and link.get("link_type") == "serial")
            )
            if iface not in router_ifaces[a_id] and is_inside:
                router_ifaces[a_id][iface] = "inside"
        elif b_type in L3_ROUTER_TYPES and b_id in router_ifaces:
            iface = resolve_port_name(
                node_map[b_id], eps[1].get("adapter_number", 0),
                eps[1].get("port_number", 0),
                link_type=link.get("link_type", "ethernet")
            )
            is_inside = (
                a_type in L2_CONCENTRATOR_TYPES or
                (a_type in L3_ROUTER_TYPES and link.get("link_type") == "serial")
            )
            if iface not in router_ifaces[b_id] and is_inside:
                router_ifaces[b_id][iface] = "inside"

    return router_ifaces


def generate_brief(topology: dict) -> str:
    """Generate the Configuration Brief string from a topology dict.

    READ-ONLY: this function does NOT mutate the topology.
    Call topology_finalizer.apply_switch_port_patches() BEFORE calling this
    if you need the ports_mapping to reflect the VLAN plan.
    """
    node_map = _build_node_map(topology)
    segments = build_segments(topology, node_map)
    nodes = topology.get("nodes", [])
    links = topology.get("links", [])

    concentrator_ids: Set[str] = {
        n["node_id"] for n in nodes if n.get("node_type") in L2_CONCENTRATOR_TYPES
    }

    lines: List[str] = []
    lines.append("NETWORK TOPOLOGY — CONFIGURATION BRIEF")
    lines.append("=" * 45)
    lines.append("")

    lines.append("NODES:")
    for node in nodes:
        nid = node.get("node_id", "?")
        ntype = node.get("node_type", "")
        template = node.get("template_name", "")
        role = NODE_ROLE_MAP.get(ntype, ntype)
        interfaces = _resolve_all_interfaces(node)
        lines.append(f"  {nid} ({ntype}/{template}, {role})")
        lines.append(f"    Interfaces: {_compact_interface_list(interfaces)}")
    lines.append("")

    lines.append("SEGMENTS:")
    trunk_router_iface = _extract_trunk_router_iface(segments)

    for seg in segments:
        hosts = _collect_segment_hosts(seg)

        if seg.seg_type == "trunk":
            lines.append(f"  Segment {seg.segment_id} (802.1Q trunk — NOT a routed segment):")
            for ep_a, ep_b in seg.link_pairs:
                lines.append(
                    f"    {ep_a.node_id:6s} {ep_a.canonical_name:20s}"
                    f"  <->  {ep_b.node_id} {ep_b.canonical_name}"
                )
            lines.append("    → Configure 802.1Q sub-interfaces on the router side, one per VLAN.")
        elif seg.seg_type == "multi-access":
            vlan_label = f"VLAN {seg.vlan_id}" if seg.vlan_id else "untagged"
            sw_label = f", access-sw: {seg.access_switch_name}" if seg.access_switch_name else ""
            lines.append(
                f"  Segment {seg.segment_id} "
                f"(multi-access, {vlan_label}{sw_label}, {len(hosts)} host(s)):"
            )
            if seg.vlan_id:
                parent_iface = trunk_router_iface or _find_router_iface_in_segment(seg)
                if parent_iface:
                    lines.append(
                        f"    → Router sub-interface: {parent_iface}.{seg.vlan_id} "
                        f"(encapsulation dot1Q {seg.vlan_id})"
                    )
                else:
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

    nat_nodes = [n for n in nodes if n.get("node_type") == "nat"]
    if nat_nodes:
        lines.append("NAT GATEWAYS:")
        for nat_node in nat_nodes:
            nat_id = nat_node.get("node_id", "?")
            role = _detect_nat_role(nat_id, links, node_map, concentrator_ids)
            lines.append(
                f"  {nat_node.get('name', nat_id)} ({nat_id}): role={role or 'unknown'}"
            )
        lines.append("")

    router_nat_ifaces = _detect_router_nat_interfaces(nodes, links, node_map, concentrator_ids)
    if router_nat_ifaces:
        lines.append("ROUTER NAT INTERFACE ASSIGNMENTS:")
        for router_id, iface_map in router_nat_ifaces.items():
            router_name = node_map.get(router_id, {}).get("name", router_id)
            lines.append(f"  {router_name} ({router_id}):")
            for iface_name, direction in sorted(iface_map.items()):
                lines.append(f"    {iface_name}: ip nat {direction}")
        lines.append("")

    p2p_segments = [s for s in segments if s.seg_type == "point-to-point"]
    if p2p_segments:
        lines.append("WAN POINT-TO-POINT LINKS:")
        for i, seg in enumerate(p2p_segments):
            is_serial = seg.link_type == "serial"
            lines.append(f"  Segment {seg.segment_id} ({'SERIAL' if is_serial else 'Ethernet'}):")
            for ep_a, ep_b in seg.link_pairs:
                lines.append(
                    f"    {ep_a.node_id:6s} {ep_a.canonical_name:20s}"
                    f"  <->  {ep_b.node_id:6s} {ep_b.canonical_name}"
                )
            lines.append(f"    → Use /30 subnets (e.g. 10.255.{i}.0/30)")
            if is_serial:
                lines.append("    → SERIAL: encapsulation hdlc, clock rate 64000 on DCE side")
        lines.append("")

    lines.append("CONFIG KEY MAPPING (use these exact property names):")
    present_types = {n.get("node_type") for n in nodes}
    for ntype in sorted(present_types):
        keys = CONFIG_KEY_MAP.get(ntype)
        if keys:
            lines.append(f"  {ntype} -> {', '.join(keys)}")
        elif ntype in NO_CONFIG_TYPES:
            lines.append(f"  {ntype} -> No config needed")
    lines.append("")

    lines.append("ARCHITECTURAL ADVICE:")
    vlan_segments = [s for s in segments if s.vlan_id > 0]
    flat_segments = [s for s in segments if s.seg_type == "multi-access" and s.vlan_id == 0]

    if vlan_segments:
        vlan_sw_names = [s.access_switch_name for s in vlan_segments if s.access_switch_name]
        lines.append(
            f"  This topology has {len(vlan_segments)} VLAN segment(s): "
            f"[{', '.join(vlan_sw_names)}]."
        )
        lines.append(
            "  You MUST implement Router-on-a-Stick (802.1Q sub-interfaces) for these segments."
        )
        if flat_segments:
            flat_sw_names = [s.access_switch_name for s in flat_segments if s.access_switch_name]
            lines.append(
                f"  ALSO {len(flat_segments)} FLAT/untagged segment(s): "
                f"[{', '.join(flat_sw_names)}]. Use plain IP on physical interface."
            )
    elif flat_segments:
        lines.append("  This is a FLAT network. Use plain IP addresses on physical interfaces.")
        lines.append("  DO NOT use 802.1Q sub-interfaces or dot1Q encapsulation.")
    else:
        lines.append("  No access switches. Assign one subnet per segment.")
    lines.append("")

    lines.append("TASK:")
    lines.append("  1. Assign one unique subnet per segment (no overlaps).")
    lines.append("  2. /24 for multi-access, /30 for point-to-point.")
    lines.append("  3. For each router: generate full Cisco IOS startup config.")
    if vlan_segments:
        lines.append("     - VLAN segments: configure 802.1Q sub-interfaces (e.g. Fa0/0.10).")
    if p2p_segments:
        lines.append("     - WAN/Serial: /30 subnets, routing protocol, 'clock rate 64000' on DCE.")
    if router_nat_ifaces:
        lines.append("     - NAT: mark interfaces ip nat inside/outside, add PAT overload rule.")
    lines.append("  4. For each VPCS host: startup_script with 'ip' command and correct gateway.")
    lines.append("  5. Include routing protocols for multi-segment routers.")
    lines.append("  6. Skip ethernet_switch, ethernet_hub, NAT, cloud — no IP config needed.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

def build_configuration_brief(topology: dict) -> str:
    """Generate the Configuration Brief string from a topology dict.

    IMPORTANT: The topology should already have ports_mapping patched by
    topology_finalizer.apply_switch_port_patches() before calling this.
    This function is READ-ONLY — it does not mutate the topology.
    """
    topo = topology.get("topology", topology)
    brief = generate_brief(topo)
    logger.info("Configuration brief generated (%d chars)", len(brief))
    return brief


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")
    json_path = sys.argv[1] if len(sys.argv) > 1 else "output/_topology.json"
    try:
        with open(json_path) as f:
            data = json.load(f)
        print(build_configuration_brief(data))
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)