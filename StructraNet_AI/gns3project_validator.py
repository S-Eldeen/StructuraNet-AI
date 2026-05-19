"""
gns3project_validator.py — Deep Structural Validator for .gns3project Files

Performs thorough validation that simulates what GNS3's own import logic checks,
going far beyond simple "is it valid JSON?" to catch the bugs that cause
GNS3 to reject or silently misconfigure imported projects.

Validation checks:
  1. ZIP structure validation (project.gns3 exists, project-files/ paths correct)
  2. JSON schema conformity (revision, type, required top-level keys)
  3. Node validation (required fields, node_type legality, properties per type)
  4. Dynamips compatibility matrix (platform ↔ slot modules, image naming)
  5. Port reference integrity (every link port exists on the referenced node)
  6. Config file path consistency (project-files/<type>/<uuid>/configs/ paths match ZIP)
  7. Template ID format validation (appliance types have UUID, built-in types have none)
  8. Compute cross-referencing ("local" is always valid; remote computes must be listed)
  9. Switch VLAN sanity (access ports have VLAN 1-4094, trunks are dot1q)
 10. Link integrity (no duplicate links, no self-links, both endpoints valid)
 11. UUID format validation (all node_id, link_id, project_id are valid UUIDs)

All node-type taxonomy and Dynamips hardware constants live in
constants/validation.py — import from there instead of duplicating here.

Usage:
    python gns3project_validator.py <file.gns3project>
    python gns3project_validator.py <file.gns3project> --verbose
"""

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from constants.hardware import DYNAMIPS_COMPAT, MODULE_PORT_COUNT
from constants.gns3 import VALID_NODE_TYPES, BUILTIN_NODE_TYPES, APPLIANCE_NODE_TYPES

# ── Severity levels ──────────────────────────────────────────────────────────────
CRITICAL = "CRITICAL"   # Will cause GNS3 import failure
ERROR    = "ERROR"      # Will cause node/link to fail at runtime
WARNING  = "WARNING"    # May work but behavior will be wrong
INFO     = "INFO"       # Informational, not a problem


# ═══════════════════════════════════════════════════════════════════════════════
#  Validator class
# ═══════════════════════════════════════════════════════════════════════════════

class GNS3ProjectValidator:
    def __init__(self, filepath: str, verbose: bool = False):
        self.filepath = filepath
        self.verbose = verbose
        self.issues: List[Dict[str, str]] = []
        self.project_json: Optional[Dict] = None
        self.zip_files: Set[str] = set()
        self.stats = {
            "total_checks": 0,
            "critical": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
        }

    def _add_issue(self, severity: str, category: str, message: str, detail: str = ""):
        self.issues.append({
            "severity": severity,
            "category": category,
            "message": message,
            "detail": detail,
        })
        self.stats[severity.lower()] = self.stats.get(severity.lower(), 0) + 1

    def validate(self) -> bool:
        """Run all validation checks. Returns True if no CRITICAL or ERROR issues."""
        print(f"\n{'='*70}")
        print(f"  GNS3 Project File Validator")
        print(f"  File: {self.filepath}")
        print(f"{'='*70}\n")

        # ── Check 1: ZIP structure ──────────────────────────────────────────────
        if not self._check_zip_structure():
            self._print_results()
            return False

        # ── Check 2: JSON schema ────────────────────────────────────────────────
        if not self._check_json_schema():
            self._print_results()
            return False

        topo     = self.project_json.get("topology", {})
        nodes    = topo.get("nodes", [])
        links    = topo.get("links", [])
        computes = topo.get("computes", [])

        # ── Check 3: Node validation ────────────────────────────────────────────
        self._check_nodes(nodes)

        # ── Check 4: Dynamips compatibility ─────────────────────────────────────
        self._check_dynamips_compat(nodes)

        # ── Check 5: Port reference integrity ───────────────────────────────────
        self._check_port_integrity(nodes, links)

        # ── Check 6: Config file path consistency ───────────────────────────────
        self._check_config_paths(nodes)

        # ── Check 7: Template ID validation ─────────────────────────────────────
        self._check_template_ids(nodes)

        # ── Check 8: Compute cross-referencing ──────────────────────────────────
        self._check_computes(nodes, computes)

        # ── Check 9: Switch VLAN sanity ─────────────────────────────────────────
        self._check_switch_vlans(nodes)

        # ── Check 10: Link integrity ────────────────────────────────────────────
        self._check_links(nodes, links)

        # ── Check 11: UUID format validation ────────────────────────────────────
        self._check_uuids(nodes, links)

        self._print_results()
        return self.stats["critical"] == 0 and self.stats["error"] == 0

    # ── Check 1: ZIP structure ──────────────────────────────────────────────────
    def _check_zip_structure(self) -> bool:
        print("1. Checking ZIP structure...")

        if not zipfile.is_zipfile(self.filepath):
            self._add_issue(CRITICAL, "ZIP", "File is not a valid ZIP archive")
            return False

        try:
            with zipfile.ZipFile(self.filepath, "r") as zf:
                self.zip_files = set(zf.namelist())

                if "project.gns3" not in self.zip_files:
                    self._add_issue(CRITICAL, "ZIP",
                                    "Missing project.gns3 — not a valid .gns3project file")
                    return False

                self.project_json = json.loads(zf.read("project.gns3"))

                for f in self.zip_files:
                    if f == "project.gns3":
                        continue
                    if not f.startswith("project-files/") and not f.startswith("files/"):
                        self._add_issue(WARNING, "ZIP",
                                        f"Unexpected file in ZIP: {f}",
                                        "Non-standard files may be ignored by GNS3")

                config_files = [f for f in self.zip_files
                                if "/configs/" in f or f.endswith(".vpc")]
                if config_files:
                    print(f"   Found {len(config_files)} config file(s) in ZIP")
                    if self.verbose:
                        for cf in config_files:
                            print(f"     - {cf}")
                else:
                    self._add_issue(INFO, "ZIP",
                                    "No config files found in ZIP",
                                    "Nodes will start with default configs")

        except zipfile.BadZipFile:
            self._add_issue(CRITICAL, "ZIP", "ZIP file is corrupted")
            return False
        except json.JSONDecodeError as e:
            self._add_issue(CRITICAL, "ZIP", f"project.gns3 contains invalid JSON: {e}")
            return False

        print("   ZIP structure: OK")
        return True

    # ── Check 2: JSON schema ────────────────────────────────────────────────────
    def _check_json_schema(self) -> bool:
        print("2. Checking JSON schema...")

        pj = self.project_json

        required_keys = ["name", "project_id", "revision", "type", "version", "topology"]
        for key in required_keys:
            if key not in pj:
                self._add_issue(CRITICAL, "Schema", f"Missing required key: {key}")

        if pj.get("type") != "topology":
            self._add_issue(ERROR, "Schema",
                            f"'type' must be 'topology', got: {pj.get('type')}")

        rev = pj.get("revision")
        if rev != 9:
            self._add_issue(ERROR, "Schema",
                            f"Revision must be 9, got: {rev}",
                            "GNS3 2.2+ uses revision 9")

        ver = pj.get("version", "")
        if not ver.startswith("2.2"):
            self._add_issue(WARNING, "Schema",
                            f"Version '{ver}' may not be compatible with GNS3 2.2+")

        topo = pj.get("topology", {})
        for key in ["nodes", "links"]:
            if key not in topo:
                self._add_issue(CRITICAL, "Schema", f"Missing topology.{key}")

        if "computes" not in topo:
            self._add_issue(WARNING, "Schema",
                            "Missing topology.computes",
                            "GNS3 may not know where to run nodes")

        if not topo.get("nodes"):
            self._add_issue(ERROR, "Schema", "No nodes defined in topology")

        print(f"   Project: {pj.get('name', '?')}")
        print(f"   Revision: {rev}, Version: {ver}")
        print("   JSON schema: OK")
        return True

    # ── Check 3: Node validation ────────────────────────────────────────────────
    def _check_nodes(self, nodes: List[dict]):
        print("3. Checking nodes...")

        if not nodes:
            self._add_issue(ERROR, "Nodes", "No nodes to validate")
            return

        node_ids   = set()
        node_names = Counter()

        for i, node in enumerate(nodes):
            name  = node.get("name", f"<unnamed-{i}>")
            ntype = node.get("node_type", "")

            required = ["node_id", "name", "node_type", "compute_id",
                        "x", "y", "properties"]
            for field in required:
                if field not in node:
                    self._add_issue(ERROR, "Nodes",
                                    f"Node '{name}' missing required field: {field}")

            if ntype and ntype not in VALID_NODE_TYPES:
                self._add_issue(ERROR, "Nodes",
                                f"Node '{name}' has unknown node_type: {ntype}",
                                f"Valid types: {', '.join(sorted(VALID_NODE_TYPES))}")

            nid = node.get("node_id", "")
            if nid in node_ids:
                self._add_issue(CRITICAL, "Nodes",
                                f"Duplicate node_id: {nid}",
                                "GNS3 will reject projects with duplicate node IDs")
            node_ids.add(nid)

            node_names[name] += 1
            if node_names[name] > 1:
                self._add_issue(WARNING, "Nodes",
                                f"Duplicate node name: '{name}'",
                                "GNS3 allows duplicate names but it's confusing")

            props = node.get("properties", {})
            if ntype in APPLIANCE_NODE_TYPES and not props:
                self._add_issue(CRITICAL, "Nodes",
                                f"Node '{name}' ({ntype}) has empty properties",
                                "GNS3 cannot create an appliance node without properties")

            # The GNS3 2.2 schema console_type enum includes both the string
            # "none" AND JSON null as valid values.  Nodes that have no console
            # (switches, hubs, NAT, etc.) should use null rather than "none" for
            # maximum compatibility, but "none" will not cause an import error.
            ctype = node.get("console_type")
            no_console_types = {
                "ethernet_switch", "ethernet_hub", "cloud", "nat",
                "frame_relay_switch", "atm_switch", "traceng",
            }
            if ntype in no_console_types and ctype not in (None, "none"):
                self._add_issue(WARNING, "Nodes",
                                f"Node '{name}' ({ntype}) has console_type='{ctype}'",
                                "This node type should have console_type=null or 'none'")

        print(f"   Validated {len(nodes)} node(s)")
        if self.verbose:
            for node in nodes:
                print(f"     - {node.get('name', '?')} ({node.get('node_type', '?')})")

    # ── Check 4: Dynamips compatibility matrix ──────────────────────────────────
    def _check_dynamips_compat(self, nodes: List[dict]):
        print("4. Checking Dynamips compatibility...")

        dynamips_nodes = [n for n in nodes if n.get("node_type") == "dynamips"]
        if not dynamips_nodes:
            print("   No Dynamips nodes — skipping")
            return

        for node in dynamips_nodes:
            name     = node.get("name", "?")
            props    = node.get("properties", {})
            platform = props.get("platform", "")

            if not platform:
                self._add_issue(CRITICAL, "Dynamips",
                                f"Node '{name}' missing 'platform' property",
                                "Dynamips requires a platform (e.g., c3745)")
                continue

            if platform not in DYNAMIPS_COMPAT:
                self._add_issue(ERROR, "Dynamips",
                                f"Node '{name}' has unknown platform: {platform}",
                                f"Known platforms: {', '.join(sorted(DYNAMIPS_COMPAT.keys()))}")
                continue

            compat = DYNAMIPS_COMPAT[platform]

            image = props.get("image", "")
            if not image:
                self._add_issue(ERROR, "Dynamips",
                                f"Node '{name}' missing 'image' property",
                                "Dynamips requires an IOS image filename")
            elif not image.startswith(platform[1:] if platform.startswith("c") else platform):
                # Lenient check: image name should contain the platform digits
                platform_digits = platform.lstrip("c")
                if platform_digits not in image and platform not in image:
                    self._add_issue(WARNING, "Dynamips",
                                    f"Node '{name}' image '{image}' may not match platform '{platform}'",
                                    "Image filename should typically contain the platform identifier")

            ram = props.get("ram", 0)
            ram_min, ram_max = compat["ram_range"]
            if ram < ram_min:
                self._add_issue(ERROR, "Dynamips",
                                f"Node '{name}' RAM={ram}MB is below minimum {ram_min}MB",
                                f"Platform {platform} requires at least {ram_min}MB")
            elif ram > ram_max:
                self._add_issue(WARNING, "Dynamips",
                                f"Node '{name}' RAM={ram}MB exceeds recommended {ram_max}MB",
                                "May work but could waste resources")

            # Validate every slotN key present in properties
            slot_num = 0
            while True:
                slot_key = f"slot{slot_num}"
                if slot_key not in props:
                    break
                module = props[slot_key]
                if module:  # empty string = unoccupied slot, skip
                    valid_modules = compat["slots"].get(slot_num)
                    if valid_modules is None:
                        self._add_issue(ERROR, "Dynamips",
                                        f"Node '{name}' platform {platform} has no slot{slot_num}",
                                        f"Max slot: {max(compat['slots'].keys())}")
                    elif module not in valid_modules:
                        self._add_issue(ERROR, "Dynamips",
                                        f"Node '{name}' slot{slot_num}='{module}' is incompatible "
                                        f"with platform {platform}",
                                        f"Allowed: {', '.join(valid_modules)}")
                slot_num += 1

        print(f"   Checked {len(dynamips_nodes)} Dynamips node(s)")

    # ── Check 5: Port reference integrity ───────────────────────────────────────
    def _check_port_integrity(self, nodes: List[dict], links: List[dict]):
        print("5. Checking port reference integrity...")

        node_map: Dict[str, dict] = {n.get("node_id"): n for n in nodes}

        node_port_map: Dict[str, Set[Tuple[int, int]]] = {}
        for node in nodes:
            nid   = node.get("node_id", "")
            ports = node.get("ports", [])
            node_port_map[nid] = {
                (p.get("adapter_number", 0), p.get("port_number", 0))
                for p in ports
            }

        for i, link in enumerate(links):
            for ep in link.get("nodes", []):
                nid     = ep.get("node_id", "")
                adapter = ep.get("adapter_number", 0)
                port    = ep.get("port_number", 0)

                if nid not in node_map:
                    self._add_issue(ERROR, "Ports",
                                    f"Link {i} references unknown node_id: {nid}")
                    continue

                port_set = node_port_map.get(nid)
                if port_set and (adapter, port) not in port_set:
                    node_name = node_map[nid].get("name", "?")
                    self._add_issue(ERROR, "Ports",
                                    f"Link {i} references adapter{adapter}/port{port} "
                                    f"which doesn't exist on node '{node_name}'",
                                    f"Available ports: {sorted(port_set)}")

        print(f"   Checked {len(links)} link(s)")

    # ── Check 6: Config file path consistency ───────────────────────────────────
    def _check_config_paths(self, nodes: List[dict]):
        print("6. Checking config file path consistency...")

        for node in nodes:
            name  = node.get("name", "?")
            ntype = node.get("node_type", "")
            nid   = node.get("node_id", "")
            props = node.get("properties", {})

            if ntype in ("dynamips", "iou", "qemu"):
                # Check for inline config content (valid GNS3 schema property).
                # startup_config / private_config are NOT valid schema properties
                # (they are forbidden pointer keys stripped by _clean_properties).
                # GNS3 reads startup_config_content during import and writes it
                # to the config files itself.
                startup_content = props.get("startup_config_content", "")
                private_content = props.get("private_config_content", "")
                has_inline = bool(startup_content) or bool(private_content)

                standard_path = f"project-files/{ntype}/{nid}/configs/startup-config.cfg"
                config_in_zip = standard_path in self.zip_files

                if has_inline and not config_in_zip:
                    # Content is inline — this is fine, GNS3 will create the
                    # file from startup_config_content on import.
                    if self.verbose:
                        print(f"     {name}: inline config content "
                              f"({len(startup_content)} chars) — ZIP file not needed")
                elif not has_inline and not config_in_zip:
                    self._add_issue(INFO, "ConfigPaths",
                                    f"Node '{name}' has no startup config "
                                    f"(no startup_config_content and no ZIP file)",
                                    "Node will boot with default config")
                elif config_in_zip:
                    if self.verbose:
                        print(f"     {name}: {standard_path} → FOUND")

                # Also check for forbidden pointer keys that would cause
                # GNS3 import rejection (should have been stripped by
                # _clean_properties but catch them here too).
                for forbidden_key in ("startup_config", "private_config", "nvram"):
                    if props.get(forbidden_key):
                        self._add_issue(ERROR, "ConfigPaths",
                                        f"Node '{name}' has forbidden pointer key "
                                        f"'{forbidden_key}' in properties",
                                        "GNS3 schemas enforce additionalProperties: false. "
                                        "This key will cause: 'Additional properties are "
                                        "not allowed'. Use startup_config_content instead.")

            elif ntype == "vpcs":
                startup_script = props.get("startup_script", "")
                if startup_script:
                    standard_path = f"project-files/vpcs/{nid}/startup.vpc"
                    legacy_path   = f"files/{nid}/startup.vpc"
                    if standard_path not in self.zip_files and legacy_path not in self.zip_files:
                        self._add_issue(WARNING, "ConfigPaths",
                                        f"VPCS '{name}' has startup_script but no "
                                        f"startup.vpc in ZIP",
                                        f"Expected: {standard_path}")

        print("   Config path consistency: checked")

    # ── Check 7: Template ID validation ─────────────────────────────────────────
    def _check_template_ids(self, nodes: List[dict]):
        print("7. Checking template IDs...")

        for node in nodes:
            name           = node.get("name", "?")
            ntype          = node.get("node_type", "")
            has_template   = "template_id" in node

            if ntype in BUILTIN_NODE_TYPES and has_template:
                self._add_issue(WARNING, "TemplateID",
                                f"Built-in type '{name}' ({ntype}) has template_id",
                                "Built-in types should not carry a template_id")
            elif ntype in APPLIANCE_NODE_TYPES and not has_template:
                self._add_issue(WARNING, "TemplateID",
                                f"Appliance type '{name}' ({ntype}) is missing template_id",
                                "GNS3 will prompt the user to select a template during import")

            if has_template:
                tid = node.get("template_id")
                if tid is not None:
                    try:
                        import uuid as uuid_mod
                        uuid_mod.UUID(str(tid))
                    except (ValueError, AttributeError):
                        self._add_issue(ERROR, "TemplateID",
                                        f"Node '{name}' has invalid template_id: {tid}",
                                        "Must be a valid UUID or null")

        print("   Template IDs: checked")

    # ── Check 8: Compute cross-referencing ──────────────────────────────────────
    def _check_computes(self, nodes: List[dict], computes: List[dict]):
        print("8. Checking compute references...")

        compute_ids = {c.get("compute_id") for c in computes}
        LOCAL_IDS   = {"local", "vm", None}

        if not computes:
            self._add_issue(INFO, "Computes",
                            "No computes defined in topology",
                            "'local' compute is implicit — remote computes must be listed")

        for node in nodes:
            name = node.get("name", "?")
            cid  = node.get("compute_id", "")

            if not cid:
                self._add_issue(ERROR, "Computes",
                                f"Node '{name}' has no compute_id",
                                "Every node must reference a compute")
            elif cid in LOCAL_IDS:
                pass  # "local" is always valid
            elif cid not in compute_ids:
                self._add_issue(ERROR, "Computes",
                                f"Node '{name}' references compute_id '{cid}' "
                                f"which doesn't exist in computes list",
                                f"Available computes: {', '.join(compute_ids) or 'none'}")

        print(f"   Computes: {len(computes)} defined, {len(compute_ids)} unique ID(s)")

    # ── Check 9: Switch VLAN sanity ─────────────────────────────────────────────
    def _check_switch_vlans(self, nodes: List[dict]):
        print("9. Checking switch VLAN assignments...")

        for node in nodes:
            name  = node.get("name", "?")
            ntype = node.get("node_type", "")

            if ntype not in ("ethernet_switch", "ethernet_hub"):
                continue

            props        = node.get("properties", {})
            ports_mapping = props.get("ports_mapping", [])

            if not ports_mapping:
                self._add_issue(WARNING, "VLANs",
                                f"Switch '{name}' has no ports_mapping",
                                "GNS3 needs ports_mapping to configure switch ports")
                continue

            access_vlans = set()
            trunk_count  = 0

            for pm in ports_mapping:
                vlan  = pm.get("vlan", 1)
                ptype = pm.get("type", "access")

                if ptype == "access":
                    access_vlans.add(vlan)
                    if vlan < 1 or vlan > 4094:
                        self._add_issue(ERROR, "VLANs",
                                        f"Switch '{name}' port {pm.get('port_number', '?')} "
                                        f"has invalid VLAN {vlan}",
                                        "VLANs must be 1-4094")
                elif ptype == "dot1q":
                    trunk_count += 1

            non_default_vlans = access_vlans - {1}
            if non_default_vlans and trunk_count == 0:
                self._add_issue(WARNING, "VLANs",
                                f"Switch '{name}' has non-default VLANs {non_default_vlans} "
                                f"on access ports but no dot1q trunk port",
                                "These VLANs may not be routable without a trunk uplink")

            if self.verbose:
                print(f"     {name}: {len(ports_mapping)} ports, "
                      f"VLANs={access_vlans}, trunks={trunk_count}")

        print("   VLAN assignments: checked")

    # ── Check 10: Link integrity ────────────────────────────────────────────────
    def _check_links(self, nodes: List[dict], links: List[dict]):
        print("10. Checking link integrity...")

        node_ids   = {n.get("node_id") for n in nodes}
        seen_pairs = set()

        for i, link in enumerate(links):
            eps = link.get("nodes", [])

            if len(eps) < 2:
                self._add_issue(ERROR, "Links",
                                f"Link {i} has fewer than 2 endpoints")
                continue

            n0, n1 = eps[0].get("node_id", ""), eps[1].get("node_id", "")

            if n0 == n1:
                self._add_issue(ERROR, "Links",
                                f"Link {i} is a self-link on node {n0}",
                                "GNS3 does not support self-links")

            for ep in eps:
                if ep.get("node_id") not in node_ids:
                    self._add_issue(ERROR, "Links",
                                    f"Link {i} references non-existent node: {ep.get('node_id')}")

            pair = tuple(sorted([
                (n0, eps[0].get("adapter_number", 0), eps[0].get("port_number", 0)),
                (n1, eps[1].get("adapter_number", 0), eps[1].get("port_number", 0)),
            ]))
            if pair in seen_pairs:
                self._add_issue(WARNING, "Links",
                                f"Link {i} is a duplicate connection",
                                "Same pair of ports connected more than once")
            seen_pairs.add(pair)

        linked_nodes = set()
        for link in links:
            for ep in link.get("nodes", []):
                linked_nodes.add(ep.get("node_id"))

        for node in nodes:
            nid = node.get("node_id", "")
            if nid in linked_nodes and not node.get("ports"):
                pass

        print(f"   Checked {len(links)} link(s)")

    # ── Check 11: UUID format validation ────────────────────────────────────────
    def _check_uuids(self, nodes: List[dict], links: List[dict]):
        print("11. Checking UUID formats...")

        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
        )

        pid = self.project_json.get("project_id", "")
        if not uuid_pattern.match(str(pid)):
            self._add_issue(ERROR, "UUIDs",
                            f"project_id is not a valid UUID: {pid}")

        for node in nodes:
            nid = node.get("node_id", "")
            if not uuid_pattern.match(str(nid)):
                self._add_issue(ERROR, "UUIDs",
                                f"Node '{node.get('name', '?')}' has invalid node_id: {nid}")

        for i, link in enumerate(links):
            lid = link.get("link_id", "")
            if not uuid_pattern.match(str(lid)):
                self._add_issue(ERROR, "UUIDs",
                                f"Link {i} has invalid link_id: {lid}")

        print("   UUID formats: checked")

    # ── Print results ───────────────────────────────────────────────────────────
    def _print_results(self):
        print(f"\n{'='*70}")
        print("  VALIDATION RESULTS")
        print(f"{'='*70}\n")

        by_severity = {CRITICAL: [], ERROR: [], WARNING: [], INFO: []}
        for issue in self.issues:
            by_severity.get(issue["severity"], []).append(issue)

        for sev in [CRITICAL, ERROR, WARNING, INFO]:
            issues = by_severity[sev]
            if not issues:
                continue
            icon = {"CRITICAL": "[!!!]", "ERROR": "[X]", "WARNING": "[!]", "INFO": "[i]"}[sev]
            print(f"  {icon} {sev} ({len(issues)}):")
            print(f"  {'-'*60}")
            for issue in issues:
                print(f"  [{issue['category']}] {issue['message']}")
                if issue["detail"] and self.verbose:
                    print(f"    → {issue['detail']}")
            print()

        total = sum(self.stats[k] for k in ["critical", "error", "warning", "info"])
        print(f"{'-'*70}")
        print(f"  Total issues: {total}")
        print(f"    CRITICAL: {self.stats['critical']}  (GNS3 will refuse to import)")
        print(f"    ERROR:    {self.stats['error']}  (Nodes/links will fail at runtime)")
        print(f"    WARNING:  {self.stats['warning']}  (May work but behavior may be wrong)")
        print(f"    INFO:     {self.stats['info']}  (Informational)")
        print()

        if self.stats["critical"] == 0 and self.stats["error"] == 0:
            print("  [PASS] No critical or error issues found.")
            print("     This file is structurally valid and should import into GNS3.")
            print()
            print("  [!] IMPORTANT: This is STRUCTURAL validation only.")
            print("     The ONLY way to be 100% sure is to import into GNS3 GUI:")
            print("     File > Import portable project > select the .gns3project file")
        else:
            print("  [FAIL] Fix CRITICAL and ERROR issues before importing into GNS3.")

        print(f"{'='*70}\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Validate a .gns3project file for GNS3 compatibility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python gns3project_validator.py my_network.gns3project\n"
            "  python gns3project_validator.py my_network.gns3project --verbose\n"
        ),
    )
    parser.add_argument("file", help="Path to the .gns3project file to validate")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed information")
    args = parser.parse_args()

    validator = GNS3ProjectValidator(args.file, verbose=args.verbose)
    success   = validator.validate()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()