"""
Structranet AI — Hybrid Assembler

Deploys an AI-generated topology to GNS3 via the REST API.
Handles template_id resolution, UUID mapping, grid layout, port validation,
and a pre-flight "Defense in Depth" check.

GNS3 API v2 endpoints used:
  POST   /v2/projects                              → Create project
  GET    /v2/projects                              → List projects
  DELETE /v2/projects/{pid}                        → Delete project
  POST   /v2/projects/{pid}/templates/{tid}        → Create node from template (Path A)
  POST   /v2/projects/{pid}/nodes                  → Create node directly (Path B fallback)
  GET    /v2/projects/{pid}/nodes                  → List nodes / poll status
  PUT    /v2/projects/{pid}/nodes/{nid}            → Update node properties (merge semantics)
  POST   /v2/projects/{pid}/nodes/{nid}/files/{path} → Write file to node's virtual FS
  POST   /v2/projects/{pid}/nodes/start            → Start all nodes
  POST   /v2/projects/{pid}/links                  → Create link
  POST   /v2/projects/{pid}/drawings               → Add drawing (title)

Path A (template-based) is preferred — it merges `properties` with template
defaults, so hardware modules (slot1, adapters, ports_mapping) are applied
at creation time.

CRITICAL — Software config injection uses TWO channels:
  1. Properties PUT:  start_command, environment, extra_hosts, extra_volumes,
     kernel_command_line, usage  →  accepted by the properties endpoint.
  2. Files API POST:  startup_config_content, private_config_content,
     startup_script  →  REJECTED by the properties endpoint (400 Bad Request).
     Must be pushed directly to the node's virtual filesystem via:
       Dynamips/IOU/QEMU: POST .../nodes/{uuid}/files/startup-config.cfg
       Dynamips/IOU:      POST .../nodes/{uuid}/files/private-config.cfg
       VPCS:              POST .../nodes/{uuid}/files/startup.vpc

Path B (direct creation) is a fallback for built-in types only (ethernet_switch,
ethernet_hub, vpcs, cloud, nat). It will NOT work for template-dependent types
(dynamips, qemu, iou, docker) which need disk image info from a template.
"""

import argparse
import json
import sys
import time
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from xml.sax.saxutils import escape


try:
    import requests
except ImportError:
    print("[ERROR] 'requests' not installed. Run: pip install requests")
    sys.exit(1)

logger = logging.getLogger("structranet.assembler")

# -- Terminal colors --
_USE_COLOUR = sys.platform != "win32"

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def OK(t):   logger.info(t);   print(_c("32",   f"  [OK]   {t}"))
def WARN(t): logger.warning(t); print(_c("33",   f"  [WARN] {t}"))
def ERR(t):  logger.error(t);   print(_c("31",   f"  [ERR]  {t}"))
def INFO(t): logger.info(t);    print(_c("36",   f"  [ . ]  {t}"))
def HEAD(t): logger.info(t);    print(_c("1;34", f"\n{'='*56}\n  {t}\n{'='*56}"))


class DeploymentError(Exception):
    """Critical deployment failure."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#  GNS3 API Client
# ═══════════════════════════════════════════════════════════════════════════════

class GNS3Client:
    """Minimal REST client for GNS3 v2 API with retry and error body extraction."""

    def __init__(self, host: str = "localhost", port: int = 3080, retries: int = 2, timeout: int = 15):
        self.base = f"http://{host}:{port}/v2"
        self.session = requests.Session()
        self.retries = retries
        self.timeout = timeout

    def _request(self, method: str, path: str, data=None):
        url = self.base + path
        last_err = None
        for attempt in range(1, self.retries + 1):
            try:
                if method == "GET":
                    r = self.session.get(url, timeout=self.timeout)
                elif method == "POST":
                    r = self.session.post(url, json=data, timeout=max(self.timeout, 30))
                elif method == "PUT":
                    r = self.session.put(url, json=data, timeout=max(self.timeout, 30))
                elif method == "DELETE":
                    r = self.session.delete(url, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                r.raise_for_status()
                return r.json() if r.content and r.status_code != 204 else {}
            except requests.exceptions.HTTPError as e:
                # Extract GNS3 error body for debugging (400/409/etc. carry messages)
                detail = ""
                if e.response is not None:
                    try:
                        body = e.response.json()
                        detail = body.get("message", body.get("error", str(body)))
                    except Exception:
                        detail = e.response.text[:200] if e.response.text else ""
                    if 400 <= e.response.status_code < 500:
                        # Client errors: don't retry, raise with detail
                        raise DeploymentError(
                            f"GNS3 {e.response.status_code} on {method} {path}: {detail}"
                        ) from e
                last_err = e
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_err = e
            if attempt < self.retries:
                time.sleep(0.5 * attempt)
        if last_err:
            raise last_err
        raise DeploymentError(f"Request to {url} failed (retries={self.retries})")

    def post_raw(self, path: str, content: str, timeout: int = 15):
        """POST raw (non-JSON) string content to the GNS3 API.

        Used for the Files API endpoints which accept plain text bodies,
        not JSON.  The standard post() method sends json=data which would
        double-encode string content.

        Args:
            path: API path (e.g. "/projects/{pid}/nodes/{uuid}/files/startup-config.cfg")
            content: Raw string content to write.
            timeout: Request timeout in seconds.
        """
        url = self.base + path
        r = self.session.post(url, data=content, timeout=timeout)
        r.raise_for_status()
        return r.text if r.content else ""
    
    def get(self, path):    return self._request("GET", path)
    def post(self, path, data=None): return self._request("POST", path, data)
    def put(self, path, data=None):  return self._request("PUT", path, data)
    def delete(self, path): return self._request("DELETE", path)


# ═══════════════════════════════════════════════════════════════════════════════
#  Template Lookup
# ═══════════════════════════════════════════════════════════════════════════════

def _build_lookup(inventory: list) -> dict:
    """
    Build template_id lookup from inventory.

    Keys: (name, gns3_type) -> template_id  (composite, specific)
          name -> template_id                (simple, fallback)
    """
    lookup = {}
    for dev in (inventory or []):
        tid = dev.get("template_id", "")
        if not tid:
            continue
        lookup[(dev["name"], dev["gns3_type"])] = tid
        if dev["name"] not in lookup:
            lookup[dev["name"]] = tid
    return lookup

# ═══════════════════════════════════════════════════════════════════════════════
#  File-Based Software Config → GNS3 Virtual Filesystem Mapping
# ═══════════════════════════════════════════════════════════════════════════════
#
# GNS3 rejects startup_config_content, private_config_content, and
# startup_script from the properties PUT endpoint entirely (400 Bad Request).
# The ONLY way to inject these is via the Files API, which writes directly
# to the node's virtual filesystem.
#
# Source: gns3server/controller/node.py — parse_node_response() deletes
# these keys from self._properties after forwarding; the compute-level
# schemas do not accept them via the properties dict.
#
# Mapping: (software_key, node_type) → virtual filesystem path
_FILE_CONFIG_PATHS: dict[tuple[str, str], str] = {
    # ── IOS startup-config (dynamips, iou, qemu IOS images) ──
    ("startup_config_content", "dynamips"): "startup-config.cfg",
    ("startup_config_content", "iou"):      "startup-config.cfg",
    ("startup_config_content", "qemu"):     "startup-config.cfg",
    # ── IOS private-config (dynamips, iou) ──
    ("private_config_content", "dynamips"): "private-config.cfg",
    ("private_config_content", "iou"):      "private-config.cfg",
    # ── VPCS startup script ──
    ("startup_script", "vpcs"):             "startup.vpc",
}


def _push_file_configs(
    client: GNS3Client,
    project_id: str,
    node_uuid: str,
    node_type: str,
    file_configs: dict,
    node_name: str,
) -> None:
    """Push file-based software configs to a node via the GNS3 Files API.

    GNS3 strictly rejects startup_config_content and startup_script from
    the properties PUT endpoint.  The Files API writes directly to the
    node's virtual filesystem, which the emulator reads on startup.

    Endpoints:
      Dynamips/IOU/QEMU: POST .../nodes/{uuid}/files/startup-config.cfg
      Dynamips/IOU:      POST .../nodes/{uuid}/files/private-config.cfg
      VPCS:              POST .../nodes/{uuid}/files/startup.vpc
    """
    for key, content in file_configs.items():
        file_path = _FILE_CONFIG_PATHS.get((key, node_type))

        if file_path is None:
            WARN(f"No file mapping for '{key}' on {node_type} node "
                 f"'{node_name}' — config dropped")
            continue

        try:
            client.post_raw(
                f"/projects/{project_id}/nodes/{node_uuid}/files/{file_path}",
                content=content,
            )
            OK(f"Pushed {key} → '{node_name}' via Files API "
               f"({file_path}, {len(content)} chars)")
        except Exception as e:
            WARN(f"Failed to push {key} to '{node_name}' via Files API: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Pre-flight Check (Defense in Depth)
# ═══════════════════════════════════════════════════════════════════════════════

def _preflight_check(ai_nodes: list, inventory: list) -> list:
    """Verify that every node's template_name exists in the GNS3 inventory.

    This is the "Defense in Depth" pre-flight check. The orchestrator's
    validate_against_inventory() catches most issues early, but this check
    runs RIGHT BEFORE deployment — the last line of defense against stale
    inventory or manually edited JSON files.

    Returns a list of (node_name, template_name, error) tuples for failures.
    """
    if not inventory:
        WARN("No inventory provided — pre-flight check cannot validate template_names")
        return []

    available = {d["name"] for d in inventory}
    name_to_type = {d["name"]: d.get("gns3_type", "") for d in inventory}
    failures = []

    for node in ai_nodes:
        tname = node.get("template_name", "")
        name = node.get("name", "?")
        ntype = node.get("node_type", "")

        if not tname:
            failures.append((name, tname, "missing template_name"))
            continue

        if tname not in available:
            failures.append((name, tname, f"template '{tname}' not found in GNS3 inventory"))
            continue

        inv_type = name_to_type.get(tname, "")
        if inv_type and inv_type != ntype:
            # Not a hard failure — the assembler auto-corrects node_type
            WARN(f"Pre-flight: '{name}' node_type={ntype} but template "
                 f"'{tname}' is {inv_type} — will auto-correct")

    return failures


# ═══════════════════════════════════════════════════════════════════════════════
#  Grid Layout
# ═══════════════════════════════════════════════════════════════════════════════

# Role priority: lower number = higher on canvas
ROLE_PRIORITY = {
    "cloud": 0, "nat": 0,
    "router": 1, "dynamips": 1, "qemu": 1, "iou": 1,
    "switch": 2, "ethernet_switch": 2, "ethernet_hub": 2,
    "frame_relay_switch": 2, "atm_switch": 2,
    "endpoint": 3, "vpcs": 3, "traceng": 3, "docker": 3,
    "virtualbox": 3, "vmware": 3,
}
DEFAULT_PRIORITY = 4


def _grid_positions(nodes: list, inventory: list = None) -> dict:
    """Compute (x, y) for each node, grouped by role."""
    cat_map = {}
    if inventory:
        for d in inventory:
            cat_map[d["name"]] = d.get("category", "")

    scored = []
    for n in nodes:
        ntype = n.get("node_type", "")
        tname = n.get("template_name", "")
        cat = cat_map.get(tname, "")
        priority = ROLE_PRIORITY.get(cat, ROLE_PRIORITY.get(ntype, DEFAULT_PRIORITY))
        nid = n.get("node_id")
        if nid:
            scored.append((priority, nid, n))
    scored.sort(key=lambda x: x[0])

    positions = {}
    col, row, last_role = 0, 0, None
    for role, nid, _ in scored:
        if last_role is not None and role != last_role:
            row += 1
            col = 0
        last_role = role
        positions[nid] = (col * 250 - 400, row * 200 - 200)
        col += 1
        if col >= 4:
            col = 0
            row += 1
    return positions


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Deployment
# ═══════════════════════════════════════════════════════════════════════════════

def deploy_hybrid_topology(client: GNS3Client, data: dict, args, inventory: list = None):
    """
    Deploy a topology from AI-generated JSON to GNS3.

    Args:
        client: GNS3Client instance.
        data: Topology dict with 'name' and 'topology' keys.
              Follows schema.GNS3Project structure:
              { "name": str, "topology": { "nodes": [...], "links": [...] } }
        args: Namespace with 'overwrite' and 'start' flags.
        inventory: Device inventory for template_id resolution
                   (from gns3_fetcher.fetch_available_templates).
    """
    topo = data.get("topology", {})
    proj_name = data.get("name", "AI_Generated_Network")
    ai_nodes = topo.get("nodes", [])
    ai_links = topo.get("links", [])

    if not ai_nodes:
        raise DeploymentError("No nodes in topology — nothing to deploy.")

    # ── Pre-flight Check (Defense in Depth) ─────────────────────────────────
    HEAD("Pre-flight — Template Validation")
    preflight_failures = _preflight_check(ai_nodes, inventory)
    if preflight_failures:
        for name, tname, err in preflight_failures:
            ERR(f"  '{name}': {err}")
        # Hard failure: cannot deploy nodes whose templates don't exist
        raise DeploymentError(
            f"Pre-flight check failed: {len(preflight_failures)} node(s) have "
            f"invalid template_names. Fix the topology or install missing templates."
        )
    OK("All template_names validated against GNS3 inventory")

    lookup = _build_lookup(inventory)
    positions = _grid_positions(ai_nodes, inventory)

    deployed_nodes, failed_nodes = [], []
    deployed_links, failed_links = [], []
    node_id_map = {}       # logical node_id -> GNS3 UUID
    node_ports = {}        # GNS3 UUID -> port list from API
    used_ports = {}        # GNS3 UUID -> set of (adapter, port) already linked
    project_id = None

    # ── Step 1: Create Project ────────────────────────────────────────────────
    HEAD("Step 1 - Project Setup")
    try:
        existing = next((p for p in client.get("/projects") if p["name"] == proj_name), None)
        if existing:
            if getattr(args, "overwrite", False):
                client.delete(f"/projects/{existing['project_id']}")
                OK("Deleted existing project")
                time.sleep(0.5)
            else:
                raise DeploymentError(f"Project '{proj_name}' already exists. Use --overwrite.")
        project = client.post("/projects", {"name": proj_name})
        project_id = project["project_id"]
        OK(f"Project '{proj_name}' created (ID: {project_id})")
    except DeploymentError:
        raise
    except Exception as e:
        raise DeploymentError(f"Failed to create project: {e}") from e

    # ── Step 2: Deploy Nodes ──────────────────────────────────────────────────
    HEAD("Step 2 - Deploying Nodes")
    for n in ai_nodes:
        nid = n.get("node_id")
        name = n.get("name", "Unknown")
        ntype = n.get("node_type", "")
        tname = n.get("template_name")
        compute_id = n.get("compute_id", "local")  # Use node's compute_id, not hardcoded

        if not nid:
            WARN(f"Skipping '{name}': missing node_id")
            failed_nodes.append((name, "missing node_id"))
            continue

        x, y = positions.get(nid, (0, 0))

        # Resolve template_id: composite key first, then simple key, then type-fallback
        tid = None
        if tname:
            tid = lookup.get((tname, ntype)) or lookup.get(tname)
        if not tid and lookup:
            for dev in (inventory or []):
                if dev.get("gns3_type") == ntype and dev.get("template_id"):
                    tid = dev["template_id"]
                    WARN(f"Type-fallback for '{name}': using template '{dev['name']}'")
                    break

        # Fix node_type if it conflicts with the template's actual type
        if tid and inventory:
            inv_dev = next((d for d in inventory if d.get("template_id") == tid), None)
            if inv_dev and inv_dev.get("gns3_type") != ntype:
                WARN(f"Correcting node_type for '{name}': '{ntype}' -> '{inv_dev['gns3_type']}'")
                ntype = inv_dev["gns3_type"]

        try:
            # ── Extract file-based software configs BEFORE any API calls ──
            # GNS3 rejects these from the properties PUT endpoint (400).
            # They must be pushed via the Files API instead.
            # pop() removes them from n["properties"] in-place so they
            # are NOT sent via PUT in the next step.
            file_configs: dict = {}
            for key in ("startup_config_content",
                        "private_config_content",
                        "startup_script"):
                value = n.get("properties", {}).pop(key, None)
                if value is not None:
                    file_configs[key] = value

            if tid:
                # ── Path A: Template-based creation (preferred) ──────────
                # TEMPLATE_USAGE_SCHEMA only accepts: x, y, name, compute_id.
                # All node-type-specific properties come from the template.
                payload = {
                    "x": x, "y": y,
                    "compute_id": compute_id,
                    "name": name,
                    # "properties": {},
                }
                result = client.post(
                    f"/projects/{project_id}/templates/{tid}", payload
                )
                uuid = result["node_id"]

                # Apply remaining properties via PUT.
                # After popping file-based configs, n["properties"] contains:
                #   - Hardware/compute keys (slot1, adapters, ports_mapping, ram, ...)
                #   - Property-based software keys (start_command, environment,
                #     extra_hosts, extra_volumes, kernel_command_line, usage)
                # Both categories are safe for the properties PUT endpoint.
                # GNS3 uses MERGE semantics — only provided keys are updated.
                remaining_props = n.get("properties")
                if remaining_props:
                    try:
                        client.put(
                            f"/projects/{project_id}/nodes/{uuid}",
                            {"properties": remaining_props},
                        )
                    except Exception as e:
                        WARN(f"Failed to apply properties to '{name}': {e}")

                # Refresh port list after PUT — the expanded hardware may have
                # added new ports that weren't in the initial POST response.
                try:
                    refreshed = client.get(f"/projects/{project_id}/nodes/{uuid}")
                    new_ports = refreshed.get("ports", [])
                    if len(new_ports) > len(result.get("ports", [])):
                        logger.info(
                            "Node '%s': port count updated after PUT: %d -> %d",
                            name, len(result.get("ports", [])), len(new_ports),
                        )
                        result = refreshed
                except Exception:
                    pass

                # Push file-based configs via Files API.
                # This MUST happen after the properties PUT so that the node's
                # virtual filesystem is fully initialised.
                if file_configs:
                    _push_file_configs(
                        client, project_id, uuid, ntype,
                        file_configs, name,
                    )

            else:
                # ── Path B: Direct node creation (fallback) ──────────────
                # WARNING: Only works reliably for BUILT-IN types
                # (ethernet_switch, ethernet_hub, vpcs, cloud, nat).
                # Template-dependent types (dynamips, qemu, iou, docker)
                # need disk image info from a template and will likely fail.
                if lookup:
                    WARN(f"No template_id for '{name}' — direct creation "
                         f"may fail for '{ntype}'")

                payload = {
                    "name": name,
                    "node_type": ntype,
                    "compute_id": compute_id,
                    "x": x,
                    "y": y,
                    "properties": n.get("properties", {}),
                }

                result = client.post(
                    f"/projects/{project_id}/nodes", payload
                )
                uuid = result["node_id"]

                # Push file-based configs for direct-created nodes too
                if file_configs:
                    _push_file_configs(
                        client, project_id, uuid, ntype,
                        file_configs, name,
                    )

            node_id_map[nid] = uuid
            ports = result.get("ports", [])
            node_ports[uuid] = ports
            used_ports[uuid] = set()
            deployed_nodes.append(name)

            # Log properties forwarding status
            props = n.get("properties", {})
            prop_keys = list(props.keys()) if props else []
            sw_keys = list(file_configs.keys()) if file_configs else []
            OK(f"'{name}' ({ntype}) -> {uuid[:8]}... "
               f"[{len(ports)} ports, hw_props: {prop_keys or 'empty'}, "
               f"file_configs: {sw_keys or 'none'}]")

            # Heuristic wait: QEMU/Docker/IOU/Dynamips take longer to init
            time.sleep(0.8 if ntype in ("qemu", "docker", "iou", "dynamips") else 0.2)

        except Exception as e:
            failed_nodes.append((name, str(e)))
            WARN(f"Failed to deploy '{name}': {e}")
            
    if not deployed_nodes:
        raise DeploymentError("All nodes failed to deploy — aborting.")

    # ── Step 3: Wait for Nodes to Settle ──────────────────────────────────────
    HEAD("Step 3 - Waiting for nodes")
    settled = False
    poll_fails = 0
    for _ in range(15):  # max ~30s
        try:
            statuses = client.get(f"/projects/{project_id}/nodes")
            poll_fails = 0
            if all(s.get("status") in ("stopped", "started", "suspended") for s in statuses):
                if len(statuses) >= len(ai_nodes):
                    settled = True
                    break
        except Exception:
            poll_fails += 1
            if poll_fails >= 3:
                break
        time.sleep(2)

    OK("Nodes settled" if settled else "Timeout — proceeding anyway")

    # Refresh port info — always replace (GNS3 may refine port metadata after init)
    try:
        for rn in client.get(f"/projects/{project_id}/nodes"):
            rid = rn.get("node_id")
            rports = rn.get("ports", [])
            if rid in node_ports:
                node_ports[rid] = rports
    except Exception:
        pass

    # ── Step 4: Deploy Links ──────────────────────────────────────────────────
    HEAD("Step 4 - Deploying Links")

    def _find_port(real_id, adapter, port, link_type="ethernet"):
        """Validate requested port, or find next available compatible one.

        Resolution order:
          1. Exact match: (adapter, port) exists and not yet used
          2. Fallback: next unused port with compatible link_type
          3. Error: no available port
        """
        ports = node_ports.get(real_id, [])
        used = used_ports.get(real_id, set())
        key = (adapter, port)

        # 1. Exact match — port exists and not yet used
        if key not in used:
            for p in ports:
                if p.get("adapter_number") == adapter and p.get("port_number") == port:
                    return {"node_id": real_id, "adapter_number": adapter, "port_number": port}

        # 2. Fallback — find next unused port with matching link_type
        for p in ports:
            pk = (p.get("adapter_number", 0), p.get("port_number", 0))
            if pk in used:
                continue
            plt = p.get("link_type")
            if plt is None or plt == link_type:
                WARN(f"Port ({adapter}/{port}) not available on {real_id[:8]}..., "
                     f"using fallback ({pk[0]}/{pk[1]})")
                return {"node_id": real_id, "adapter_number": pk[0], "port_number": pk[1]}

        raise DeploymentError(
            f"No available port on node {real_id[:8]}... for link creation "
            f"(requested {adapter}/{port}, {len(ports)} ports total, "
            f"{len(used)} already used)"
        )

    for lnk in ai_links:
        eps = lnk.get("nodes", [])
        if len(eps) < 2:
            failed_links.append(("bad link", "fewer than 2 endpoints"))
            continue

        ep0, ep1 = eps[0], eps[1]
        rid0 = node_id_map.get(ep0.get("node_id"))
        rid1 = node_id_map.get(ep1.get("node_id"))

        if not rid0 or not rid1:
            missing = ep0.get("node_id") if not rid0 else ep1.get("node_id")
            failed_links.append((f"missing {missing}", "node was not deployed"))
            continue

        ltype = lnk.get("link_type", "ethernet")
        try:
            vp0 = _find_port(rid0, ep0.get("adapter_number", 0), ep0.get("port_number", 0), ltype)
            vp1 = _find_port(rid1, ep1.get("adapter_number", 0), ep1.get("port_number", 0), ltype)
        except DeploymentError as e:
            failed_links.append((f"{ep0.get('node_id')}<->{ep1.get('node_id')}", str(e)))
            WARN(f"Port error: {e}")
            continue

        used_ports.setdefault(rid0, set()).add((vp0["adapter_number"], vp0["port_number"]))
        used_ports.setdefault(rid1, set()).add((vp1["adapter_number"], vp1["port_number"]))

        try:
            client.post(f"/projects/{project_id}/links",
                        {"nodes": [vp0, vp1], "link_type": ltype})
            deployed_links.append(1)
            OK(f"{ep0.get('node_id')} <-> {ep1.get('node_id')} ({ltype})")
            time.sleep(0.2)
        except Exception as e:
            failed_links.append((f"{ep0.get('node_id')}<->{ep1.get('node_id')}", str(e)))
            WARN(f"Link failed: {e}")

    # ── Step 5: Start Nodes (optional) ────────────────────────────────────────
    if getattr(args, "start", True):
        HEAD("Step 5 - Starting Nodes")
        try:
            client.post(f"/projects/{project_id}/nodes/start")
            OK("Start command sent")
        except Exception as e:
            WARN(f"Start failed: {e}")

    # ── Step 6: Add Visual Title (Drawing) ────────────────────────────────────
    try:
        safe_name = escape(proj_name)
        svg_content = f'<svg><text font-size="30" font-weight="bold" fill="blue">{safe_name}</text></svg>'
        client.post(f"/projects/{project_id}/drawings", {
            "x": -400, "y": -300, "z": 1, "svg": svg_content
        })
        OK("Visual title added to canvas")
    except Exception as e:
        WARN(f"Could not add title (ignoring): {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    HEAD("Summary")
    OK(f"Nodes: {len(deployed_nodes)}/{len(ai_nodes)}  |  Links: {len(deployed_links)}/{len(ai_links)}")
    for name, err in failed_nodes:
        ERR(f"  Node '{name}': {err}")
    for desc, err in failed_links:
        ERR(f"  Link {desc}: {err}")

    if failed_nodes and len(failed_nodes) > len(ai_nodes) * 0.5:
        ERR("More than half the nodes failed — consider deleting the project and retrying.")

    if not failed_nodes and not failed_links:
        OK("Network deployed successfully!")

    return {"project_id": project_id, "nodes": len(deployed_nodes), "links": len(deployed_links),
            "failed_nodes": len(failed_nodes), "failed_links": len(failed_links)}



# ═══════════════════════════════════════════════════════════════════════════════
#  CLI (standalone mode)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Structranet AI - Assembler")
    parser.add_argument("topology_file", help="AI-generated JSON topology")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=3080, type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--start", action="store_true", default=True,
                        help="Start nodes after deployment (default: True)")
    parser.add_argument("--no-start", action="store_false", dest="start",
                        help="Don't start nodes after deployment")
    parser.add_argument("--inventory", default=None, metavar="JSON_FILE",
                        help="GNS3 inventory JSON (from gns3_fetcher). "
                             "Without this, template_id resolution and "
                             "pre-flight validation are disabled.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")
    HEAD("Structranet AI - Assembler")

    # Load topology
    try:
        with open(args.topology_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        ERR(f"Cannot load topology: {e}")
        sys.exit(1)

    # Load inventory if provided
    inventory = None
    if args.inventory:
        try:
            with open(args.inventory) as f:
                inventory = json.load(f)
            INFO(f"Loaded inventory: {len(inventory)} device(s)")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            WARN(f"Cannot load inventory: {e} — proceeding without template resolution")

    try:
        deploy_hybrid_topology(GNS3Client(args.host, args.port), data, args, inventory)
    except DeploymentError as e:
        ERR(str(e))
        sys.exit(1)
    except Exception as e:
        ERR(f"Fatal: {e}")
        sys.exit(1)
