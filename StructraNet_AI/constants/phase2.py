from typing import Dict, FrozenSet, Tuple

# Derive SOFTWARE_CONFIG_KEYS from the SSOT FILE_CONFIG_TRIPLETS in constants/gns3.py
# plus the non-file-based config keys (start_command, environment).
# This ensures phase2.py stays in sync with the exporter's config key list.
from constants.gns3 import FILE_CONFIG_TRIPLETS

SOFTWARE_CONFIG_KEYS: FrozenSet[str] = frozenset(
    k for k, _, _ in FILE_CONFIG_TRIPLETS
) | {"start_command", "environment"}

ALLOWED_VALUE_TYPES: Dict[str, Tuple[type, ...]] = {
    "startup_config_content": (str,),
    "private_config_content": (str,),
    "startup_script": (str,),
    "start_command": (str,),
    "environment": (dict, str),
}

