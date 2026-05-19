"""
Structranet AI — Grand Orchestrator (Main Entry Point)

Offline export pipeline:
  [1/6] Load catalog
  [2/6] User input
  [3/6] AI topology (Phase 1)
  [4/6] Hardware injection
  [5/6] Software configs (Phase 2)
  [6/6] GNS3 Export & Validation

Output: final_topology.json ready for .gns3project export.

Supported flags:
  --no-phase2              → Skip Phase 2 (software config generation)
  --catalog PATH           → Custom appliance catalog JSON overlay
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys

from appliance_catalog import load_catalog
from ai_agent import generate_network_topology, process_and_save_topology
from gns3_exporter import convert as export_gns3project
from gns3project_validator import GNS3ProjectValidator
from constants.hardware import DYNAMIPS_MAX_PORTS
from preflight import (
    PreflightProfile,
    check_topology_compatibility,
    collect_profile_interactive,
    filter_inventory_by_profile,
    load_profile,
    profile_to_dict,
    save_profile,
)
from config_agent import run_phase2

logger = logging.getLogger("structranet.main")

# Default output directory (overridable via env var)
OUTPUT_DIR = os.getenv("STRUCTRANET_OUTPUT_DIR", "output")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI Arguments
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Structranet AI - Natural Language to GNS3 Topology JSON"
    )
    parser.add_argument("--request", "-r", type=str, default=None,
                        help="Network description (skips interactive prompt)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output JSON file path (default: output/final_topology.json)")
    parser.add_argument("--catalog", type=str, default=None,
                        help="Path to custom appliance catalog JSON overlay")
    parser.add_argument("--profile", type=str, default=None,
                        help="Path to preflight environment profile JSON")
    parser.add_argument("--no-phase2", action="store_true",
                        help="Skip Phase 2 (software configuration generation)")
    parser.add_argument("--project-output", type=str, default=None,
                        help="Output .gns3project path (default: output/<final_json_stem>.gns3project)")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip .gns3project structural validation")
    parser.add_argument("--configs", type=str, default=None, metavar="DIR",
                        help="Export raw configs to DIR for pre-GNS3 review")
    parser.add_argument("--yes", action="store_true",
                        help="Auto-approve generation without interactive confirmation")
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
#  Catalog → Inventory Adapter
# ═══════════════════════════════════════════════════════════════════════════════

# Port-count derivation constants
# DYNAMIPS_MAX_PORTS is now imported from constants/hardware.py — the SSOT.
_DYNAMIPS_MAX_PORTS = DYNAMIPS_MAX_PORTS
_SINGLE_PORT_TYPES = {"vpcs", "traceng", "nat"}
_MAX_EXPANDABLE_PORTS = {
    "iou": 16, "qemu": 8, "docker": 8,
    "virtualbox": 8, "vmware": 10,
    "ethernet_switch": 128, "ethernet_hub": 128,
}


def _build_design_review(
    topology_dict: dict,
    profile: PreflightProfile,
    compatibility_issues: list[str],
) -> tuple[list[str], list[str]]:
    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    node_types = sorted({str(n.get("node_type", "unknown")) for n in nodes})
    counts_by_type = {}
    for n in nodes:
        ntype = str(n.get("node_type", "unknown"))
        counts_by_type[ntype] = counts_by_type.get(ntype, 0) + 1

    thoughts = [
        f"Designed topology with {len(nodes)} node(s) and {len(links)} link(s).",
        "Node type mix: " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts_by_type.items())
        ),
    ]

    assumptions: list[str] = []
    if "dynamips" in node_types:
        assumptions.append(
            "Dynamips images/templates on your machine match the selected catalog names."
        )
    if "iou" in node_types:
        assumptions.append("IOU is available and licensed on your environment.")
    if "qemu" in node_types:
        assumptions.append("Required QEMU images exist on your machine.")
    if "docker" in node_types:
        assumptions.append("Docker is available and integrated with GNS3.")
    if not assumptions:
        assumptions.append("Built-in and selected node types are available on your machine.")

    if not str(profile.gns3_version).startswith("2.2"):
        assumptions.append(
            f"GNS3 version '{profile.gns3_version}' may behave differently than expected 2.2.x."
        )

    if compatibility_issues:
        assumptions.extend(compatibility_issues)

    return thoughts, assumptions


def catalog_to_inventory(catalog: dict) -> list[dict]:
    """Convert the appliance_catalog dict into the inventory list format
    expected by ai_agent.generate_network_topology().

    The catalog is keyed by template_name with values containing node_type
    and other hardware properties.  The inventory format is a flat list of
    dicts with name, gns3_type, category, and port_count fields.

    Port counts are derived from the catalog's hardware properties and
    the same constants used in schema.py's Topology validators.
    """
    inventory = []

    for name, props in catalog.items():
        ntype = props.get("node_type", "")
        entry = {
            "name": name,
            "gns3_type": ntype,
            "category": props.get("category", ""),
        }

        if ntype in _SINGLE_PORT_TYPES:
            entry["port_count"] = 1
        elif ntype == "dynamips":
            platform = props.get("platform", "").lower()
            entry["port_count"] = _DYNAMIPS_MAX_PORTS.get(platform, 3)
        elif ntype == "iou":
            eth = props.get("ethernet_adapters", 0)
            ser = props.get("serial_adapters", 0)
            entry["port_count"] = eth * 4 + ser * 4
        elif ntype in _MAX_EXPANDABLE_PORTS:
            entry["port_count"] = _MAX_EXPANDABLE_PORTS[ntype]

        inventory.append(entry)

    return inventory


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")

    print("=" * 60)
    print("  Structranet AI - Natural Language to GNS3 Topology JSON")
    print("  (Topology + Hardware + Software Config)")
    print("=" * 60 + "\n")

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1/5: Load appliance catalog ────────────────────────────────────
    print("[1/6] Loading appliance catalog...")
    catalog = load_catalog(args.catalog)
    inventory = catalog_to_inventory(catalog)

    if not inventory:
        print("[ERR] No appliances in catalog. Add entries to appliance_catalog.py.")
        sys.exit(1)

    print(f"  Found {len(inventory)} appliance(s): "
          f"{', '.join(d['name'] for d in inventory)}")

    # ── Step 2/5: Get user input ────────────────────────────────────────────
    print(f"\n[2/6] Describe the network you want.")
    print(f"  Available: {', '.join(d['name'] for d in inventory)}")
    if args.request:
        user_request = args.request
        print(f"  Request: {user_request}")
    else:
        user_request = input("\n  > ")
    if not user_request.strip():
        print("[ERR] No input. Exiting.")
        sys.exit(1)

    # ── Step 2b/6: Preflight profile (environment compatibility) ─────────────
    if args.profile:
        try:
            profile = load_profile(args.profile)
            print(f"\n[Preflight] Loaded profile: {args.profile}")
        except Exception as exc:
            print(f"[ERR] Failed to load profile '{args.profile}': {exc}")
            sys.exit(1)
    else:
        profile = collect_profile_interactive()
        profile_path = os.path.join(OUTPUT_DIR, "preflight_profile.json")
        save_profile(profile, profile_path)
        print(f"[Preflight] Profile saved to: {profile_path}")

    filtered_inventory, blocked_types = filter_inventory_by_profile(inventory, profile)
    if not filtered_inventory:
        print("[ERR] Profile blocks all available node types in inventory.")
        sys.exit(1)

    if len(filtered_inventory) != len(inventory):
        blocked_list = ", ".join(sorted(blocked_types))
        print(f"[Preflight] Filtering unsupported types from generation: {blocked_list}")

    # ── Step 3/6: Phase 1 — Logical topology generation ─────────────────────
    print("\n[3/6] Phase 1 — AI generating logical topology...")
    result = generate_network_topology(
        user_request,
        filtered_inventory,
        disallowed_node_types=blocked_types,
    )
    if not result:
        print("[ERR] AI generation failed. Check your API key and model config.")
        sys.exit(1)
    print(f"  Generated {len(result.topology.nodes)} node(s), "
          f"{len(result.topology.links)} link(s)")

    # ── Step 4/6: Phase 1 — Hardware injection + save ───────────────────────
    print("\n[4/6] Phase 1 — Injecting hardware expansion (slots/adapters/ports)...")
    phase1_file = os.path.join(OUTPUT_DIR, "_topology.json")
    enriched = process_and_save_topology(result, phase1_file)
    if not enriched:
        print("[ERR] Hardware injection failed. Check logs above.")
        sys.exit(1)
    print(f"  Hardware-injected topology saved to: {phase1_file}")

    topo_dict = enriched.model_dump()

    # Compatibility gate: block unsupported node types for this environment.
    compatibility_issues = check_topology_compatibility(topo_dict, profile)
    if compatibility_issues:
        print("\n[Compatibility] Found environment issues:")
        for issue in compatibility_issues:
            print(f"  - {issue}")
        if profile.strict_validation:
            print("[ERR] Aborting due to strict preflight validation.")
            sys.exit(1)
        print("[WARN] Continuing (strict_validation=false).")

    thoughts, assumptions = _build_design_review(topo_dict, profile, compatibility_issues)
    print("\n[Design Review]")
    for t in thoughts:
        print(f"  - {t}")
    print("  Assumptions / risks:")
    for a in assumptions:
        print(f"    * {a}")

    if not args.yes:
        confirm_design = input("Approve this design before software config generation? [Y/n] ").strip().lower()
        if confirm_design in {"n", "no"}:
            print("Stopped before Phase 2 at your request.")
            sys.exit(0)

    # ── Step 5/6: Phase 2 — Software configuration generation ───────────────
    final_file = args.output or os.path.join(OUTPUT_DIR, "final_topology.json")

    if args.no_phase2:
        print("\n[5/6] Phase 2 — SKIPPED (--no-phase2 flag set)")
        # Use Phase 1 output as the final topology
        final_dict = topo_dict
        # Save it as final
        with open(final_file, "w") as f:
            json.dump(final_dict, f, indent=2)
        print(f"  Phase 1 output saved as final: {final_file}")
    else:
        print("\n[5/6] Phase 2 — Generating software configurations (IP/routing/startup)...")
        final_dict = run_phase2(phase1_file, final_file)
        if final_dict is None:
            print("[WARN] Phase 2 failed — falling back to Phase 1 topology (no software configs).")
            final_dict = topo_dict
            # Save Phase 1 as the final file
            with open(final_file, "w") as f:
                json.dump(final_dict, f, indent=2)
            print(f"  Phase 1 topology saved as final: {final_file}")
        else:
            print(f"  Phase 2 complete. Final topology saved to: {final_file}")

    # ── Summary ──────────────────────────────────────────────────────────────
    node_count = len(final_dict.get("topology", {}).get("nodes", []))
    link_count = len(final_dict.get("topology", {}).get("links", []))
    # Count how many nodes have software configs
    configured = sum(
        1 for n in final_dict.get("topology", {}).get("nodes", [])
        if n.get("properties") and any(
            k in n["properties"]
            for k in ("startup_config_content", "startup_script", "start_command")
        )
    )
    print(f"\n  Summary: {node_count} node(s), {link_count} link(s), "
          f"{configured} node(s) with software configs")
    print(f"  Output: {final_file}")

    if not args.yes:
        print("\nDesign looks ready. I can now generate the final .gns3project.")
        confirm = input("Proceed with export and validation? [Y/n] ").strip().lower()
        if confirm in {"n", "no"}:
            print("Stopped before export at your request.")
            sys.exit(0)

    # ── Export: final_topology.json → .gns3project ───────────────────────────
    print("\n[6/6] Exporting portable GNS3 project (.gns3project)...")
    project_output = args.project_output
    if not project_output:
        final_stem = Path(final_file).stem
        project_output = os.path.join(OUTPUT_DIR, f"{final_stem}.gns3project")

    # Config review directory: use --configs flag, or default to output/configs_review
    config_review_dir = args.configs
    if config_review_dir is None:
        config_review_dir = os.path.join(OUTPUT_DIR, "configs_review")

    try:
        project_path = export_gns3project(
            final_dict,
            project_output,
            image_map=profile.normalized_template_image_map,
            config_review_dir=config_review_dir,
        )
        print(f"  Export complete: {project_path}")
    except Exception as exc:
        print(f"[ERR] Export failed: {exc}")
        sys.exit(1)

    # ── Validation gate (optional) ────────────────────────────────────────────
    validator_ok = None
    if args.no_validate:
        print("  Validation skipped (--no-validate)")
    else:
        print("  Running structural validator...")
        validator = GNS3ProjectValidator(project_path, verbose=False)
        validator_ok = validator.validate()
        if validator_ok:
            print("  Validator result: PASS")
        else:
            print("[ERR] Validator result: FAIL (see issues above)")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request": user_request,
        "profile": profile_to_dict(profile),
        "phase2_skipped": bool(args.no_phase2),
        "compatibility_issues": compatibility_issues,
        "design_review": {
            "thoughts": thoughts,
            "assumptions": assumptions,
        },
        "outputs": {
            "phase1_json": phase1_file,
            "final_json": final_file,
            "gns3project": project_path,
        },
        "validator": {
            "skipped": bool(args.no_validate),
            "passed": validator_ok,
        },
    }
    report_path = os.path.join(OUTPUT_DIR, "generation_report.json")
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)
    print(f"  Generation report: {report_path}")

    if validator_ok is False:
        sys.exit(1)


if __name__ == "__main__":
    main()