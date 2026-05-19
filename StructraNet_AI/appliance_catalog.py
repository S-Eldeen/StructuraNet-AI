"""
appliance_catalog.py -- Static Appliance Catalog for Structranet AI

Defines the mandatory creation properties for every GNS3 appliance type
that Structranet AI can emit.  These properties are required by the GNS3
server (or by the .gns3project portable-project format) to create a
functional node -- without them, GNS3 will reject the node or silently
default to broken values.

Phase A deliverable: Static Catalog + Mandatory Properties.

Design choices
~~~~~~~~~~~~~~
  * Each entry is keyed by **template_name** (the human-readable string
    the AI agent uses to identify a device, e.g. "Cisco 7200").
  * Values include ALL properties that GNS3 requires at node-creation
    time, minus the ones that hw_config.py will dynamically inject
    (slotN, adapters, ports_mapping).
  * The catalog is a plain dict so it can be serialised to JSON and
    shipped to users for customisation.
  * `load_catalog()` merges a user-supplied JSON overlay on top of the
    built-in defaults, giving users an escape hatch for custom images /
    RAM / non-standard platforms.
  * `get_appliance()` is the single lookup point that all other modules
    call -- they never access APPLIANCE_CATALOG directly.

Sources: GNS3 server v2.2 source code
  - gns3server/schemas/dynamips_template.py
  - gns3server/schemas/iou_template.py
  - gns3server/schemas/vpcs_template.py
  - gns3server/schemas/ethernet_switch_template.py
  - gns3server/schemas/ethernet_hub_template.py
  - gns3server/compute/dynamips/nodes/c7200.py
  - gns3server/compute/iou/iou_vm.py
"""

import json
import logging
import os
from copy import deepcopy
from typing import Any, Dict, Optional

from constants.appliances import APPLIANCE_CATALOG

logger = logging.getLogger("structranet.appliance_catalog")


# ═══════════════════════════════════════════════════════════════════════════════
#  Default Appliance Catalog
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Each entry maps a template_name to a dict of mandatory creation
#  properties.  The dict is NOT the complete GNS3 node -- it only
#  contains the keys that MUST be present in node["properties"] for
#  the .gns3project to be valid.
#
#  Mandatory keys per GNS3 node type:
#    dynamips : platform, image, ram, nvram, slot0, console_type,
#               port_name_format, port_segment_size
#    iou      : path, ram, nvram, ethernet_adapters, serial_adapters,
#               console_type, port_name_format, port_segment_size
#    vpcs     : console_type
#    ethernet_switch : console_type, port_name_format, port_segment_size
#    ethernet_hub    : port_name_format, port_segment_size
#

# ═══════════════════════════════════════════════════════════════════════════════
#  Catalog Loading with User Overlay
# ═══════════════════════════════════════════════════════════════════════════════

def load_catalog(user_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Load the appliance catalog, optionally merging a user-supplied overlay.

    The merge strategy is **shallow merge per appliance**: for each key in
    the user JSON, the user's value completely overrides the default.
    New appliances (keys not in the built-in catalog) are added as-is.

    This keeps the merge simple and predictable -- users who want to
    override a single field (e.g., change the IOS image path) can
    provide just that field and the rest falls through from defaults.

    Args:
        user_path: Path to a JSON file with user-defined appliance
                   overrides.  If ``None`` or the file does not exist,
                   the built-in catalog is returned unchanged.

    Returns:
        A new dict containing the merged catalog.  The built-in
        APPLIANCE_CATALOG is never mutated.
    """
    catalog = deepcopy(APPLIANCE_CATALOG)

    if user_path is None:
        return catalog

    if not os.path.isfile(user_path):
        logger.warning(
            "User catalog file '%s' not found — using built-in defaults",
            user_path,
        )
        return catalog

    try:
        with open(user_path, "r", encoding="utf-8") as fh:
            user_overrides: Dict[str, Dict[str, Any]] = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(
            "Failed to load user catalog '%s': %s — using built-in defaults",
            user_path, exc,
        )
        return catalog

    if not isinstance(user_overrides, dict):
        logger.error(
            "User catalog '%s' must be a JSON object (dict), got %s — "
            "using built-in defaults",
            user_path, type(user_overrides).__name__,
        )
        return catalog

    # Shallow-merge each appliance entry
    for name, overrides in user_overrides.items():
        if not isinstance(overrides, dict):
            logger.warning(
                "User catalog entry '%s' is not a dict — skipping", name,
            )
            continue

        if name in catalog:
            # Merge: user keys override default keys
            catalog[name].update(overrides)
            logger.info(
                "User catalog: merged overrides for appliance '%s' "
                "(%d keys overridden)", name, len(overrides),
            )
        else:
            # New appliance not in built-in catalog
            catalog[name] = deepcopy(overrides)
            logger.info(
                "User catalog: added new appliance '%s' (%d keys)",
                name, len(overrides),
            )

    return catalog


# ═══════════════════════════════════════════════════════════════════════════════
#  Appliance Lookup
# ═══════════════════════════════════════════════════════════════════════════════

def get_appliance(
    name: str,
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Look up an appliance definition by template name.

    The lookup is case-insensitive to tolerate variations in how the
    LLM or user capitalises the name (e.g., "cisco 7200" vs "Cisco 7200").

    Args:
        name:    Template name to look up (e.g., "Cisco 7200", "IOU L3").
        catalog: Catalog dict to search.  If ``None``, the built-in
                 APPLIANCE_CATALOG is used (without user overlay).

    Returns:
        A *deep copy* of the appliance definition dict, or ``None`` if
        no match is found.  The copy ensures callers can mutate the
        result without polluting the catalog.
    """
    if catalog is None:
        catalog = APPLIANCE_CATALOG

    # Exact match first (fast path)
    if name in catalog:
        return deepcopy(catalog[name])

    # Case-insensitive fallback
    name_lower = name.lower()
    for key, value in catalog.items():
        if key.lower() == name_lower:
            return deepcopy(value)

    logger.debug("Appliance lookup failed for '%s' — no match in catalog", name)
    return None