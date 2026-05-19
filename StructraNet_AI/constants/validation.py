"""
constants/validation.py — Structural Validation Constants for Structranet AI

This module re-exports constants from the canonical SSOT modules
(constants/hardware.py and constants/gns3.py) for backward compatibility.

All hardware facts (module lists, port counts, RAM defaults, slot configs,
compatibility matrices) are defined in constants/hardware.py.
All node-type taxonomy and GNS3 format constants are in constants/gns3.py.

Previously this module contained duplicate definitions that could drift
from the SSOT.  It has been refactored to import and re-export from
the canonical sources, eliminating the drift risk.

Verified against:
  gns3-gui/gns3/modules/dynamips/settings.py  ADAPTER_MATRIX
  GNS3 Dynamips README
  GNS3 official docs (cisco-ios-images-for-dynamips)
"""

# ═══════════════════════════════════════════════════════════════════════════════
#  Re-exports from SSOT modules
#  Import from constants.validation is kept for backward compatibility,
#  but all definitions come from the single source of truth.
# ═══════════════════════════════════════════════════════════════════════════════

# Node-type taxonomy — SSOT: constants/gns3.py
from constants.gns3 import (                         # noqa: F401
    VALID_NODE_TYPES,
    BUILTIN_NODE_TYPES,
    APPLIANCE_NODE_TYPES,
)

# Dynamips compatibility matrix — SSOT: constants/hardware.py
from constants.hardware import (                     # noqa: F401
    C2600_MOTHERBOARDS,
    C2600_NMS,
    C3600_NMS,
    C3700_NMS,
    C7200_PAS,
    IO_C7200,
    DYNAMIPS_COMPAT,
    DYNAMIPS_MODULE_INTERFACES,
    MODULE_PORT_COUNT,
)
