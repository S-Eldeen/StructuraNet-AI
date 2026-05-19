"""
constants/hardware.py — SINGLE SOURCE OF TRUTH for all hardware constants.

Every hardware fact (module lists, port counts, RAM defaults, slot configs,
compatibility matrices) used anywhere in the StructraNet pipeline MUST be
imported from this module.  No other module may define local copies.

Verified against GNS3 source code (v2.2.59):
  gns3-gui/gns3/modules/dynamips/settings.py  — ADAPTER_MATRIX, C2600_NMS,
        C3600_NMS, C3700_NMS, C7200_PAS, IO_C7200, PLATFORMS_DEFAULT_RAM,
        PLATFORMS_DEFAULT_NVRAM, CHASSIS
  gns3-gui/gns3/modules/dynamips/nodes/c1700.py, c2600.py, c2691.py,
        c3600.py, c3725.py, c3745.py, c7200.py
  gns3-server/gns3server/compute/dynamips/nodes/ (same platforms)
  gns3-server/gns3server/schemas/dynamips_template.py
  gns3-server/gns3server/compute/dynamips/__init__.py  — ADAPTER_MATRIX

Key corrections vs previous version:
  - C2600_NMS separated from C3600_NMS (C2600_NMS lacks NM-1D and NM-4T)
  - NM-1T REMOVED — it does NOT exist in the GNS3 server ADAPTER_MATRIX
    and produces invalid .gns3project files.  Serial on c2600 requires WIC
    slots (WIC-1T/WIC-2T) which are not modeled in this pipeline.
  - c1700/c2600: DYNAMIPS_SERIAL_MODULES max_slots set to 0; these platforms
    have no serial NM expansion (serial only via WIC, not modeled).
  - DYNAMIPS_COMPAT moved here from constants/validation.py (SSOT directive).
  - DYNAMIPS_MAX_PORTS computed dynamically from SSOT data (resolves the
    critical divergence between schema.py hardcoded values and main.py
    derived values).
  - RAM ranges: GNS3 has NO hardcoded RAM min/max per platform — RAM is an
    unbounded integer in the schema.  The ram_range values below are ADVISORY
    only, derived from real Cisco hardware specs and GNS3 recommended defaults.
  - DYNAMIPS_ADAPTER0_MAX_ETH_PORT moved here from schema.py.
  - PLATFORMS_DEFAULT_RAM / PLATFORMS_DEFAULT_NVRAM added from GNS3 source.
"""

from typing import Any, Dict, FrozenSet, List, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
#  GNS3 Module Compatibility Lists
#  Source: gns3-gui/settings.py (v2.2.59)
# ═══════════════════════════════════════════════════════════════════════════════

# c2600 slot 0 motherboard options (NOT Network Modules — these are
# the fixed motherboard chips that occupy slot 0 on c2600 platforms).
# Source: gns3-gui/settings.py  C2600_MOTHERBOARDS
C2600_MOTHERBOARDS: Tuple[str, ...] = ("C2600-MB-1E", "C2600-MB-2E", "C2600-MB-1FE", "C2600-MB-2FE")

# c2600 slot 1 NM options (SUBSET of C3600_NMS — lacks NM-1D and NM-4T)
# Source: gns3-gui/settings.py  C2600_NMS
C2600_NMS: Tuple[str, ...] = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW")

# c3620/c3640/c3660 NM options
# Source: gns3-gui/settings.py  C3600_NMS
C3600_NMS: Tuple[str, ...] = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW", "NM-4T")

# c2691/c3725/c3745 NM options
# Source: gns3-gui/settings.py  C3700_NMS
C3700_NMS: Tuple[str, ...] = ("NM-1FE-TX", "NM-4T", "NM-16ESW")

# c7200 Port Adapter options (slots 1-6)
# Source: gns3-gui/settings.py  C7200_PAS
C7200_PAS: Tuple[str, ...] = (
    "PA-A1", "PA-FE-TX", "PA-2FE-TX", "PA-GE",
    "PA-4T+", "PA-8T", "PA-4E", "PA-8E", "PA-POS-OC3",
)

# c7200 I/O controller options (slot 0 only)
# Source: gns3-gui/settings.py  IO_C7200
IO_C7200: Tuple[str, ...] = ("C7200-IO-FE", "C7200-IO-2FE", "C7200-IO-GE-E")


# ═══════════════════════════════════════════════════════════════════════════════
#  GNS3 Default RAM / NVRAM
#  Source: gns3-gui/settings.py PLATFORMS_DEFAULT_RAM, PLATFORMS_DEFAULT_NVRAM
#          gns3-server schemas/dynamips_template.py
# ═══════════════════════════════════════════════════════════════════════════════

PLATFORMS_DEFAULT_RAM: Dict[str, int] = {
    # Source: gns3-gui settings.py + dynamips_template.py
    "c1700": 160,
    "c2600": 160,
    "c2691": 192,
    "c3600": 192,   # applies to c3620/c3640/c3660
    "c3660": 192,   # alias — same as c3600 default
    "c3640": 128,   # conservative for lighter chassis
    "c3620": 128,   # conservative for lighter chassis
    "c3725": 128,
    "c3745": 256,
    "c7200": 512,
}

PLATFORMS_DEFAULT_NVRAM: Dict[str, int] = {
    # Source: gns3-gui settings.py PLATFORMS_DEFAULT_NVRAM (KB)
    "c1700": 128,
    "c2600": 128,
    "c2691": 256,
    "c3600": 256,
    "c3660": 256,   # alias — same as c3600 default
    "c3640": 256,   # alias — same as c3600 default
    "c3620": 256,   # alias — same as c3600 default
    "c3725": 256,
    "c3745": 256,
    "c7200": 512,
}

# Server-side Dynamips hypervisor minimums (lower than GUI recommended)
# Source: gns3-server compute/dynamips/nodes/cXXXX.py
DYNAMIPS_SERVER_MIN_RAM: Dict[str, int] = {
    "c1700": 64,
    "c2600": 64,
    "c2691": 128,
    "c3600": 128,
    "c3725": 128,
    "c3745": 128,
    "c7200": 256,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips Platform Compatibility Matrix (DYNAMIPS_COMPAT)
#  Moved from constants/validation.py — this is now the SSOT location.
#
#  Slot assignments verified against gns3-gui/settings.py ADAPTER_MATRIX.
#  RAM ranges are ADVISORY (GNS3 has no hardcoded min/max).
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_COMPAT: Dict[str, Dict] = {

    # ── c7200 ────────────────────────────────────────────────────────────────
    # Slot 0 = I/O controller (configurable). Slots 1-6 = PA modules.
    # Source: ADAPTER_MATRIX["c7200"][""] = {0: IO_C7200, 1-6: C7200_PAS}
    "c7200": {
        "builtin_ifaces": 0,   # depends on IO controller chosen
        "slots": {
            0: list(IO_C7200),
            1: list(C7200_PAS), 2: list(C7200_PAS), 3: list(C7200_PAS),
            4: list(C7200_PAS), 5: list(C7200_PAS), 6: list(C7200_PAS),
        },
        "valid_images": [r"c7200.*\.image", r"c7200.*\.bin"],
        "ram_range": (256, 1024),     # advisory; GNS3 enforces no upper bound
        "default_ram": PLATFORMS_DEFAULT_RAM["c7200"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c7200"],
    },

    # ── c3745 ────────────────────────────────────────────────────────────────
    # Slot 0 = GT96100-FE (fixed, 2 FE). Slots 1-4 = C3700_NMS.
    # NM-4E is NOT valid — it is C3600-only.
    "c3745": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["GT96100-FE"],
            1: list(C3700_NMS), 2: list(C3700_NMS),
            3: list(C3700_NMS), 4: list(C3700_NMS),
        },
        "valid_images": [r"c3745.*\.bin"],
        "ram_range": (128, 512),
        "default_ram": PLATFORMS_DEFAULT_RAM["c3745"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c3745"],
    },

    # ── c3725 ────────────────────────────────────────────────────────────────
    # Slot 0 = GT96100-FE (fixed, 2 FE). Slots 1-2 = C3700_NMS.
    "c3725": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["GT96100-FE"],
            1: list(C3700_NMS), 2: list(C3700_NMS),
        },
        "valid_images": [r"c3725.*\.bin"],
        "ram_range": (128, 512),
        "default_ram": PLATFORMS_DEFAULT_RAM["c3725"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c3725"],
    },

    # ── c3660 ────────────────────────────────────────────────────────────────
    # Slot 0 = Leopard-2FE (fixed, 2 FE). Slots 1-6 = C3600_NMS.
    # GNS3 stores this as platform="c3600", chassis="3660".
    "c3660": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["Leopard-2FE"],
            1: list(C3600_NMS), 2: list(C3600_NMS), 3: list(C3600_NMS),
            4: list(C3600_NMS), 5: list(C3600_NMS), 6: list(C3600_NMS),
        },
        "valid_images": [r"c3660.*\.bin"],
        "ram_range": (128, 512),
        "default_ram": PLATFORMS_DEFAULT_RAM["c3600"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c3600"],
    },

    # ── c3640 ────────────────────────────────────────────────────────────────
    # No fixed motherboard. All 4 slots configurable (C3600_NMS).
    # GNS3 stores this as platform="c3600", chassis="3640".
    "c3640": {
        "builtin_ifaces": 0,
        "slots": {
            0: list(C3600_NMS), 1: list(C3600_NMS),
            2: list(C3600_NMS), 3: list(C3600_NMS),
        },
        "valid_images": [r"c3640.*\.bin"],
        "ram_range": (128, 512),
        "default_ram": PLATFORMS_DEFAULT_RAM["c3600"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c3600"],
    },

    # ── c3620 ────────────────────────────────────────────────────────────────
    # No fixed motherboard. 2 NM slots (C3600_NMS).
    # GNS3 stores this as platform="c3600", chassis="3620".
    "c3620": {
        "builtin_ifaces": 0,
        "slots": {
            0: list(C3600_NMS), 1: list(C3600_NMS),
        },
        "valid_images": [r"c3620.*\.bin"],
        "ram_range": (64, 256),
        "default_ram": PLATFORMS_DEFAULT_RAM["c3600"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c3600"],
    },

    # ── c2691 ────────────────────────────────────────────────────────────────
    # Slot 0 = GT96100-FE (fixed, 2 FE). Slot 1 = C3700_NMS.
    "c2691": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["GT96100-FE"],
            1: list(C3700_NMS),
        },
        "valid_images": [r"c2691.*\.bin"],
        "ram_range": (128, 512),
        "default_ram": PLATFORMS_DEFAULT_RAM["c2691"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c2691"],
    },

    # ── c2600 ────────────────────────────────────────────────────────────────
    # Slot 0 = motherboard (varies by chassis). Slot 1 = C2600_NMS.
    # C2600_NMS = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW") — subset of C3600_NMS.
    # NM-4T and NM-1D are NOT valid for c2600.
    # Serial connectivity only via WIC slots (not modeled in this pipeline).
    "c2600": {
        "builtin_ifaces": 1,   # safe minimum; actual depends on chassis
        "slots": {
            0: list(C2600_MOTHERBOARDS),
            1: list(C2600_NMS),
        },
        "valid_images": [r"c2600.*\.bin"],
        "ram_range": (64, 256),
        "default_ram": PLATFORMS_DEFAULT_RAM["c2600"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c2600"],
    },

    # ── c1700 ────────────────────────────────────────────────────────────────
    # Slot 0 = C1700-MB-1FE (fixed). NO NM expansion slots.
    # Slot 1 on 1751/1760 = C1700-MB-WIC1 (fixed WIC carrier, not an NM slot).
    # Adding NM modules to c1700 is invalid — GNS3 will reject them.
    "c1700": {
        "builtin_ifaces": 1,
        "slots": {
            0: ["C1700-MB-1FE"],
            # No NM slots — c1700 has no Network Module bay
        },
        "valid_images": [r"c1700.*\.bin"],
        "ram_range": (128, 256),
        "default_ram": PLATFORMS_DEFAULT_RAM["c1700"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c1700"],
    },

    # ── c3600 (alias) ────────────────────────────────────────────────────────
    # GNS3 exports all c3620/c3640/c3660 with platform="c3600".
    # This alias maps to c3660 spec (most capable: Leopard-2FE + 6 NM slots).
    "c3600": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["Leopard-2FE", "GT96100-FE"],  # varies by chassis
            1: list(C3600_NMS), 2: list(C3600_NMS), 3: list(C3600_NMS),
            4: list(C3600_NMS), 5: list(C3600_NMS), 6: list(C3600_NMS),
        },
        "valid_images": [r"c3[0-9]+.*\.bin"],
        "ram_range": (64, 512),
        "default_ram": PLATFORMS_DEFAULT_RAM["c3600"],
        "default_nvram": PLATFORMS_DEFAULT_NVRAM["c3600"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips Ethernet Slot Module Defaults
#  Used by hw_config._inject_dynamips_slots for default module injection.
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_SLOT_MODULES: Dict[str, Dict[str, Any]] = {
    # c7200: slot 0 = IO controller (fixed), slots 1-6 = PA modules
    "c7200": {"module": "PA-8E",     "ports_per_module": 8,  "first_configurable": 1, "max_slots": 6},

    # c3745: slot 0 = GT96100-FE (fixed), slots 1-4 = C3700_NMS
    "c3745": {"module": "NM-1FE-TX", "ports_per_module": 1,  "first_configurable": 1, "max_slots": 4},

    # c3725: slot 0 = GT96100-FE (fixed), slots 1-2 = C3700_NMS
    "c3725": {"module": "NM-1FE-TX", "ports_per_module": 1,  "first_configurable": 1, "max_slots": 2},

    # c3660: slot 0 = Leopard-2FE (fixed), slots 1-6 = C3600_NMS
    "c3660": {"module": "NM-4E",     "ports_per_module": 4,  "first_configurable": 1, "max_slots": 6},

    # c3640: no fixed slot 0, slots 0-3 = C3600_NMS
    "c3640": {"module": "NM-4E",     "ports_per_module": 4,  "first_configurable": 0, "max_slots": 4},

    # c3620: no fixed slot 0, slots 0-1 = C3600_NMS
    "c3620": {"module": "NM-4E",     "ports_per_module": 4,  "first_configurable": 0, "max_slots": 2},

    # c2691: slot 0 = GT96100-FE (fixed), slot 1 = C3700_NMS
    "c2691": {"module": "NM-1FE-TX", "ports_per_module": 1,  "first_configurable": 1, "max_slots": 1},

    # c2600: slot 0 = motherboard (fixed), slot 1 = C2600_NMS
    "c2600": {"module": "NM-1E",     "ports_per_module": 1,  "first_configurable": 1, "max_slots": 1},

    # c1700: NO NM slots — only WIC subslots (not modeled)
    "c1700": {"module": "NM-1FE-TX", "ports_per_module": 1,  "first_configurable": 1, "max_slots": 0},

    # c3600 alias: maps to c3660 spec
    "c3600": {"module": "NM-4E",     "ports_per_module": 4,  "first_configurable": 1, "max_slots": 6},
}

DYNAMIPS_FALLBACK: Dict[str, Any] = {
    "module": "PA-8E",
    "ports_per_module": 8,
    "first_configurable": 1,
    "max_slots": 4,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips Serial Slot Module Defaults
#
#  CRITICAL: c2600 and c1700 have NO serial NM modules.
#  C2600_NMS = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW") — no serial!
#  c1700 has no NM slots at all.
#  Serial on these platforms requires WIC slots (WIC-1T/WIC-2T) which are
#  NOT modeled in this pipeline.  max_slots=0 prevents invalid NM injection.
#
#  NM-1T has been REMOVED — it does NOT exist in the GNS3 server's
#  ADAPTER_MATRIX and produces invalid .gns3project files.
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_SERIAL_MODULES: Dict[str, Dict[str, Any]] = {
    "c7200":  {"module": "PA-4T+",  "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3745":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3725":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 2},
    "c3660":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3640":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 0, "max_slots": 4},
    "c3620":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 0, "max_slots": 2},
    "c2691":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 1},
    # c2600: C2600_NMS has no serial module. Serial only via WIC (not modeled).
    "c2600":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 0},
    # c1700: no NM slots. Serial only via WIC (not modeled).
    "c1700":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 0},
    "c3600":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
}

DYNAMIPS_SERIAL_FALLBACK: Dict[str, Any] = {
    "module": "PA-4T+",
    "ports_per_module": 4,
    "first_configurable": 1,
    "max_slots": 4,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Built-in (motherboard) Ethernet port counts per platform
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_BUILTIN_PORTS: Dict[str, int] = {
    "c7200": 1,   # C7200-IO-FE in slot 0 (default I/O controller)
    "c3745": 2,   # GT96100-FE in slot 0
    "c3725": 2,   # GT96100-FE in slot 0
    "c3660": 2,   # Leopard-2FE in slot 0
    "c3640": 0,   # no fixed slot 0
    "c3620": 0,   # no fixed slot 0
    "c2691": 2,   # GT96100-FE in slot 0
    "c2600": 1,   # C2600-MB-1E/1FE (safe minimum; actual depends on chassis)
    "c1700": 1,   # C1700-MB-1FE
    "c3600": 2,   # alias — c3660 is most capable (Leopard-2FE = 2 ports)
}
DYNAMIPS_BUILTIN_DEFAULT = 1

DYNAMIPS_BUILTIN_SERIAL_PORTS: Dict[str, int] = {
    "c7200": 0, "c3745": 0, "c3725": 0, "c3660": 0, "c3640": 0,
    "c3620": 0, "c2691": 0, "c2600": 0, "c1700": 0, "c3600": 0,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Module interface details (name → prefix + port count)
#  Used for IOS interface name resolution.
#
#  Only includes modules that exist in the GNS3 server's ADAPTER_MATRIX.
#  NM-1T has been REMOVED — it is not a valid GNS3 module.
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    # C7200 PA modules
    "PA-8E":          {"prefix": "Ethernet",        "count": 8},
    "PA-4E":          {"prefix": "Ethernet",        "count": 4},
    "PA-FE-TX":       {"prefix": "FastEthernet",    "count": 1},
    "PA-2FE-TX":      {"prefix": "FastEthernet",    "count": 2},
    "PA-GE":          {"prefix": "GigabitEthernet", "count": 1},
    "PA-A1":          {"prefix": "ATM",             "count": 1},
    "PA-POS-OC3":     {"prefix": "POS",             "count": 1},
    # C3600/C3700 NM modules
    "NM-4E":          {"prefix": "Ethernet",        "count": 4},
    "NM-1E":          {"prefix": "Ethernet",        "count": 1},
    "NM-1FE-TX":      {"prefix": "FastEthernet",    "count": 1},
    "NM-16ESW":       {"prefix": "FastEthernet",    "count": 16},
    "NM-4T":          {"prefix": "Serial",          "count": 4},
    # Motherboard chips
    "GT96100-FE":     {"prefix": "FastEthernet",    "count": 2},
    "Leopard-2FE":    {"prefix": "FastEthernet",    "count": 2},
    # C7200 I/O controllers (slot 0 only)
    "C7200-IO-FE":    {"prefix": "FastEthernet",    "count": 1},
    "C7200-IO-2FE":   {"prefix": "FastEthernet",    "count": 2},
    "C7200-IO-GE-E":  {"prefix": "GigabitEthernet", "count": 1},
    # C1700 motherboard
    "C1700-MB-1FE":   {"prefix": "FastEthernet",    "count": 1},
    # C1700 WIC carrier (slot 1 on 1751/1760) — no direct ports
    "C1700-MB-WIC1":  {"prefix": None,              "count": 0},
    # C2600 motherboards
    "C2600-MB-1E":    {"prefix": "Ethernet",        "count": 1},
    "C2600-MB-2E":    {"prefix": "Ethernet",        "count": 2},
    "C2600-MB-1FE":   {"prefix": "FastEthernet",    "count": 1},
    "C2600-MB-2FE":   {"prefix": "FastEthernet",    "count": 2},
    # C7200 Serial modules
    "PA-4T+":         {"prefix": "Serial",          "count": 4},
    "PA-8T":          {"prefix": "Serial",          "count": 8},
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Built-in interface details per platform (for IOS name resolution)
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_BUILTIN_INTERFACE_DETAILS: Dict[str, Dict[str, Any]] = {
    "c7200": {"prefix": "FastEthernet",  "count": 1},
    "c3745": {"prefix": "FastEthernet",  "count": 2},
    "c3725": {"prefix": "FastEthernet",  "count": 2},
    "c3660": {"prefix": "FastEthernet",  "count": 2},
    "c3640": {"prefix": None,            "count": 0},
    "c3620": {"prefix": None,            "count": 0},
    "c2691": {"prefix": "FastEthernet",  "count": 2},
    "c2600": {"prefix": "FastEthernet",  "count": 1},
    "c1700": {"prefix": "FastEthernet",  "count": 1},
    "c3600": {"prefix": "FastEthernet",  "count": 2},  # alias
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips adapter 0 max Ethernet port number per platform
#  (Moved from schema.py — used for port assignment validation)
#  -1 means platform has NO built-in Ethernet on adapter 0 (c3640, c3620).
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_ADAPTER0_MAX_ETH_PORT: Dict[str, int] = {
    "c7200": 0,    # C7200-IO-FE: 1 port → max port_number = 0
    "c3745": 1,    # GT96100-FE: 2 ports → max port_number = 1
    "c3725": 1,    # GT96100-FE: 2 ports → max port_number = 1
    "c3660": 1,    # Leopard-2FE: 2 ports → max port_number = 1
    "c3640": -1,   # no fixed slot 0
    "c3620": -1,   # no fixed slot 0
    "c2691": 1,    # GT96100-FE: 2 ports → max port_number = 1
    "c2600": 0,    # C2600-MB-1FE: 1 port → max port_number = 0 (safe min)
    "c1700": 0,    # C1700-MB-1FE: 1 port → max port_number = 0
    "c3600": 1,    # alias
}
DYNAMIPS_ADAPTER0_DEFAULT_MAX: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
#  DYNAMIPS_MAX_PORTS — dynamically computed from SSOT
#
#  Maximum Ethernet links per platform = builtin + (default_module_ports * configurable_slots)
#  This resolves the critical divergence where schema.py had hardcoded wrong values.
# ═══════════════════════════════════════════════════════════════════════════════

DYNAMIPS_MAX_PORTS: Dict[str, int] = {
    platform: (
        DYNAMIPS_BUILTIN_PORTS.get(platform, DYNAMIPS_BUILTIN_DEFAULT)
        + (cfg["ports_per_module"] * cfg["max_slots"])
    )
    for platform, cfg in DYNAMIPS_SLOT_MODULES.items()
}
# Result: c7200=49, c3745=6, c3725=4, c3660=26, c3640=16, c3620=8,
#         c2691=3, c2600=2, c1700=1, c3600=26


# ═══════════════════════════════════════════════════════════════════════════════
#  VM / Docker adapter caps
# ═══════════════════════════════════════════════════════════════════════════════

MAX_ADAPTERS: Dict[str, int] = {
    "qemu": 275,
    "docker": 99,
    "virtualbox": 8,
    "vmware": 10,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  IOU Constants
# ═══════════════════════════════════════════════════════════════════════════════

IOU_PORTS_PER_ADAPTER: int = 4
IOU_MAX_ADAPTERS: int = 16
IOU_DEFAULT_ETH_ADAPTERS: int = 2
IOU_DEFAULT_SER_ADAPTERS: int = 2


# ═══════════════════════════════════════════════════════════════════════════════
#  Switch / Hub / Immutable node constants
# ═══════════════════════════════════════════════════════════════════════════════

SWITCH_HUB_DEFAULT_PORTS: int = 8

IMMUTABLE_PORT_COUNT: Dict[str, int] = {"vpcs": 1, "traceng": 1, "nat": 1}
IMMUTABLE_TYPES: FrozenSet[str] = frozenset(IMMUTABLE_PORT_COUNT.keys())
MAPPING_BASED_TYPES: FrozenSet[str] = frozenset(["frame_relay_switch", "atm_switch"])

L2_CONCENTRATOR_TYPES: FrozenSet[str] = frozenset(["ethernet_switch", "ethernet_hub"])
L3_ROUTER_TYPES: FrozenSet[str] = frozenset(["dynamips", "iou", "qemu", "docker", "virtualbox", "vmware"])
NO_CONFIG_TYPES: FrozenSet[str] = frozenset([
    "ethernet_switch", "ethernet_hub", "nat", "cloud", "frame_relay_switch", "atm_switch",
])

# Module → port count lookup (derived from DYNAMIPS_MODULE_INTERFACES)
MODULE_PORT_COUNT: Dict[str, int] = {
    name: info["count"]
    for name, info in DYNAMIPS_MODULE_INTERFACES.items()
}
