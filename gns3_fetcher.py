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
    "ethernet_switch": 8, "ethernet_hub": 8, "vpcs": 1, "traceng": 1,
    "cloud": 1, "nat": 1, "frame_relay_switch": 8, "atm_switch": 8,
}

def _get_port_count(template: dict) -> Optional[int]:
    """Best-effort port count from a template's data."""
    ttype = template.get("template_type") or template.get("type", "")

    # Built-in types have known counts
    if ttype in BUILTIN_PORTS:
        return BUILTIN_PORTS[ttype]

    # QEMU/Docker/VirtualBox/VMware templates declare adapter count
    if "adapters" in template and isinstance(template["adapters"], int):
        return template["adapters"]

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
