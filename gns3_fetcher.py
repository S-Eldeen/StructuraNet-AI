"""
Structranet AI — GNS3 Template Fetcher

Polls the local GNS3 REST API for installed templates (the real hardware inventory).
No hardcoded profiles — the pipeline adapts to whatever is installed.
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
GNS3_URL = os.getenv("GNS3_SERVER_URL", "http://127.0.0.1:3080")
logger = logging.getLogger("structranet.fetcher")

# Well-known port counts for built-in GNS3 node types
BUILTIN_PORTS = {
    "ethernet_switch": 8, "ethernet_hub": 8, "vpcs": 1,
    "cloud": 1, "nat": 1, "traceng": 1,
    "frame_relay_switch": 8, "atm_switch": 8,
}

# Practical GNS3-safe maximum Ethernet port counts per Dynamips platform.
# These are NOT theoretical slot limits — they reflect the actual PCI bus
# bandwidth constraint in Dynamips emulation.  The c7200 will CRASH if you
# inject more than 2 PA-8E cards (each 8 ports).  Conservative = safe.
# Source: GNS3 community testing + Dynamips PCI bus model
DYNAMIPS_MAX_PORTS = {
    "c7200": 3,    # PCI bus crash with >2 PA-8E; safe = 1 builtin + 1 PA
    "c3745": 6,    # NM-4E is lighter; safe = 2 builtin + 1 NM-4E
    "c3725": 6,    # Same NM-4E; safe = 2 builtin + 1 NM-4E
    "c3660": 5,    # 1 builtin + 1 NM-4E
    "c3640": 4,    # No builtin eth + 1 NM-4E
    "c3620": 4,    # Same as c3640
    "c2691": 6,    # 2 builtin + 1 NM-4E
    "c2600": 2,    # 1 builtin + 1 NM-1E
    "c1700": 2,    # 1 builtin + 1 NM-1E
}

def _get_port_count(template: dict) -> Optional[int]:
    """Best-effort port count from a template's data.

    For expandable types (dynamips, iou), returns the MAXIMUM possible
    port count after all expansion slots are filled.  This gives the AI
    agent an upper bound so it doesn't assign more links than the node
    can physically support.
    """
    ttype = template.get("template_type") or template.get("type", "")

    # Built-in types have known counts
    if ttype in BUILTIN_PORTS:
        return BUILTIN_PORTS[ttype]

    # QEMU/Docker/VirtualBox/VMware templates declare adapter count
    if "adapters" in template and isinstance(template["adapters"], int):
        return template["adapters"]

    # Dynamips: compute max ports from platform + slot expansion
    if ttype == "dynamips":
        platform = template.get("platform", "").lower()
        # Try to extract platform from template name if not in properties
        if not platform:
            name = template.get("name", "").lower()
            # Match both "c3745" and bare "3745" in names like "Cisco 3745"
            for p in ("c7200", "c3745", "c3725", "c3660", "c3640", "c3620",
                      "c2691", "c2600", "c1700"):
                if p in name or p[1:] in name:  # "c3745" or "3745"
                    platform = p
                    break
        if platform in DYNAMIPS_MAX_PORTS:
            return DYNAMIPS_MAX_PORTS[platform]
        # Fallback: conservative default for unknown dynamips platforms
        return 3

    # IOU: practical limit (4 builtin + 1 slot is safe in GNS3)
    if ttype == "iou":
        return 8

    return None

class FetcherError(Exception):
    """Raised when the GNS3 server is unreachable or returns an error."""
    pass


def fetch_available_templates(retries: int = 3, timeout: float = 10.0) -> list[dict]:
    """
    Fetch the list of available GNS3 templates.

    Returns a list of dicts, each with:
        name, gns3_type, template_id, builtin, category, port_count
    """
    url = f"{GNS3_URL}/v2/templates"
    last_err = None

    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()

            inventory = []
            for t in resp.json():
                if "name" not in t or not t.get("template_id"):
                    continue
                gns3_type = t.get("template_type") or t.get("type") or "unknown"
                inventory.append({
                    "name": t["name"],
                    "gns3_type": gns3_type,
                    "template_id": t["template_id"],
                    "builtin": t.get("builtin", False),
                    "category": t.get("category", "unknown"),
                    "port_count": _get_port_count(t),
                })

            logger.info("Found %d device(s).", len(inventory))
            return inventory

        except requests.exceptions.ConnectionError as e:
            last_err = e
            logger.warning("Connection failed (attempt %d/%d)", attempt, retries)
        except requests.exceptions.Timeout as e:
            last_err = e
            logger.warning("Timeout (attempt %d/%d)", attempt, retries)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise FetcherError(f"GNS3 API error: {e}") from e
            last_err = e
            logger.warning("HTTP error (attempt %d/%d)", attempt, retries)

    raise FetcherError(
        f"Cannot reach GNS3 at {GNS3_URL} after {retries} attempts. Is the server running?"
    ) from last_err


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")
    try:
        for d in fetch_available_templates():
            print(f"  {d['name']:20s}  type={d['gns3_type']:20s}  ports={d['port_count']}")
    except FetcherError as e:
        print(f"Error: {e}")
