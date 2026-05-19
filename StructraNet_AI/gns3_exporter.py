"""
gns3_exporter.py — Structranet AI  ·  GNS3 Portable Project Exporter  (V4.5)

Converts final_topology.json → network.gns3project (a ZIP importable via
GNS3 GUI → File → Import portable project).

V4.5 changes vs V4.4
─────────────────────
  • FIX: _clean_properties no longer injects file-pointer keys
    (startup_config, private_config). These are NOT valid properties
    in the GNS3 Dynamips/IOU/QEMU schemas — the schemas enforce
    additionalProperties: false, so injecting them causes:
      "Additional properties are not allowed ('startup_config' was unexpected)"
    Content keys (startup_config_content, private_config_content,
    startup_script) ARE valid schema properties and are now KEPT in
    the output.  GNS3 reads them during portable project import and
    writes the content to the correct config files.
  • FIX: _FORBIDDEN_POINTER_KEYS — explicit set of pointer keys that
    must be stripped from properties even if the LLM or upstream
    pipeline accidentally includes them.  Covers startup_config,
    private_config, and nvram.
  • Removed _CONTENT_TO_POINTER mapping (no longer needed).

V4.4 changes vs V4.3
─────────────────────
  • _clean_properties now strips pipeline-only content keys
    (startup_config_content, private_config_content, startup_script)
    and injects the GNS3-required file-pointer keys
    (startup_config, private_config, startup_script) pointing to the
    standard filenames inside the ZIP.
    Previously the content keys leaked into the JSON (ignored by GNS3)
    and the file-pointer keys were missing — so packed configs were
    invisible to GNS3, causing routers/VPCS to boot blank.
  • New export_configs_for_review() extracts all raw configs into a
    local directory with human-readable filenames (e.g. R1-Main.cfg,
    Core-SW_ports.json, PC1.vpc) for pre-GNS3 review.
  • convert() accepts config_review_dir parameter; when set, calls
    export_configs_for_review() automatically.
  • CLI gains --configs flag to specify the review output directory.

V4.3 changes vs V4.2
─────────────────────
  Corrections based on GNS3 source (gns3-gui/settings.py ADAPTER_MATRIX):

  • C1700-MB-1ETH → C1700-MB-1FE everywhere (correct Dynamips/GNS3 name).
  • c3745/c3725/c2691 default_nm: NM-4E → NM-1FE-TX
    (NM-4E is C3600-only; C3700_NMS = NM-1FE-TX, NM-4T, NM-16ESW)
  • c3640/c3620 first_configurable corrected to 0 (no fixed slot 0).
  • Added c3600 alias entry in _DYN_HW_DEFAULTS (GNS3 uses platform="c3600"
    for all 3620/3640/3660 chassis).
  • Added Leopard-2FE to _DYN_MODULE (was missing — caused wrong interface
    names for c3660 slot 0).
  • RAM defaults corrected:
      c3725: 256 → 128 MB  (GNS3 default)
      c3660: 256 → 192 MB  (GNS3 default for c3600 platform)
      c3640: 256 → 128 MB
      c3620: 256 → 128 MB
      c2691: 256 → 192 MB  (GNS3 default)
      c2600: 128 → 160 MB  (GNS3 default)
      c1700: 128 → 160 MB  (GNS3 default)
  • _DYN_BUILTIN updated to include c3600 alias.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GROUND TRUTH SOURCES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GNS3 server source  gns3server/schemas/project.py
                      gns3server/schemas/node.py
                      gns3server/schemas/link.py
  GNS3 controller     gns3server/controller/import_project.py
                      gns3server/controller/topology.py
  gns3-gui            gns3/modules/dynamips/settings.py  (ADAPTER_MATRIX)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import logging
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from constants.gns3 import (
    CONSOLE_TYPE,
    DEFAULT_ROLE_PRIORITY,
    FILE_CONFIG_TRIPLETS,
    GNS3_REVISION,
    GNS3_VERSION,
    LABEL_STYLE,
    ROLE_PRIORITY,
    SCENE_HEIGHT,
    SCENE_WIDTH,
    SYMBOL,
)
from constants.hardware import (
    DYNAMIPS_BUILTIN_INTERFACE_DETAILS,
    DYNAMIPS_COMPAT,
    DYNAMIPS_MODULE_INTERFACES,
    DYNAMIPS_SLOT_MODULES,
    PLATFORMS_DEFAULT_RAM,
)

logger = logging.getLogger("gns3_exporter")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

def _is_uuid(s: str) -> bool:
    return bool(s and _UUID_RE.match(s))


# ═══════════════════════════════════════════════════════════════════════════════
#  Visual defaults
# ═══════════════════════════════════════════════════════════════════════════════

_NODE_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "dynamips": (56, 40),
    "iou":      (56, 40),
    "vpcs":     (34, 32),
    "traceng":  (34, 32),
    "cloud":    (95, 65),
    "nat":      (95, 65),
}
_DEFAULT_NODE_SIZE = (65, 65)

_LABEL_OFFSET: Dict[str, Tuple[int, int]] = {
    "dynamips": (-17, -25),
    "iou":      (-17, -25),
    "vpcs":     (-8,  -22),
    "traceng":  (-8,  -22),
}
_DEFAULT_LABEL_OFFSET = (-10, -25)

_APPLIANCE_TYPES = frozenset(
    ["dynamips", "iou", "qemu", "docker", "virtualbox", "vmware"]
)
_BUILTIN_TYPES = frozenset([
    "vpcs", "ethernet_switch", "ethernet_hub", "cloud", "nat",
    "traceng", "frame_relay_switch", "atm_switch",
])


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips platform helpers
#
#  All hardware data is imported from constants/hardware.py — the SSOT.
#  No local copies of DYNAMIPS_BUILTIN_INTERFACE_DETAILS, DYNAMIPS_MODULE_INTERFACES,
#  or DYNAMIPS_SLOT_MODULES are maintained here.
# ═══════════════════════════════════════════════════════════════════════════════


def _get_slot0_module(platform: str) -> str:
    """Derive the fixed/motherboard slot0 module name from DYNAMIPS_COMPAT.

    Only returns a module name for platforms where slot 0 is a fixed
    motherboard chip (e.g., GT96100-FE on c3745, Leopard-2FE on c3660).
    Returns "" for platforms where slot 0 is user-configurable (c3640, c3620).
    """
    builtin = DYNAMIPS_BUILTIN_INTERFACE_DETAILS.get(platform, {})
    if builtin.get("count", 0) > 0:
        # Platform has a fixed slot 0 — derive the module name
        compat = DYNAMIPS_COMPAT.get(platform, {})
        slots = compat.get("slots", {})
        slot0_options = slots.get(0, [])
        if slot0_options:
            return slot0_options[0]
    return ""


_NODE_TYPE_DIR: Dict[str, str] = {
    "dynamips":   "dynamips",
    "iou":        "iou",
    "qemu":       "qemu",
    "docker":     "docker",
    "vpcs":       "vpcs",
    "virtualbox": "virtualbox",
    "vmware":     "vmware",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Pre-export validation gate
# ═══════════════════════════════════════════════════════════════════════════════

class ExportError(Exception):
    """Raised by _pre_export_validate when a blocking issue is found."""


def _pre_export_validate(nodes: List[dict], links: List[dict]) -> None:
    """Validate topology data before writing a single byte to disk.

    Raises ExportError listing ALL blocking issues found (not just the first).
    Prints warnings for non-blocking issues that the user should be aware of.
    """
    errors:   List[str] = []
    warnings: List[str] = []

    node_map: Dict[str, dict] = {n.get("node_id", ""): n for n in nodes}

    def _dynamips_installed_adapters(node: dict) -> set:
        props    = node.get("properties", {})
        platform = str(props.get("platform", node.get("template_name", ""))).lower()
        builtin  = DYNAMIPS_BUILTIN_INTERFACE_DETAILS.get(platform, {})
        installed = set()

        if builtin.get("count", 0) > 0 or props.get("slot0"):
            installed.add(0)

        hw = DYNAMIPS_SLOT_MODULES.get(platform, {})
        max_slots = hw.get("max_slots", 4)
        for slot_num in range(1, max_slots + 1):
            if props.get(f"slot{slot_num}"):
                installed.add(slot_num)

        return installed

    # Check 1: Dynamips slot compatibility
    for node in nodes:
        if node.get("node_type") != "dynamips":
            continue
        name     = node.get("name", node.get("node_id", "?"))
        props    = node.get("properties", {})
        platform = str(props.get("platform", "")).lower()

        if not platform or platform not in DYNAMIPS_COMPAT:
            continue

        compat = DYNAMIPS_COMPAT[platform]

        slot_num = 0
        while True:
            slot_key = f"slot{slot_num}"
            if slot_key not in props:
                break
            module = props[slot_key]
            if module:
                valid_modules = compat["slots"].get(slot_num)
                if valid_modules is None:
                    errors.append(
                        f"Node '{name}' ({platform}): slot{slot_num} does not exist "
                        f"on this platform (max slot: {max(compat['slots'].keys())})"
                    )
                elif module not in valid_modules:
                    errors.append(
                        f"Node '{name}' ({platform}): slot{slot_num}='{module}' is "
                        f"incompatible — allowed: {', '.join(valid_modules)}"
                    )
            slot_num += 1

        image = props.get("image", "")
        if image and ("placeholder" in image.lower() or image.endswith(".bin")):
            warnings.append(
                f"Node '{name}' ({platform}): image='{image}' looks like a placeholder. "
                f"GNS3 will fail to start this node unless a real IOS image is installed."
            )

    # Check 2: Link endpoints reference installed adapters
    for i, link in enumerate(links):
        for ep in link.get("nodes", []):
            nid     = ep.get("node_id", "")
            adapter = ep.get("adapter_number", 0)
            node    = node_map.get(nid)
            if node is None or node.get("node_type") != "dynamips":
                continue
            name      = node.get("name", nid)
            installed = _dynamips_installed_adapters(node)
            if adapter not in installed:
                errors.append(
                    f"Link {i}: node '{name}' uses adapter {adapter} but no slot module "
                    f"is installed there. GNS3 will show the link as connected but the "
                    f"interface will not exist in IOS."
                )

    # Check 3: Switch VLAN / trunk consistency
    for node in nodes:
        if node.get("node_type") != "ethernet_switch":
            continue
        name          = node.get("name", node.get("node_id", "?"))
        props         = node.get("properties", {})
        ports_mapping = props.get("ports_mapping", [])

        if not ports_mapping:
            errors.append(
                f"Switch '{name}' has no ports_mapping. "
                f"Run hw_config.inject_hardware_config() before exporting."
            )
            continue

        access_vlans = {p.get("vlan", 1) for p in ports_mapping if p.get("type") == "access"}
        trunk_count  = sum(1 for p in ports_mapping if p.get("type") == "dot1q")
        non_default  = access_vlans - {1}

        if non_default and trunk_count == 0:
            errors.append(
                f"Switch '{name}' has access ports on VLAN(s) {sorted(non_default)} "
                f"but no dot1q trunk port. Inter-VLAN traffic will be silently dropped. "
                f"Run topology_finalizer.apply_switch_port_patches() before exporting."
            )

    if warnings:
        print("\n[pre-export WARNINGS]")
        for w in warnings:
            print(f"  [!] {w}")

    if errors:
        msg = "\n[pre-export ERRORS — export aborted]\n"
        for e in errors:
            msg += f"  [X] {e}\n"
        raise ExportError(msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  Input normalisation
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise_input(data: dict) -> Tuple[str, List[dict], List[dict]]:
    name = data.get("name", "Imported_Network")
    topo = data.get("topology")
    if isinstance(topo, dict):
        nodes = topo.get("nodes", [])
        links = topo.get("links", [])
    else:
        nodes = data.get("nodes", [])
        links = data.get("links", [])

    if not nodes:
        raise ValueError(
            "No nodes found. Expected 'topology.nodes' or top-level 'nodes'."
        )
    return name, list(nodes), list(links)


# ═══════════════════════════════════════════════════════════════════════════════
#  UUID assignment
# ═══════════════════════════════════════════════════════════════════════════════

def _assign_uuids(
    project_name: str,
    nodes: List[dict],
) -> Tuple[str, Dict[str, str]]:
    project_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"structranet-{project_name}"))
    node_uuid_map: Dict[str, str] = {}
    for n in nodes:
        nid = n.get("node_id", "")
        if _is_uuid(nid):
            node_uuid_map[nid] = nid
        else:
            node_uuid_map[nid] = str(uuid.uuid5(uuid.UUID(project_uuid), nid))
    return project_uuid, node_uuid_map


# ═══════════════════════════════════════════════════════════════════════════════
#  Canvas layout
# ═══════════════════════════════════════════════════════════════════════════════

def _grid_positions(nodes: List[dict]) -> Dict[str, Tuple[int, int]]:
    existing:      Dict[str, Tuple[int, int]] = {}
    needs_layout:  List[dict] = []

    for n in nodes:
        nid = n.get("node_id", "")
        if "x" in n and "y" in n:
            try:
                existing[nid] = (int(n["x"]), int(n["y"]))
                continue
            except (TypeError, ValueError):
                pass
        needs_layout.append(n)

    if not needs_layout:
        return existing

    scored = sorted(
        needs_layout,
        key=lambda n: (
            ROLE_PRIORITY.get(n.get("node_type", ""), DEFAULT_ROLE_PRIORITY),
            n.get("node_id", ""),
        ),
    )

    positions: Dict[str, Tuple[int, int]] = dict(existing)
    col, row, last_priority = 0, 0, None

    for n in scored:
        nid      = n.get("node_id", "")
        priority = ROLE_PRIORITY.get(n.get("node_type", ""), DEFAULT_ROLE_PRIORITY)

        if last_priority is not None and priority != last_priority:
            row += 1
            col  = 0
        last_priority = priority

        positions[nid] = (col * 200 - 400, row * 150 - 200)
        col += 1
        if col >= 5:
            col  = 0
            row += 1

    return positions


# ═══════════════════════════════════════════════════════════════════════════════
#  Port name resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _port_name(node: dict, adapter: int, port: int) -> str:
    ntype    = node.get("node_type", "")
    props    = node.get("properties", {})
    template = str(node.get("template_name", "")).lower()

    if ntype == "dynamips":
        platform = str(props.get("platform", "")).lower() or template
        if adapter == 0:
            bi  = DYNAMIPS_BUILTIN_INTERFACE_DETAILS.get(platform, {"prefix": "FastEthernet", "count": 1})
            pfx = bi.get("prefix") or "FastEthernet"
            if bi.get("count", 0) == 0:
                mod = props.get("slot0", "")
                if mod and mod in DYNAMIPS_MODULE_INTERFACES:
                    pfx = DYNAMIPS_MODULE_INTERFACES[mod]["prefix"]
                else:
                    pfx = "FastEthernet"
            return f"{pfx}0/{port}"
        mod_name = props.get(f"slot{adapter}", "")
        if mod_name and mod_name in DYNAMIPS_MODULE_INTERFACES:
            pfx = DYNAMIPS_MODULE_INTERFACES[mod_name]["prefix"]
            return f"{pfx}{adapter}/{port}"
        return f"Ethernet{adapter}/{port}"

    if ntype == "iou":
        eth_adapters = int(props.get("ethernet_adapters", 2))
        if adapter < eth_adapters:
            return f"Ethernet{adapter}/{port}"
        return f"Serial{adapter - eth_adapters}/{port}"

    if ntype in ("qemu", "docker", "virtualbox", "vmware"):
        return f"eth{adapter}"

    if ntype in ("vpcs", "traceng"):
        return "eth0"

    if ntype == "ethernet_switch":
        return f"Ethernet{port}"

    if ntype == "ethernet_hub":
        return f"Ethernet{port}"

    if ntype == "nat":
        return "nat0"

    if ntype == "cloud":
        return f"Cloud{port}"

    if ntype == "frame_relay_switch":
        return f"Serial{port}"

    if ntype == "atm_switch":
        return f"ATM{port}"

    return f"Ethernet{adapter}/{port}"


def _short_name(long_name: str) -> str:
    return (
        long_name
        .replace("GigabitEthernet", "g")
        .replace("FastEthernet",    "f")
        .replace("Ethernet",        "e")
        .replace("Serial",          "s")
        .lower()
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ports array builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_ports(node: dict, links: List[dict]) -> List[dict]:
    nid   = node.get("node_id", "")
    seen  = set()
    ports = []

    for link in links:
        for ep in link.get("nodes", []):
            if ep.get("node_id") != nid:
                continue
            adapter = ep.get("adapter_number", 0)
            port    = ep.get("port_number",    0)
            key     = (adapter, port)
            if key in seen:
                continue
            seen.add(key)

            long  = _port_name(node, adapter, port)
            short = _short_name(long)
            ltype = link.get("link_type", "ethernet")

            ports.append({
                "adapter_number":  adapter,
                "port_number":     port,
                "name":            long,
                "short_name":      short,
                "link_type":       ltype,
                "data_link_types": (
                    {"Ethernet": "DLT_EN10MB"} if ltype == "ethernet"
                    else {"PPP": "DLT_PPP_SERIAL"}
                ),
            })

    ports.sort(key=lambda p: (p["adapter_number"], p["port_number"]))
    return ports


# ═══════════════════════════════════════════════════════════════════════════════
#  Config file extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_configs(node: dict, node_uuid: str) -> Dict[str, str]:
    ntype    = node.get("node_type", "")
    props    = node.get("properties", {})
    type_dir = _NODE_TYPE_DIR.get(ntype, ntype)
    result: Dict[str, str] = {}

    for prop_key, target_type, subpath in FILE_CONFIG_TRIPLETS:
        if target_type != ntype:
            continue
        value = props.get(prop_key)
        if value and isinstance(value, str):
            zip_path = f"project-files/{type_dir}/{node_uuid}/{subpath}"
            result[zip_path] = value

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Properties cleaner
# ═══════════════════════════════════════════════════════════════════════════════

# Config content keys that the AI embeds into node properties.
# These are VALID GNS3 schema properties — keep them in the output.
# However, content keys belonging to a DIFFERENT node type must be
# stripped because they are not valid for this node type's schema
# (GNS3 schemas have additionalProperties: false).
_PIPELINE_CONTENT_KEYS: frozenset = frozenset(
    k for k, _, _ in FILE_CONFIG_TRIPLETS
)

# File-pointer keys that must NEVER appear in node properties.
# These are NOT valid properties in ANY GNS3 node-type schema
# (Dynamips, IOU, QEMU, VPCS all have additionalProperties: false).
# They exist only in the .gns3 project file as path references, but
# GNS3 rejects them when they appear in the node properties dict.
# The LLM or upstream pipeline may accidentally include them — strip them.
_FORBIDDEN_POINTER_KEYS: frozenset = frozenset([
    "startup_config",    # Dynamips/IOU/QEMU — use startup_config_content instead
    "private_config",   # Dynamips/IOU     — use private_config_content instead
    "nvram",            # Dynamips         — not a valid schema property
])


def _clean_properties(node: dict) -> dict:
    """Strip forbidden pointer keys and cross-type content keys from node properties.

    The GNS3 server validates each node's properties against its type-specific
    schema with ``additionalProperties: false``.  This means ONLY properties
    listed in the schema are allowed.

    Two categories of keys are stripped:

    1. **Forbidden pointer keys** (``startup_config``, ``private_config``,
       ``nvram``) — These are NOT valid properties in ANY GNS3 node-type
       schema.  They are file-path references that exist only in the
       ``.gns3`` project file, not in the node properties dict.  The LLM
       or upstream pipeline may accidentally include them (e.g. from GNS3
       project examples), so they are explicitly stripped via
       ``_FORBIDDEN_POINTER_KEYS``.

    2. **Cross-type content keys** — Content keys like
       ``startup_config_content`` and ``startup_script`` ARE valid properties
       in their respective node-type schemas (Dynamips, IOU, QEMU, VPCS) and
       must be KEPT.  However, a content key that belongs to a DIFFERENT node
       type (e.g. ``startup_config_content`` on a VPCS node, or
       ``startup_script`` on a Dynamips node) must be removed because it is
       not in that node type's schema.

    The config files embedded in the ZIP by ``_extract_configs()`` are read
    by GNS3 during portable project import independently of the node
    properties.  GNS3 copies them from
    ``project-files/<type>/<uuid>/<subpath>`` to the project directory.
    """
    ntype = node.get("node_type", "")
    props = node.get("properties", {})
    cleaned: dict = {}

    # Build the set of content keys that are valid for this node type.
    active_content_keys: set = set()
    for prop_key, target_type, _subpath in FILE_CONFIG_TRIPLETS:
        if target_type == ntype:
            active_content_keys.add(prop_key)

    for k, v in props.items():
        # Strip forbidden file-pointer keys that are never valid in any
        # GNS3 node-type schema.  The LLM or upstream pipeline may
        # accidentally include them (e.g. from GNS3 project examples).
        if k in _FORBIDDEN_POINTER_KEYS:
            logger.debug(
                "Stripped forbidden pointer key '%s' from %s node", k, ntype,
            )
            continue
        if k in _PIPELINE_CONTENT_KEYS and k not in active_content_keys:
            # Content key for a *different* node type — drop it.
            # It is not valid in this node type's schema.
            logger.debug(
                "Stripped cross-type key '%s' (not valid for %s)", k, ntype,
            )
            continue
        # Valid property (including content keys for THIS node type) — keep.
        cleaned[k] = v

    return cleaned


# ═══════════════════════════════════════════════════════════════════════════════
#  Hardware property injection (gap-filling — trusts hw_config output)
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_dynamips_platform(props: dict, template: str) -> str:
    existing = str(props.get("platform", "")).lower().strip()
    if existing and existing in DYNAMIPS_SLOT_MODULES:
        return existing
    name_lower = str(template).lower()
    for platform in DYNAMIPS_SLOT_MODULES:
        if platform in name_lower or platform[1:] in name_lower:
            return platform
    logger.warning(
        "Cannot detect Dynamips platform from template '%s' — defaulting to c3745",
        template,
    )
    return "c3745"


def _inject_dynamips_properties(
    node: dict, props: dict, template: str, links: List[dict]
) -> None:
    """Fill in any Dynamips properties that hw_config didn't set.
    Uses setdefault throughout so hw_config output is never overwritten.
    """
    platform = _detect_dynamips_platform(props, template)
    hw       = DYNAMIPS_SLOT_MODULES.get(platform, DYNAMIPS_SLOT_MODULES["c3745"])

    props.setdefault("platform", platform)
    props.setdefault("ram", PLATFORMS_DEFAULT_RAM.get(platform, 256))

    if "image" not in props:
        placeholder = f"{platform}-adventerprisek9-mz.124-25d.bin"
        props["image"] = placeholder
        logger.warning(
            "Node '%s': no 'image' property — using placeholder '%s'.",
            node.get("name", "?"), placeholder,
        )

    slot0_module = _get_slot0_module(platform)
    if "slot0" not in props and slot0_module:
        props["slot0"] = slot0_module

    nid              = node.get("node_id", "")
    max_adapter      = 0
    serial_adapter_set: set = set()

    for link in links:
        for ep in link.get("nodes", []):
            if ep.get("node_id") != nid:
                continue
            adapter = ep.get("adapter_number", 0)
            max_adapter = max(max_adapter, adapter)
            if link.get("link_type") == "serial":
                serial_adapter_set.add(adapter)

    default_nm = hw["module"]
    serial_nm  = "NM-4T" if default_nm.startswith("NM") else "PA-4T+"
    max_slots  = hw["max_slots"]

    for slot_num in range(1, min(max_adapter + 1, max_slots + 1)):
        slot_key = f"slot{slot_num}"
        if slot_key not in props:
            props[slot_key] = serial_nm if slot_num in serial_adapter_set else default_nm

    if "slot0" not in props:
        for link in links:
            for ep in link.get("nodes", []):
                if ep.get("node_id") == nid and ep.get("adapter_number", -1) == 0:
                    props["slot0"] = serial_nm if 0 in serial_adapter_set else default_nm
                    break


def _inject_iou_properties(
    node: dict, props: dict, template: str, links: List[dict]
) -> None:
    if "path" not in props:
        props["path"] = f"/opt/gns3/images/{template}.bin"
        logger.warning(
            "Node '%s': no 'path' property — using placeholder '%s'.",
            node.get("name", "?"), props["path"],
        )

    if "ethernet_adapters" not in props or "serial_adapters" not in props:
        nid     = node.get("node_id", "")
        max_eth = -1
        max_ser = -1
        for link in links:
            for ep in link.get("nodes", []):
                if ep.get("node_id") != nid:
                    continue
                adapter = ep.get("adapter_number", 0)
                if link.get("link_type") == "serial":
                    max_ser = max(max_ser, adapter)
                else:
                    max_eth = max(max_eth, adapter)

        eth = int(props.get("ethernet_adapters",
                            max(max_eth + 1, 2) if max_eth >= 0 else 2))
        props.setdefault("ethernet_adapters", eth)
        if "serial_adapters" not in props:
            if max_ser >= 0:
                props["serial_adapters"] = max(max_ser - eth + 1, 1)
            else:
                props["serial_adapters"] = 0

    props.setdefault("ram", 256)


def _inject_qemu_properties(props: dict, template: str) -> None:
    if "hda_disk_image" not in props:
        props["hda_disk_image"] = f"{template}.qcow2"
    props.setdefault("ram",      512)
    props.setdefault("adapters", 8)


def _inject_docker_properties(props: dict, template: str) -> None:
    props.setdefault("image", template)


def _inject_hardware_properties(node: dict, links: List[dict]) -> None:
    ntype    = node.get("node_type", "")
    template = node.get("template_name", "")
    props    = node.setdefault("properties", {})

    if ntype == "dynamips":
        _inject_dynamips_properties(node, props, template, links)
    elif ntype == "iou":
        _inject_iou_properties(node, props, template, links)
    elif ntype == "qemu":
        _inject_qemu_properties(props, template)
    elif ntype == "docker":
        _inject_docker_properties(props, template)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main converter
# ═══════════════════════════════════════════════════════════════════════════════

def export_configs_for_review(nodes: List[dict], output_dir: str) -> str:
    """Extract all raw config text from nodes into a local directory.

    Writes human-readable config files suitable for pre-GNS3 review by
    network engineers.  Filenames are based on the node name, not the
    UUID — e.g. ``R1-Main.cfg``, ``Core-SW_ports.json``, ``PC1.vpc``.

    Args:
        nodes:          List of node dicts (same format as topology.nodes).
        output_dir:     Target directory (created if it does not exist).

    Returns:
        Absolute path of the output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    seen_names: Dict[str, int] = {}  # dedup counter

    for node in nodes:
        ntype = node.get("node_type", "")
        props = node.get("properties", {})
        raw_name = node.get("name", node.get("node_id", "unknown"))

        # Sanitise the node name for use as a filename.
        safe_name = re.sub(r"[^\w\-.]", "_", raw_name)

        # Deduplicate: if two nodes share a name, append a suffix.
        if safe_name in seen_names:
            seen_names[safe_name] += 1
            safe_name = f"{safe_name}_{seen_names[safe_name]}"
        else:
            seen_names[safe_name] = 0

        # ── Dynamips / IOU / QEMU: startup-config ──────────────────────
        for content_key in ("startup_config_content", "private_config_content"):
            content = props.get(content_key)
            if not content or not isinstance(content, str):
                continue
            if content_key == "startup_config_content":
                ext = ".cfg"
                suffix = ""
            else:
                ext = ".cfg"
                suffix = "_private"
            filename = f"{safe_name}{suffix}{ext}"
            filepath = out / filename
            filepath.write_text(content, encoding="utf-8")
            count += 1
            logger.info("Exported review config: %s", filepath)

        # ── VPCS: startup script ──────────────────────────────────────
        if ntype == "vpcs":
            script = props.get("startup_script")
            if script and isinstance(script, str):
                filename = f"{safe_name}.vpc"
                filepath = out / filename
                filepath.write_text(script, encoding="utf-8")
                count += 1
                logger.info("Exported review script: %s", filepath)

        # ── Ethernet switch: ports_mapping as JSON ─────────────────────
        if ntype == "ethernet_switch":
            ports_mapping = props.get("ports_mapping")
            if ports_mapping and isinstance(ports_mapping, list):
                filename = f"{safe_name}_ports.json"
                filepath = out / filename
                filepath.write_text(
                    json.dumps(ports_mapping, indent=2), encoding="utf-8",
                )
                count += 1
                logger.info("Exported switch ports: %s", filepath)

    abs_dir = str(out.resolve())
    print(f"[configs] {count} file(s) exported to {abs_dir}")
    return abs_dir


def convert(
    input_data: dict,
    output_path: str,
    name_override: str = None,
    image_map: Dict[str, str] = None,
    config_review_dir: str = None,
) -> str:
    """Convert a topology dict to a .gns3project ZIP.

    Args:
        input_data:        Topology dict (with topology.nodes / topology.links).
        output_path:       Destination .gns3project file path.
        name_override:     Override the project name.
        image_map:         Template→IOS image filename mapping.
        config_review_dir: If set, raw configs are also exported to this
                           local directory for human review before GNS3
                           import.  Filenames are based on node names.
    """
    image_map = image_map or {}

    project_name, nodes_in, links_in = _normalise_input(input_data)
    if name_override:
        project_name = name_override

    for n in nodes_in:
        if n.get("node_type") == "dynamips" and n.get("template_name") in image_map:
            n.setdefault("properties", {})["image"] = image_map[n["template_name"]]
        _inject_hardware_properties(n, links_in)

    iou_application_id_counter = 1
    for n in nodes_in:
        if n.get("node_type") == "iou":
            props = n.setdefault("properties", {})
            if "application_id" not in props:
                props["application_id"] = iou_application_id_counter
            iou_application_id_counter += 1

    _pre_export_validate(nodes_in, links_in)

    project_uuid, node_uuid_map = _assign_uuids(project_name, nodes_in)
    positions = _grid_positions(nodes_in)
    node_lookup: Dict[str, dict] = {n.get("node_id", ""): n for n in nodes_in}

    gns3_nodes:      List[dict] = []
    all_zip_configs: Dict[str, str] = {}

    for n in nodes_in:
        nid   = n.get("node_id", "")
        ntype = n.get("node_type", "")
        nuuid = node_uuid_map[nid]
        x, y  = positions.get(nid, (0, 0))
        w, h  = _NODE_DIMENSIONS.get(ntype, _DEFAULT_NODE_SIZE)
        lx, ly = _LABEL_OFFSET.get(ntype, _DEFAULT_LABEL_OFFSET)

        all_zip_configs.update(_extract_configs(n, nuuid))

        template_name = n.get("template_name", "")
        template_id:  Optional[str] = None
        if ntype in _APPLIANCE_TYPES and template_name:
            template_id = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"gns3-template-{template_name}")
            )

        if ntype == "iou":
            port_name_format  = "Ethernet{segment0}/{port0}"
            port_segment_size = 4
        else:
            port_name_format  = n.get("port_name_format", "Ethernet{0}")
            port_segment_size = 0

        label = n.get("label") if isinstance(n.get("label"), dict) else {}
        node_obj: dict = {
            "compute_id":        n.get("compute_id", "local"),
            "node_id":           nuuid,
            "node_type":         ntype,
            "name":              n.get("name", nid),
            "console":           None,
            "console_type":      CONSOLE_TYPE.get(ntype),
            "x":                 x,
            "y":                 y,
            "z":                 n.get("z", 1),
            "width":             w,
            "height":            h,
            "symbol":            SYMBOL.get(ntype, ":/symbols/computer.svg"),
            "label": {
                "text":     n.get("name", nid),
                "x":        label.get("x", lx),
                "y":        label.get("y", ly),
                "rotation": 0,
                "style":    LABEL_STYLE,
            },
            "properties":        _clean_properties(n),
            "port_name_format":  port_name_format,
            "port_segment_size": port_segment_size,
            "first_port_name":   n.get("first_port_name"),
            # "ports":             _build_ports(n, links_in), --> read only you can't write 
        }

        if ntype in _APPLIANCE_TYPES:
            node_obj["template_id"] = template_id

        gns3_nodes.append(node_obj)

    gns3_links: List[dict] = []

    for i, link in enumerate(links_in):
        eps = link.get("nodes", [])
        if len(eps) < 2:
            logger.warning("Link %d has fewer than 2 endpoints — skipped", i)
            continue

        ep0, ep1   = eps[0], eps[1]
        orig_id0   = ep0.get("node_id", "")
        orig_id1   = ep1.get("node_id", "")
        uuid0      = node_uuid_map.get(orig_id0)
        uuid1      = node_uuid_map.get(orig_id1)

        if not uuid0:
            logger.warning("Link %d: unknown node_id '%s' — skipped", i, orig_id0)
            continue
        if not uuid1:
            logger.warning("Link %d: unknown node_id '%s' — skipped", i, orig_id1)
            continue

        ltype     = link.get("link_type", "ethernet")
        link_uuid = str(uuid.uuid5(uuid.UUID(project_uuid), f"link-{i}"))

        node0 = node_lookup.get(orig_id0, {})
        node1 = node_lookup.get(orig_id1, {})
        ad0, pt0 = ep0.get("adapter_number", 0), ep0.get("port_number", 0)
        ad1, pt1 = ep1.get("adapter_number", 0), ep1.get("port_number", 0)
        pname0   = _port_name(node0, ad0, pt0)
        pname1   = _port_name(node1, ad1, pt1)

        gns3_links.append({
            "link_id":   link_uuid,
            "link_type": ltype,
            "nodes": [
                {
                    "node_id":        uuid0,
                    "adapter_number": ad0,
                    "port_number":    pt0,
                    "label": {
                        "text":     _short_name(pname0),
                        "x":        0,
                        "y":        0,
                        "rotation": 0,
                        "style":    LABEL_STYLE,
                    },
                },
                {
                    "node_id":        uuid1,
                    "adapter_number": ad1,
                    "port_number":    pt1,
                    "label": {
                        "text":     _short_name(pname1),
                        "x":        0,
                        "y":        0,
                        "rotation": 0,
                        "style":    LABEL_STYLE,
                    },
                },
            ],
        })

    project_gns3 = {
        "name":         project_name,
        "project_id":   project_uuid,
        "revision":     GNS3_REVISION,
        "type":         "topology",
        "version":      GNS3_VERSION,
        "auto_start":   True,
        "auto_close":   False,
        "auto_open":    False,
        "scene_width":  SCENE_WIDTH,
        "scene_height": SCENE_HEIGHT,
        "topology": {
            "nodes":    gns3_nodes,
            "links":    gns3_links,
            "drawings": [],
            "computes": [],
        },
    }

    if not str(output_path).endswith(".gns3project"):
        output_path = str(output_path) + ".gns3project"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(
        output_path, "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as zf:
        zf.writestr(
            "project.gns3",
            json.dumps(project_gns3, indent=2, ensure_ascii=False),
        )
        for zip_path, content in all_zip_configs.items():
            zf.writestr(zip_path, content)
            logger.info("Packed config: %s (%d bytes)", zip_path, len(content))

    # ── External config export for pre-GNS3 review ──────────────────
    if config_review_dir:
        export_configs_for_review(nodes_in, config_review_dir)

    abs_path = os.path.abspath(output_path)

    print(f"[OK] '{project_name}'  ->  {abs_path}")
    print(f"     nodes:   {len(gns3_nodes)}")
    print(f"     links:   {len(gns3_links)}")
    print(f"     configs: {len(all_zip_configs)} file(s) packed")
    if config_review_dir:
        print(f"     review:  {os.path.abspath(config_review_dir)}")
    print()
    print("Import: GNS3 GUI -> File -> Import portable project")

    return abs_path


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(
        description="Convert any network topology JSON → GNS3 .gns3project",
    )
    parser.add_argument("input",  help="Input topology JSON file")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output .gns3project path")
    parser.add_argument("--name",   default=None, help="Override the project name")
    parser.add_argument("--images", default=None,
                        help="Template→image map: 'c3745=image.bin,c7200=other.bin'")
    parser.add_argument("--configs", default=None, metavar="DIR",
                        help="Export raw configs to DIR for pre-GNS3 review")
    parser.add_argument("--debug",  action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    image_map: Dict[str, str] = {}
    if args.images:
        for entry in args.images.split(","):
            entry = entry.strip()
            if "=" in entry:
                k, v = entry.split("=", 1)
                image_map[k.strip()] = v.strip()

    try:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[ERR] File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERR] Invalid JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        out_path = args.output
    else:
        raw_name = (
            args.name
            or data.get("name")
            or (data.get("topology") or {}).get("name")
            or "network"
        )
        safe     = re.sub(r"[^\w\- ]", "_", raw_name).replace(" ", "_")
        out_path = str(Path(args.input).parent / f"{safe}.gns3project")

    try:
        convert(
            data, out_path,
            name_override=args.name,
            image_map=image_map,
            config_review_dir=args.configs,
        )
    except ExportError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERR] {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()