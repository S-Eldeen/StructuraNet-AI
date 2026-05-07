"""
hw_config.py — Hardware Configuration Injector for Structranet AI

Dynamically expands port/adapter counts for GNS3 nodes based on
the number of links the AI topology assigns to each node, preventing
the dreaded "No available port" deployment error.

Tier classification
───────────────────
  Tier 1 — Expandable via `properties` payload:
    dynamips / iou           → slot-based modules  (PA-8E, NM-4E, …)
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

# ── Tier 1a: Dynamips slot-module catalogue ──────────────────────────────────
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

# ── Tier 1a: IOU slot configuration ─────────────────────────────────────────
# IOU slot values are image-dependent.  For L3 IOU images, integer module IDs
# are used; the most common is module 2 (4 Ethernet interfaces per slot).
# For L2 IOU images, the string "l2" is used.
IOU_L3_DEFAULT_MODULE = 2        # 4 Ethernet interfaces per slot (image-dependent)
IOU_L2_MODULE = "l2"
IOU_PORTS_PER_SLOT = 4           # SINGLE SOURCE OF TRUTH — imported by context_builder.py
IOU_FIRST_CONFIGURABLE_SLOT = 1  # slot0 is always present
IOU_MAX_SLOTS = 15               # slot1–slot15
IOU_BUILTIN_PORTS = 4            # slot0 typically provides 4 interfaces

# NOTE — cross-module contract:
# context_builder.py imports DYNAMIPS_BUILTIN_PORTS and IOU_PORTS_PER_SLOT
# from this module so there is a single source of truth for both constants.
# If you change the values above, context_builder.py inherits the change
# automatically without needing a separate edit.

# ── Tier 1c: Built-in ports for switch / hub ────────────────────────────────
# Source: gns3server/schemas/ethernet_switch_template.py (default = 8 entries)
#         gns3server/schemas/ethernet_hub_template.py   (default = 8 entries)
SWITCH_HUB_DEFAULT_PORTS = 8

# ── Tier 2: Immutable single-port nodes ─────────────────────────────────────
# Source: gns3server/compute/vpcs/vpcs_vm.py       → EthernetAdapter() × 1
#         gns3server/compute/traceng/traceng_vm.py   → EthernetAdapter() × 1
#         gns3server/compute/builtin/nodes/nat.py    → 1 port, setter = pass
IMMUTABLE_PORT_COUNT: Dict[str, int] = {
    "vpcs": 1,
    "traceng": 1,
    "nat": 1,
}
IMMUTABLE_TYPES = frozenset(IMMUTABLE_PORT_COUNT.keys())

# ── Tier 3: Mapping-based nodes ─────────────────────────────────────────────
# frame_relay_switch uses  {"1:101": "2:202"}  (port:dlci → port:dlci)
# atm_switch uses          {"1:10:100": "2:20:200"}  (port:vpi:vci → …)
MAPPING_BASED_TYPES = frozenset(["frame_relay_switch", "atm_switch"])


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper: count how many links attach to each node
# ═══════════════════════════════════════════════════════════════════════════════

def _count_links_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return ``{node_id: link_count}`` from the topology's links array.

    Each link has a ``nodes`` list with two entries; we count how many
    endpoint references point to each node ID.

    Example
    -------
    >>> links = [
    ...     {"nodes": [{"node_id": "R1"}, {"node_id": "SW1"}]},
    ...     {"nodes": [{"node_id": "R1"}, {"node_id": "SW2"}]},
    ... ]
    >>> _count_links_per_node(links)
    {'R1': 2, 'SW1': 1, 'SW2': 1}
    """
    counts: Dict[str, int] = {}
    for link in links:
        for ep in link.get("nodes", []):
            nid = ep.get("node_id")
            if nid:
                counts[nid] = counts.get(nid, 0) + 1
    return counts


def _max_port_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return ``{node_id: max_port_number + 1}`` from the topology's links.

    For switch/hub ports_mapping, the array must be large enough to
    include every ``port_number`` referenced in a link endpoint.  If the
    AI assigns non-contiguous port numbers (e.g., ports 0, 5, 10 on a
    switch with 3 links), we need 11 entries — not 3.

    A value of 0 means the node has no links.
    """
    max_ports: Dict[str, int] = {}
    for link in links:
        for ep in link.get("nodes", []):
            nid = ep.get("node_id")
            port = ep.get("port_number", 0)
            if nid:
                current = max_ports.get(nid, 0)
                max_ports[nid] = max(current, port + 1)
    return max_ports


def _max_adapter_per_node(links: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return ``{node_id: max_adapter_number_used}`` from the topology's links.

    Critical for Dynamips / IOU: adapter_number == slot_number.  If the AI
    assigns a link to adapter 3, then slot3 MUST exist on that node, even
    if slot1 alone has enough total ports to cover the link count.

    Used alongside _count_links_per_node() so that hw_config injects slots
    up to the highest adapter the AI actually referenced — not just enough
    ports by count.
    """
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

def _inject_slots(node: Dict[str, Any], required_ports: int, min_adapter_slots: int = 0) -> None:
    """Inject slot modules for dynamips / iou nodes to provide enough ports.

    Modifies ``node["properties"]`` in-place by adding ``slotN`` entries.
    Pre-existing slot assignments are **never overwritten** — if the LLM or
    a prior step already configured a slot, we skip it and move to the next.

    Parameters
    ----------
    required_ports : int
        Minimum number of ports needed (based on link count).
    min_adapter_slots : int
        Highest adapter_number used in any link endpoint for this node.
        Slots are injected up to at least this number, even if the port
        count is already satisfied by fewer slots.  This prevents the
        "adapter 3 has no slot" mismatch when the AI assigns links to
        high adapter numbers but hw_config only fills by port count.
    """
    properties = node.setdefault("properties", {})
    node_type = node["node_type"]

    if node_type == "dynamips":
        _inject_dynamips_slots(node, properties, required_ports, min_adapter_slots)
    elif node_type == "iou":
        _inject_iou_slots(node, properties, required_ports, min_adapter_slots)



def _identify_dynamips_platform(
    node: Dict[str, Any], properties: Dict[str, Any]
) -> str:
    """Best-effort identification of the Dynamips platform model.

    Checks, in order:
      1. ``properties.platform``  (explicit)
      2. ``node["template_name"]`` (e.g. "c7200")
      3. Fallback: "c7200" (most common in GNS3 topologies)
    """
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
) -> None:
    """Expand Dynamips slots based on the platform's module catalogue.

    Two injection drivers (both must be satisfied):
      1. Port count: inject enough slots to cover ``required_ports``.
      2. Adapter coverage: inject slots up to ``min_adapter_slots``,
         ensuring every adapter_number used in a link has a real slot
         behind it.  Without this, the AI can assign a link to adapter 3
         but only slot1 gets injected (enough ports by count, but
         adapter 3 doesn't physically exist on the router).
    """
    platform = _identify_dynamips_platform(node, properties)
    config = DYNAMIPS_SLOT_MODULES.get(platform, DYNAMIPS_FALLBACK)

    module_name = config["module"]
    ports_per_module = config["ports_per_module"]
    first_slot = config["first_configurable"]
    max_slots = config["max_slots"]

    # How many built-in ports does this platform have?
    builtin = DYNAMIPS_BUILTIN_PORTS.get(platform, DYNAMIPS_BUILTIN_DEFAULT)

    remaining = max(0, required_ports - builtin)

    # Calculate the last slot number we MUST reach for adapter coverage.
    # adapter_number == slot_number in Dynamips, so if the AI used
    # adapter 3, we need slot3 = slot_idx 3.
    # last_required_slot = min_adapter_slots (since slotN == adapter N)
    last_required_slot = min(min_adapter_slots, first_slot + max_slots - 1)

    if remaining <= 0 and min_adapter_slots < first_slot:
        logger.debug(
            "Node %s (%s): built-in ports sufficient "
            "(%d required, %d built-in)",
            node.get("node_id"), platform, required_ports, builtin,
        )
        # Even if port count is fine, we may still need slots for adapter coverage
        if min_adapter_slots < first_slot:
            return

    # Walk slots from first_configurable upward; skip occupied slots.
    #
    # TERMINATION FIX: The old guard was `slots_injected < max_slots`, which
    # only counts *newly* injected slots.  If the node already had pre-existing
    # slots (from a prior run or template), those pre-existing slots did NOT
    # increment `slots_injected`, so the loop could attempt to write beyond the
    # platform's physical slot range before the inner break fired.
    #
    # The correct bound is the slot_idx itself: never walk past the last
    # configurable slot for this platform, regardless of how many of those
    # slots were pre-existing vs. freshly injected.
    slots_injected = 0
    ports_covered = 0
    slot_idx = first_slot
    last_slot = first_slot + max_slots - 1  # inclusive upper bound

    # Continue until BOTH conditions are met:
    #   a) enough ports are covered (ports_covered >= remaining)
    #   b) we've reached the last adapter slot the AI referenced
    # AND we have not exceeded the platform's physical slot range.
    while slot_idx <= last_slot and (ports_covered < remaining or slot_idx <= last_required_slot):
        slot_key = f"slot{slot_idx}"

        if slot_key in properties:
            # Slot already configured — count its contribution but don't overwrite.
            # (Conservative: the existing module might provide fewer ports than
            #  ports_per_module, but we don't want to overwrite the user's choice.)
            ports_covered += ports_per_module
            logger.debug(
                "Node %s (%s): %s already set to '%s', counting %d ports",
                node.get("node_id"), platform,
                slot_key, properties[slot_key], ports_per_module,
            )
        else:
            properties[slot_key] = module_name
            ports_covered += ports_per_module
            slots_injected += 1
            logger.debug(
                "Node %s (%s): injected %s = %s (%d ports)",
                node.get("node_id"), platform,
                slot_key, module_name, ports_per_module,
            )

        slot_idx += 1

    total_after = builtin + ports_covered
    logger.info(
        "Node %s (%s): %d links, max_adapter=%d → injected %d slot(s) with %s "
        "→ %d total ports (built-in=%d + slots=%d)",
        node.get("node_id"), platform, required_ports, min_adapter_slots,
        slots_injected, module_name, total_after, builtin, ports_covered,
    )

    if total_after < required_ports:
        logger.warning(
            "Node %s (%s): could only provide %d/%d required ports — "
            "platform slot limit reached! Topology may fail to deploy.",
            node.get("node_id"), platform, total_after, required_ports,
        )


def _inject_iou_slots(
    node: Dict[str, Any], properties: Dict[str, Any],
    required_ports: int, min_adapter_slots: int = 0,
) -> None:
    """Expand IOU slots to provide enough Ethernet interfaces.

    IOU slot values are **image-dependent**.  We default to module 2
    (typically 4 Ethernet interfaces per slot on L3 IOU images).
    If the existing ``slot0`` value contains ``"l2"``, we assume an
    L2 IOU image and inject ``"l2"`` instead.

    Two injection drivers (both must be satisfied):
      1. Port count: inject enough slots to cover ``required_ports``.
      2. Adapter coverage: inject slots up to ``min_adapter_slots``.

    .. note:: If your IOU image uses different module IDs, adjust
              ``IOU_L3_DEFAULT_MODULE`` or set slots explicitly in the
              LLM output / template properties.
    """
    # Detect L2 vs L3 IOU image from existing slot0 value
    is_l2 = "l2" in str(properties.get("slot0", "")).lower()
    module_value: Any = IOU_L2_MODULE if is_l2 else IOU_L3_DEFAULT_MODULE
    ports_per_slot = IOU_PORTS_PER_SLOT

    # slot0 provides a baseline of interfaces
    builtin = IOU_BUILTIN_PORTS
    remaining = max(0, required_ports - builtin)

    # Calculate slots needed for port count
    slots_for_ports = (remaining + ports_per_slot - 1) // ports_per_slot  # ceil

    # Calculate slots needed for adapter coverage
    # adapter_number == slot_number in IOU, so if the AI used adapter 3,
    # we need slot3, which is slot index 3 (i.e., slots 1..3 = 3 slots)
    slots_for_adapters = max(0, min_adapter_slots - IOU_FIRST_CONFIGURABLE_SLOT + 1)

    # Take the maximum of both drivers
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
    """Set the ``adapters`` integer property for QEMU / Docker / VBox / VMware.

    Each adapter provides exactly **1** network port.  The value is capped
    at the platform-specific maximum (see ``MAX_ADAPTERS``).

    If ``properties.adapters`` already exists and is ≥ required, we leave
    it untouched — the template default or a prior step may have already
    set it correctly.
    """
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
    """Create a single ethernet_switch port entry for ``ports_mapping``.

    Schema source: gns3server/schemas/ethernet_switch.py
      ETHERNET_SWITCH_PORT_SCHEMA requires: name, port_number, type
      Optional: vlan (≥1), ethertype ("" | "0x8100" | "0x88A8" | …)
    """
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
        "type": "access",
        "vlan": 1,
        "ethertype": "",
    }


def _make_hub_port(index: int) -> Dict[str, Any]:
    """Create a single ethernet_hub port entry for ``ports_mapping``.

    Schema source: gns3server/schemas/ethernet_hub.py
      ETHERNET_HUB_PORT_SCHEMA requires: name, port_number
      (No type / vlan / ethertype — a hub is a dumb Layer 1 device.)
    """
    return {
        "name": f"Ethernet{index}",
        "port_number": index,
    }


def _inject_ports_mapping(node: Dict[str, Any], required_ports: int) -> None:
    """Expand the ``ports_mapping`` array for ethernet_switch / ethernet_hub.

    **Critical detail**: When ``ports_mapping`` is set explicitly in
    ``properties``, it **completely overrides** the template default.
    Therefore, if we need more than the default 8 ports, we must provide
    the **full** array from index 0 to N-1, not just the additional entries.

    **Explicit-always policy**: We ALWAYS generate a full ``ports_mapping``
    array for every switch/hub, even when the link count fits within the
    template default of 8 ports.  Relying on implicit template defaults is
    dangerous — different GNS3 servers may ship different defaults, and the
    absence of an explicit mapping can cause silent port mismatches during
    deployment.  Generating ``max(required_ports, 8)`` entries ensures a
    deterministic, portable configuration regardless of the server's template
    settings.

    If ``ports_mapping`` already exists in properties, we only **append**
    new entries (never shrink or overwrite existing ones).  If the existing
    mapping already covers the required count, we leave it untouched — it
    was either set by a prior run or explicitly by the user.
    """
    node_type = node["node_type"]
    properties = node.setdefault("properties", {})

    # Always generate at least SWITCH_HUB_DEFAULT_PORTS entries.
    # This eliminates reliance on implicit template defaults that may
    # differ across GNS3 installations.
    target_ports = max(required_ports, SWITCH_HUB_DEFAULT_PORTS)

    existing_raw = properties.get("ports_mapping")

    if existing_raw is not None:
        # ── ports_mapping already set explicitly — expand if needed ──
        existing: List[Dict[str, Any]] = list(existing_raw)
        current_count = len(existing)

        if target_ports <= current_count:
            logger.debug(
                "Node %s (%s): explicit ports_mapping has %d ports, "
                "%d target — no change",
                node.get("node_id"), node_type, current_count, target_ports,
            )
            return

        # Append only the additional entries
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
        # ── No explicit ports_mapping — always create a full array ──
        # We never rely on template defaults anymore.  Always emit a
        # deterministic ports_mapping of max(required_ports, 8) entries.
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
    """Inject hardware configuration into every topology node that needs it.

    Iterates every node, counts how many links attach to it, and dispatches
    to the correct helper based on ``node_type``::

        dynamips / iou                  → _inject_slots()
        qemu / docker / virtualbox      → _inject_adapter_count()
          / vmware
        ethernet_switch / ethernet_hub  → _inject_ports_mapping()
        vpcs / traceng / nat            → ⛔ skipped (hard-locked to 1 port)
        frame_relay_switch / atm_switch → ⚠️  warning (mappings paradigm)
        other                           → skipped silently

    Returns the topology dict with modified node properties (in-place).
    """
    # Our schema wraps nodes/links inside a "topology" object
    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    # Pre-compute link counts — one pass over the links array
    link_counts = _count_links_per_node(links)
    logger.info("Link counts per node: %s", link_counts)

    # Pre-compute max port numbers — needed for switch/hub ports_mapping
    # (Bug 1 fix: link count is insufficient when the AI assigns
    # non-contiguous port numbers)
    max_port_map = _max_port_per_node(links)

    # Pre-compute max adapter numbers — needed for Dynamips/IOU slot injection
    # (Bug fix: if the AI assigns a link to adapter 3, slot3 MUST exist,
    #  even if slot1 alone provides enough ports by count)
    max_adapters = _max_adapter_per_node(links)

    for node in nodes:
        node_id = node.get("node_id", "?")
        node_type = node.get("node_type", "")
        required = link_counts.get(node_id, 0)

        # No links attached → nothing to expand
        if required == 0:
            logger.debug("Node %s (%s): no links, skipping", node_id, node_type)
            continue

        # ── Tier 1: Expandable node types ──────────────────────────────

        if node_type in ("dynamips", "iou"):
            _inject_slots(node, required, min_adapter_slots=max_adapters.get(node_id, 0))

        elif node_type in MAX_ADAPTERS:
            _inject_adapter_count(node, required)

        elif node_type in ("ethernet_switch", "ethernet_hub"):
            # Bug 1 fix: Use max(port_number)+1, NOT link count.
            # If AI assigns non-contiguous ports (e.g., 0, 5, 10),
            # we need ports_mapping entries for ALL indices 0..max.
            ports_needed = max(max_port_map.get(node_id, 0), required)
            _inject_ports_mapping(node, ports_needed)

        # ── Tier 2: Immutable single-port nodes ────────────────────────

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

        # ── Tier 3: Mapping-based nodes ────────────────────────────────

        elif node_type in MAPPING_BASED_TYPES:
            logger.warning(
                "Node %s (%s): uses the `mappings` paradigm, not port "
                "counts — hardware injection not supported. If this node "
                "has links, manual `mappings` configuration may be required.",
                node_id, node_type,
            )

        # ── Unknown node type ──────────────────────────────────────────

        else:
            logger.debug(
                "Node %s (%s): no injection rule defined, skipping",
                node_id, node_type,
            )

    return topology_dict