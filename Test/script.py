#!/usr/bin/env python3
"""
gns3_create_project.py
======================
Reads a .gns3 topology JSON file and creates the full project
on a running local GNS3 server via its REST API.

Usage:
    python gns3_create_project.py topology.gns3 [options]

Options:
    --host      GNS3 server host   (default: localhost)
    --port      GNS3 server port   (default: 3080)
    --user      HTTP auth username (optional)
    --password  HTTP auth password (optional)
    --start     Auto-start all nodes after creation
    --overwrite Delete existing project with same name before creating

Hardcoded rules applied automatically:
    1. ALL nodes -> compute_id = "local"  (no GNS3 VM needed)
    2. ALL dynamips nodes -> chassis "c7200" with default adapters
    3. virtualbox / vmware nodes -> converted to vpcs
    4. qemu nodes that were on a remote 'vm' compute -> converted to vpcs
    5. Duplicate console ports are resolved automatically (auto-increment)

Requirements:
    pip install requests
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("[ERROR] 'requests' not found. Run:  pip install requests")
    sys.exit(1)

import os as _os
_USE_COLOUR = _os.name != "nt"

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def OK(t):   print(_c("32",   f"  [OK]   {t}"))
def WARN(t): print(_c("33",   f"  [WARN] {t}"))
def ERR(t):  print(_c("31",   f"  [ERR]  {t}"))
def INFO(t): print(_c("36",   f"  [ . ]  {t}"))
def HEAD(t): print(_c("1;34", f"\n{'='*56}\n  {t}\n{'='*56}"))


# --------------------------------------------------------------------------- #
#  GNS3 REST API CLIENT                                                        #
# --------------------------------------------------------------------------- #
class GNS3Client:
    def __init__(self, host, port, user=None, password=None):
        self.base    = f"http://{host}:{port}/v2"
        self.session = requests.Session()
        if user:
            self.session.auth = HTTPBasicAuth(user, password)

    def _url(self, path):
        return f"{self.base}{path}"

    def get(self, path, **kw):
        r = self.session.get(self._url(path), timeout=15, **kw)
        r.raise_for_status()
        return r.json()

    def post(self, path, data=None, **kw):
        r = self.session.post(self._url(path), json=data, timeout=30, **kw)
        r.raise_for_status()
        # Some endpoints (e.g. /nodes/start) return 204 No Content
        if r.status_code == 204 or not r.content:
            return {}
        return r.json()

    def delete(self, path, **kw):
        r = self.session.delete(self._url(path), timeout=15, **kw)
        r.raise_for_status()

    def ping(self):
        return self.get("/version").get("version", "unknown")


# --------------------------------------------------------------------------- #
#  LOAD & VALIDATE JSON                                                        #
# --------------------------------------------------------------------------- #
def load_topology(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text.startswith("{"):
        text = "{" + text
    if not text.endswith("}"):
        text = text + "}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        ERR(f"JSON parse error: {e}")
        sys.exit(1)
    if "topology" not in data:
        ERR("Missing 'topology' field. Is this a valid .gns3 file?")
        sys.exit(1)
    return data


# --------------------------------------------------------------------------- #
#  NORMALIZE NODES                                                             #
# --------------------------------------------------------------------------- #
def normalize_nodes(nodes_def):
    """
    Rule 1 - Force compute_id = 'local' on every node.
    Rule 2 - Every dynamips node gets chassis c7200 with default adapters.
    Rule 3 - virtualbox / vmware nodes -> vpcs.
    Rule 4 - qemu nodes that lived on remote 'vm' compute -> vpcs.
    Rule 5 - Deduplicate console ports; each node gets a unique port >= 5000.
    """
    used_consoles = set()
    next_port = [5000]

    def alloc_console(preferred):
        try:
            port = int(preferred) if preferred else next_port[0]
        except (TypeError, ValueError):
            port = next_port[0]
        while port in used_consoles:
            next_port[0] += 1
            port = next_port[0]
        used_consoles.add(port)
        if port >= next_port[0]:
            next_port[0] = port + 1
        return port

    result = []
    for n in nodes_def:
        node             = dict(n)
        original_compute = node.get("compute_id", "local")
        original_type    = node.get("node_type", "")

        # Rule 1
        node["compute_id"] = "local"
        if original_compute != "local":
            INFO(f"Node '{node.get('name')}': compute '{original_compute}' -> 'local'")

        # Rule 2
        if original_type == "dynamips":
            props      = dict(node.get("properties", {}))
            src_chassis = props.get("platform", "unknown")
            node_name   = node.get("name", "?")

            # ----------------------------------------------------------
            # CHASSIS PROFILES
            # Defines which slot keys and WIC keys each platform supports,
            # and the default adapters to assign on conversion.
            # Add a new entry here whenever a new IOS image is available.
            # ----------------------------------------------------------
            CHASSIS_PROFILES = {
                # ---- c7200 ----
                # Slots  : slot0..slot6   (NO wic slots at all)
                # slot0  : must be an IO card (C7200-IO-FE or C7200-IO-2FE)
                "c7200": {
                    "slot_keys": ["slot0","slot1","slot2","slot3",
                                  "slot4","slot5","slot6"],
                    "wic_keys":  [],          # c7200 has NO wic slots
                    "defaults": {
                        "slot0": "C7200-IO-FE",
                        "slot1": "PA-FE-TX",
                        "slot2": "PA-FE-TX",
                        "slot3": "PA-FE-TX",
                    },
                    "ram":   256,
                    "nvram": 512,
                    "image": "c7200-adventerprisek9-mz.153-3.XB12.image",
                    "idlepc": "",             # set if known
                },

                # ---- c3745 ----
                # Slots  : slot0..slot2
                # WICs   : wic0..wic2  (on the motherboard WIC bay)
                "c3745": {
                    "slot_keys": ["slot0","slot1","slot2"],
                    "wic_keys":  ["wic0","wic1","wic2"],
                    "defaults": {
                        "slot0": "GT96100-FE",   # built-in dual FE (required)
                        "slot1": "NM-16ESW",
                        "slot2": "NM-4T",
                        "wic0":  "WIC-2T",
                        "wic1":  "WIC-1T",
                    },
                    "ram":   256,
                    "nvram": 256,
                    "image": "",              # fill if you have c3745 image
                    "idlepc": "0x60a80f7c",
                },

                # ---- c3725 ----
                "c3725": {
                    "slot_keys": ["slot0","slot1","slot2"],
                    "wic_keys":  ["wic0","wic1","wic2"],
                    "defaults": {
                        "slot0": "GT96100-FE",
                        "slot1": "NM-1FE-TX",
                        "wic0":  "WIC-2T",
                    },
                    "ram":   128,
                    "nvram": 256,
                    "image": "",
                    "idlepc": "",
                },

                # ---- c2691 ----
                "c2691": {
                    "slot_keys": ["slot0","slot1"],
                    "wic_keys":  ["wic0","wic1","wic2"],
                    "defaults": {
                        "slot0": "GT96100-FE",
                        "wic0":  "WIC-2T",
                    },
                    "ram":   192,
                    "nvram": 256,
                    "image": "",
                    "idlepc": "",
                },

                # ---- c1700 ----
                "c1700": {
                    "slot_keys": ["slot0"],
                    "wic_keys":  ["wic0","wic1"],
                    "defaults": {
                        "slot0": "C1700-MB-1FE",
                        "wic0":  "WIC-2T",
                    },
                    "ram":   128,
                    "nvram": 32,
                    "image": "",
                    "idlepc": "",
                },

                # ---- c2600 (generic) ----
                "c2600": {
                    "slot_keys": ["slot0","slot1"],
                    "wic_keys":  ["wic0","wic1","wic2"],
                    "defaults": {
                        "slot0": "C2600-MB-1FE",
                        "wic0":  "WIC-2T",
                    },
                    "ram":   128,
                    "nvram": 256,
                    "image": "",
                    "idlepc": "",
                },
            }

            # Save original chassis so port remapper can use it later
            node["_original_chassis"] = src_chassis

            # ----------------------------------------------------------
            # Decide target chassis:
            #   - If src_chassis already has a known profile AND an image
            #     is available -> keep it as-is (no conversion needed).
            #   - Otherwise -> convert to c7200 (our available image).
            # ----------------------------------------------------------
            src_profile = CHASSIS_PROFILES.get(src_chassis)
            if src_profile and src_profile.get("image"):
                # Source chassis has an available IOS image -> keep it
                target_chassis  = src_chassis
                target_profile  = src_profile
                converted       = False
            else:
                # Convert to c7200
                target_chassis  = "c7200"
                target_profile  = CHASSIS_PROFILES["c7200"]
                converted       = (src_chassis != "c7200")

            # ----------------------------------------------------------
            # Wipe ALL slot/WIC keys that exist in the SOURCE profile
            # (prevents alien modules from leaking into the target chassis)
            # Also wipe any keys from the target profile for a clean slate.
            # ----------------------------------------------------------
            all_keys_to_clear = set()
            for p in CHASSIS_PROFILES.values():
                all_keys_to_clear.update(p["slot_keys"])
                all_keys_to_clear.update(p["wic_keys"])
            for k in all_keys_to_clear:
                props.pop(k, None)

            # ----------------------------------------------------------
            # Apply target chassis settings
            # ----------------------------------------------------------
            props["platform"] = target_chassis

            # Slot defaults: only set slots that exist in target profile
            for k, v in target_profile["defaults"].items():
                if k in target_profile["slot_keys"] or k in target_profile["wic_keys"]:
                    props[k] = v

            # Null-out remaining valid-but-unused slots (clean API payload)
            for k in target_profile["slot_keys"]:
                props.setdefault(k, None)
            for k in target_profile["wic_keys"]:
                props.setdefault(k, None)

            # RAM / NVRAM
            props["ram"]   = props.get("ram")   or target_profile["ram"]
            props["nvram"] = props.get("nvram")  or target_profile["nvram"]

            # Image
            if target_profile.get("image"):
                props["image"] = target_profile["image"]
                props.pop("image_md5sum", None)   # md5 of old image is wrong

            # idlepc
            if target_profile.get("idlepc"):
                props.setdefault("idlepc", target_profile["idlepc"])

            node["properties"] = props

            if converted:
                INFO(f"Node '{node_name}': dynamips '{src_chassis}' -> '{target_chassis}' "
                     f"(no local image for {src_chassis}, using {target_chassis})")
            else:
                INFO(f"Node '{node_name}': dynamips '{target_chassis}' kept "
                     f"(image available)")

        # Rules 3 & 4
        vm_types = {"virtualbox", "vmware"}
        convert = (
            original_type in vm_types
            or (original_type == "qemu" and original_compute == "vm")
        )
        if convert:
            INFO(f"Node '{node.get('name')}': '{original_type}' -> 'vpcs' (no local support)")
            node["node_type"]  = "vpcs"
            node["properties"] = {}
            node["symbol"]     = ":/symbols/vpcs_guest.svg"

        # Rule 5
        node["console"] = alloc_console(node.get("console"))

        result.append(node)

    return result


# --------------------------------------------------------------------------- #
#  CREATE PROJECT                                                              #
# --------------------------------------------------------------------------- #
def create_project(client, data, args):
    topo      = data["topology"]
    proj_name = data.get("name", "ImportedTopology")
    links_def = topo.get("links", [])
    drawings  = topo.get("drawings", [])

    HEAD("Step 0 - Normalizing Nodes")
    nodes_def = normalize_nodes(topo.get("nodes", []))
    OK(f"Normalized {len(nodes_def)} nodes: all local, dynamips -> c7200")

    HEAD("Step 1 - Project")
    existing_projects = client.get("/projects")
    existing = next((p for p in existing_projects if p["name"] == proj_name), None)

    if existing:
        if args.overwrite:
            WARN(f"Deleting existing project '{proj_name}' (--overwrite)")
            client.delete(f"/projects/{existing['project_id']}")
            OK("Deleted")
        else:
            WARN(f"Project '{proj_name}' already exists.")
            answer = input("      Overwrite? [y/N] ").strip().lower()
            if answer == "y":
                client.delete(f"/projects/{existing['project_id']}")
                OK("Deleted")
            else:
                INFO("Adding to existing project.")
                project_id = existing["project_id"]
                try:
                    client.post(f"/projects/{project_id}/open")
                except Exception:
                    pass
                return _populate(client, project_id, nodes_def, links_def, drawings, args)

    payload = {
        "name":         proj_name,
        "scene_height": data.get("scene_height", 1000),
        "scene_width":  data.get("scene_width",  2000),
        "auto_start":   data.get("auto_start",   False),
        "auto_close":   data.get("auto_close",   True),
        "auto_open":    data.get("auto_open",    False),
    }
    src_pid = data.get("project_id", "")
    if src_pid and len(src_pid) == 36:
        payload["project_id"] = src_pid

    project    = client.post("/projects", payload)
    project_id = project["project_id"]
    OK(f"Created project '{proj_name}' -> ID: {project_id}")

    return _populate(client, project_id, nodes_def, links_def, drawings, args)


# --------------------------------------------------------------------------- #
#  PORT REMAPPING                                                              #
#  Each chassis uses a different port-numbering scheme.                        #
#  When a node is converted to a different chassis we must translate the       #
#  original (adapter, port) pair to the equivalent on the target chassis.      #
# --------------------------------------------------------------------------- #

# For every source chassis, map (adapter, flat_port) -> logical interface index
# Then map that index to the target chassis (adapter, port).
#
# GNS3 port numbering per chassis:
#
#  c3745  (FLAT — all ports on adapter 0):
#    slot0  GT96100-FE  2 ports  -> a=0, p=0..1
#    slot1  NM-16ESW   16 ports  -> a=0, p=16..31
#    slot2  NM-4T       4 ports  -> a=0, p=32..35
#    wic0   WIC-2T      2 ports  -> a=0, p=?  (serial, rarely linked)
#
#  c7200  (ADAPTER-BASED — each slot = one adapter):
#    slot0  C7200-IO-FE  1 port  -> a=0, p=0
#    slot1  PA-FE-TX     1 port  -> a=1, p=0
#    slot2  PA-FE-TX     1 port  -> a=2, p=0
#    slot3  PA-FE-TX     1 port  -> a=3, p=0
#
# Translation strategy:
#   We assign a "logical index" (0-based, sequential across all FE ports)
#   to each port on the source chassis, then map that index to the
#   corresponding (adapter, port) on the target chassis.
#   If the source port is out of range for the target we WARN and skip.

def _build_c3745_port_index():
    """
    Returns a dict  (adapter, port) -> logical_index  for c3745 flat layout.
    logical_index 0..N maps to FastEthernet ports in slot order.
    """
    idx = {}
    # slot0 GT96100-FE: 2 FE ports  -> a=0, p=0..1  -> logical 0,1
    for p in range(2):
        idx[(0, p)] = p                    # logical 0,1
    # slot1 NM-16ESW: 16 ports -> a=0, p=16..31  -> logical 2..17
    for p in range(16):
        idx[(0, 16 + p)] = 2 + p          # logical 2..17
    # slot2 NM-4T: 4 serial -> a=0, p=32..35  -> logical 18..21  (serial)
    for p in range(4):
        idx[(0, 32 + p)] = 18 + p
    return idx

def _build_c7200_port_index():
    """
    Returns a dict  logical_index -> (adapter, port)  for c7200.
    slot0 C7200-IO-FE = 1 port, slot1..3 PA-FE-TX = 1 port each.
    """
    # logical 0 -> a=0,p=0 ; logical 1 -> a=1,p=0 ; ...
    return {i: (i, 0) for i in range(4)}

# Pre-build the tables
_C3745_TO_IDX  = _build_c3745_port_index()
_C7200_FROM_IDX = _build_c7200_port_index()

# PORT_REMAP_TABLE[src_chassis][dst_chassis] = callable(adapter, port) -> (adapter, port) | None
def _remap_c3745_to_c7200(adapter, port):
    logical = _C3745_TO_IDX.get((adapter, port))
    if logical is None:
        return None                        # unknown source port
    result = _C7200_FROM_IDX.get(logical)
    return result                          # None if out of range on c7200

PORT_REMAP = {
    ("c3745", "c7200"): _remap_c3745_to_c7200,
    # Add more pairs here as needed, e.g. ("c3725", "c7200"): ...
}

def remap_endpoint(ep, nodes_def):
    """
    Given a link endpoint dict and the (already-normalized) nodes_def list,
    return (adapter_number, port_number) — possibly remapped if the node
    was converted from one chassis to another.
    """
    adapter = ep.get("adapter_number", 0)
    port    = ep.get("port_number",    0)
    node_id = ep.get("node_id", "")

    node = next((n for n in nodes_def if n.get("node_id") == node_id), None)
    if node is None:
        return adapter, port

    src = node.get("_original_chassis")   # set during normalization
    dst = node.get("properties", {}).get("platform")

    if src and dst and src != dst:
        fn = PORT_REMAP.get((src, dst))
        if fn:
            result = fn(adapter, port)
            if result is not None:
                new_a, new_p = result
                if (new_a, new_p) != (adapter, port):
                    INFO(f"  Port remap [{node.get('name')}] "
                         f"({src}) a{adapter}/p{port} -> "
                         f"({dst}) a{new_a}/p{new_p}")
                return new_a, new_p
            else:
                WARN(f"  Port remap [{node.get('name')}] "
                     f"({src}) a{adapter}/p{port} has NO equivalent on {dst} — link skipped")
                return None, None   # signal to skip this link

    return adapter, port



def _populate(client, project_id, nodes_def, links_def, drawings, args):

    HEAD("Step 2 - Nodes")
    node_id_map = {}

    for n in nodes_def:
        payload = {
            "name":       n.get("name", "Node"),
            "node_type":  n.get("node_type", "vpcs"),
            "compute_id": "local",
            "x":          n.get("x", 0),
            "y":          n.get("y", 0),
            "z":          n.get("z", 1),
            "properties": n.get("properties", {}),
            "console":    n.get("console"),
        }
        for opt in ("symbol", "label", "width", "height",
                    "port_name_format", "port_segment_size", "first_port_name"):
            val = n.get(opt)
            if val is not None:
                payload[opt] = val

        orig_id = n.get("node_id", "")
        if orig_id:
            payload["node_id"] = orig_id

        try:
            result = client.post(f"/projects/{project_id}/nodes", payload)
            new_id = result["node_id"]
            node_id_map[orig_id] = new_id
            OK(f"Node '{payload['name']}' ({payload['node_type']}) "
               f"console={payload['console']} -> {new_id}")
        except requests.HTTPError as e:
            WARN(f"Node '{payload['name']}' FAILED: {e.response.text[:150]}")
            node_id_map[orig_id] = orig_id

    HEAD("Step 3 - Waiting 10s for nodes to settle")
    for i in range(10, 0, -1):
        print(f"\r  [ . ]  Waiting... {i}s ", end="", flush=True)
        time.sleep(1)
    print()
    OK("Done waiting — proceeding to links")

    HEAD("Step 4 - Links")

    for lnk in links_def:
        endpoints = lnk.get("nodes", [])
        if len(endpoints) < 2:
            WARN(f"Link {lnk.get('link_id','')} skipped (< 2 endpoints)")
            continue

        ep0, ep1 = endpoints[0], endpoints[1]

        def resolve(ep):
            return node_id_map.get(ep.get("node_id", ""), ep.get("node_id", ""))

        n1_name = _node_name(nodes_def, ep0.get("node_id", ""))
        n2_name = _node_name(nodes_def, ep1.get("node_id", ""))

        # Remap ports if the node chassis was converted
        a0, p0 = remap_endpoint(ep0, nodes_def)
        a1, p1 = remap_endpoint(ep1, nodes_def)

        if a0 is None or a1 is None:
            WARN(f"Link {n1_name} <-> {n2_name} SKIPPED "
                 f"— port has no equivalent after chassis conversion")
            continue

        port_str = f"a{a0}/p{p0} <-> a{a1}/p{p1}"

        link_payload = {
            "nodes": [
                {
                    "node_id":        resolve(ep0),
                    "adapter_number": a0,
                    "port_number":    p0,
                },
                {
                    "node_id":        resolve(ep1),
                    "adapter_number": a1,
                    "port_number":    p1,
                },
            ]
        }
        if "link_type" in lnk:
            link_payload["link_type"] = lnk["link_type"]

        for i, ep in enumerate([ep0, ep1]):
            if "label" in ep:
                link_payload["nodes"][i]["label"] = ep["label"]

        try:
            result = client.post(f"/projects/{project_id}/links", link_payload)
            lid = result.get("link_id", "?")
            OK(f"Link {n1_name} <-> {n2_name}  [{port_str}] -> {lid}")
        except requests.HTTPError as e:
            WARN(f"Link {n1_name} <-> {n2_name} FAILED [{port_str}]: "
                 f"{e.response.text[:150]}")

    HEAD("Step 4b - Waiting 10s after links")
    for i in range(10, 0, -1):
        print(f"\r  [ . ]  Waiting... {i}s ", end="", flush=True)
        time.sleep(1)
    print()
    OK("Done waiting — proceeding to drawings / start")

    if drawings:
        HEAD("Step 5 - Drawings")
        ok_count = 0
        for d in drawings:
            payload = {k: v for k, v in d.items() if k != "drawing_id"}
            try:
                client.post(f"/projects/{project_id}/drawings", payload)
                ok_count += 1
            except requests.HTTPError as e:
                WARN(f"Drawing ({d.get('x',0)},{d.get('y',0)}) failed: "
                     f"{e.response.text[:80]}")
        OK(f"{ok_count}/{len(drawings)} drawings added")

    HEAD("Step 6 - Starting All Nodes")
    try:
        client.post(f"/projects/{project_id}/nodes/start")
        OK("All nodes start command sent")
        HEAD("Step 6b - Waiting 10s for nodes to boot")
        for i in range(10, 0, -1):
            print(f"\r  [ . ]  Waiting... {i}s ", end="", flush=True)
            time.sleep(1)
        print()
        OK("Done waiting — nodes should be up")
    except requests.HTTPError as e:
        WARN(f"Start failed: {e.response.text[:120]}")

    HEAD("Done")
    OK(f"Project ID : {project_id}")
    INFO(f"Nodes      : {len(nodes_def)}")
    INFO(f"Links      : {len(links_def)}")
    INFO(f"Drawings   : {len(drawings)}")
    INFO(f"Open GNS3 GUI -> File -> Open Project")
    return project_id


def _node_name(nodes_def, node_id):
    n = next((x for x in nodes_def if x.get("node_id") == node_id), None)
    return n["name"] if n else node_id[:8]


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Create a GNS3 project from a .gns3 JSON file "
                    "(all nodes -> local compute, dynamips -> c7200)"
    )
    parser.add_argument("topology_file")
    parser.add_argument("--host",      default="localhost")
    parser.add_argument("--port",      default=3080, type=int)
    parser.add_argument("--user",      default=None)
    parser.add_argument("--password",  default=None)
    parser.add_argument("--start",     action="store_true",
                        help="Auto-start all nodes after creation")
    parser.add_argument("--overwrite", action="store_true",
                        help="Delete & recreate if project name already exists")

    args = parser.parse_args()

    HEAD("GNS3 Topology Importer")
    INFO(f"File   : {args.topology_file}")
    INFO(f"Server : http://{args.host}:{args.port}")

    if not Path(args.topology_file).exists():
        ERR(f"File not found: {args.topology_file}")
        sys.exit(1)

    data = load_topology(args.topology_file)
    topo = data.get("topology", {})
    INFO(f"Project: {data.get('name', '(unnamed)')}")
    INFO(f"Nodes  : {len(topo.get('nodes', []))}")
    INFO(f"Links  : {len(topo.get('links', []))}")

    client = GNS3Client(args.host, args.port, args.user, args.password)
    try:
        version = client.ping()
        OK(f"Connected to GNS3 server v{version}")
    except requests.ConnectionError:
        ERR(f"Cannot connect to GNS3 at {args.host}:{args.port}")
        ERR("Make sure GNS3 is running with the local server enabled.")
        ERR("  GNS3 GUI -> Edit -> Preferences -> Server -> Enable local server")
        sys.exit(1)
    except requests.HTTPError as e:
        ERR(f"Server returned an error: {e}")
        sys.exit(1)

    create_project(client, data, args)


if __name__ == "__main__":
    main()


# to Run 
# python gns3_create_project.py <Testfilename>.gns3