from typing import Dict, FrozenSet, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
#  Node-type taxonomy
#  Moved from constants/validation.py — these are GNS3 node type enums,
#  not validation limits.  They define the set of valid GNS3 node types.
# ═══════════════════════════════════════════════════════════════════════════════

VALID_NODE_TYPES: FrozenSet[str] = frozenset([
    "cloud", "nat", "ethernet_hub", "ethernet_switch",
    "frame_relay_switch", "atm_switch",
    "docker", "dynamips", "vpcs", "traceng",
    "virtualbox", "vmware", "iou", "qemu",
])

BUILTIN_NODE_TYPES: FrozenSet[str] = frozenset([
    "vpcs", "ethernet_switch", "ethernet_hub",
    "cloud", "nat", "traceng",
    "frame_relay_switch", "atm_switch",
])

APPLIANCE_NODE_TYPES: FrozenSet[str] = frozenset([
    "dynamips", "iou", "qemu", "docker", "virtualbox", "vmware",
])

GNS3_REVISION: int = 9
GNS3_VERSION: str = "2.2.0"
SCENE_WIDTH: int = 2000
SCENE_HEIGHT: int = 1000

# NOTE: FILE_CONFIG_PATHS was removed (V4.4) — it duplicated information
# already in FILE_CONFIG_TRIPLETS and was never imported anywhere.
# Use FILE_CONFIG_TRIPLETS as the single source of truth.

FILE_CONFIG_TRIPLETS: List[Tuple[str, str, str]] = [
    ("startup_config_content", "dynamips", "configs/startup-config.cfg"),
    ("startup_config_content", "iou", "startup-config.cfg"),
    ("startup_config_content", "qemu", "configs/startup-config.cfg"),
    ("private_config_content", "dynamips", "configs/private-config.cfg"),
    ("private_config_content", "iou", "private-config.cfg"),
    ("startup_script", "vpcs", "startup.vpc"),
]

SOFTWARE_CONFIG_KEYS: FrozenSet[str] = frozenset(
    k for k, _, _ in FILE_CONFIG_TRIPLETS
) | {"start_command", "environment"}

SYMBOL: Dict[str, str] = {
    "dynamips": ":/symbols/router.svg",
    "iou": ":/symbols/router.svg",
    "qemu": ":/symbols/router.svg",
    "docker": ":/symbols/docker_guest.svg",
    "vpcs": ":/symbols/vpcs_guest.svg",
    "traceng": ":/symbols/traceng.svg",
    "ethernet_switch": ":/symbols/ethernet_switch.svg",
    "ethernet_hub": ":/symbols/hub.svg",
    "cloud": ":/symbols/cloud.svg",
    "nat": ":/symbols/nat.svg",
    "virtualbox": ":/symbols/vbox_guest.svg",
    "vmware": ":/symbols/vmware_guest.svg",
    "frame_relay_switch": ":/symbols/frame_relay_switch.svg",
    "atm_switch": ":/symbols/atm_switch.svg",
}

NODE_SIZE: Dict[str, Tuple[int, int]] = {
    "dynamips": (65, 65),
    "iou": (65, 65),
    "qemu": (65, 65),
    "docker": (65, 65),
    "vpcs": (65, 65),
    "traceng": (65, 65),
    "ethernet_switch": (65, 65),
    "ethernet_hub": (65, 65),
    "cloud": (95, 65),
    "nat": (95, 65),
    "virtualbox": (65, 65),
    "vmware": (65, 65),
    "frame_relay_switch": (65, 65),
    "atm_switch": (65, 65),
}

CONSOLE_TYPE: Dict[str, Optional[str]] = {
    "dynamips": "telnet",
    "iou": "telnet",
    "qemu": "telnet",
    "docker": "telnet",
    "vpcs": "telnet",
    "traceng": None,
    "ethernet_switch": None,
    "ethernet_hub": None,
    "cloud": None,
    "nat": None,
    "virtualbox": "telnet",
    "vmware": "telnet",
    "frame_relay_switch": None,
    "atm_switch": None,
}

LABEL_STYLE: str = (
    "font-family: TypeWriter;"
    "font-size: 10.0;"
    "font-weight: bold;"
    "fill: #000000;"
    "fill-opacity: 1.0;"
)

ROLE_PRIORITY: Dict[str, int] = {
    "cloud": 0, "nat": 0,
    "dynamips": 1, "iou": 1, "qemu": 1, "virtualbox": 1, "vmware": 1,
    "ethernet_switch": 2, "ethernet_hub": 2,
    "frame_relay_switch": 2, "atm_switch": 2,
    "vpcs": 3, "traceng": 3, "docker": 3,
}
DEFAULT_ROLE_PRIORITY: int = 4

PORT_NAME_FORMAT: Dict[str, str] = {
    "dynamips": "FastEthernet{0}/{1}",
    "iou": "Ethernet{0}/{1}",
    "qemu": "eth{0}",
    "docker": "eth{0}",
    "vpcs": "Ethernet{0}",
    "traceng": "Ethernet{0}",
    "ethernet_switch": "Ethernet{0}",
    "ethernet_hub": "Ethernet{0}",
    "virtualbox": "eth{0}",
    "vmware": "eth{0}",
    "cloud": "Cloud{0}",
    "nat": "nat{0}",
    "frame_relay_switch": "{0}",
    "atm_switch": "{0}",
}

PORT_SEGMENT_SIZE: Dict[str, int] = {
    "dynamips": 0,
    "iou": 4,
    "qemu": 0,
    "docker": 0,
    "vpcs": 0,
    "traceng": 0,
    "ethernet_switch": 0,
    "ethernet_hub": 0,
    "virtualbox": 0,
    "vmware": 0,
}
DEFAULT_PORT_SEGMENT_SIZE: int = 0

GRID_COLUMN_SPACING: int = 200
GRID_ROW_SPACING: int = 150
GRID_COLUMNS_PER_ROW: int = 5
GRID_X_OFFSET: int = -400
GRID_Y_OFFSET: int = -200

# Key stamped onto the topology dict after apply_switch_port_patches runs.
# Checked by config_agent.run_phase2() to avoid running the patch twice.
VLAN_PATCHED_KEY: str = "__vlan_patched__"

