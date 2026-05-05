"""
Structranet AI — Grand Orchestrator (Main Entry Point)

Full 7-step pipeline:
  [1/7] Fetch inventory    → gns3_fetcher.fetch_available_templates
  [2/7] User input         → CLI / interactive prompt
  [3/7] AI topology        → ai_agent.generate_network_topology (Phase 1: structure, properties={})
  [4/7] Hardware injection → ai_agent.process_and_save_topology (Phase 1: slots, adapters, ports_mapping)
  [5/7] Software configs   → config_agent.run_phase2           (Phase 2: IPs, routing, startup scripts)
  [6/7] Save final JSON    → output/final_topology.json
  [7/7] Deploy to GNS3     → assembler.deploy_hybrid_topology  (properties forwarded to GNS3 API)

Supported modes:
  --deploy-only JSON_FILE  → Skip steps 1-6, deploy an existing JSON
  --no-deploy              → Stop after step 6 (JSON only)
  --no-phase2              → Skip Phase 2 (software config generation)
"""

import argparse
import json
import logging
import os
import sys

from gns3_fetcher import fetch_available_templates, FetcherError
from ai_agent import generate_network_topology, process_and_save_topology
from config_agent import run_phase2
from assembler import GNS3Client, deploy_hybrid_topology, DeploymentError

logger = logging.getLogger("structranet.main")

# Default output directory (overridable via env var)
OUTPUT_DIR = os.getenv("STRUCTRANET_OUTPUT_DIR", "output")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI Arguments
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Structranet AI - Natural Language to Live GNS3 Topology"
    )
    parser.add_argument("--request", "-r", type=str, default=None,
                        help="Network description (skips interactive prompt)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output JSON file path (default: output/final_topology.json)")
    parser.add_argument("--host", type=str, default=os.getenv("GNS3_HOST", "localhost"),
                        help="GNS3 server host")
    try:
        default_port = int(os.getenv("GNS3_PORT", "3080"))
    except ValueError:
        print(f"[ERR] GNS3_PORT must be an integer, got '{os.getenv('GNS3_PORT')}'")
        sys.exit(1)
    parser.add_argument("--port", type=int, default=default_port,
                        help="GNS3 server port")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing GNS3 project")
    parser.add_argument("--start", action="store_true",
                        help="Start nodes after deployment")
    parser.add_argument("--deploy-only", type=str, default=None, metavar="JSON_FILE",
                        help="Deploy an existing JSON file (skip steps 1-6)")
    parser.add_argument("--no-deploy", action="store_true",
                        help="Generate JSON only, don't deploy")
    parser.add_argument("--no-phase2", action="store_true",
                        help="Skip Phase 2 (software configuration generation)")
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
#  Pre-flight Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_against_inventory(topology: dict, inventory: list) -> list:
    """Check that all template_names in the topology exist in inventory.

    Returns a list of warning strings. Errors here are warnings, not
    hard failures — the assembler's own Defense-in-Depth check will
    catch the same issues at deploy time with a hard error.
    """
    if not inventory:
        return []
    available = {d["name"] for d in inventory}
    name_to_type = {d["name"]: d.get("gns3_type", "") for d in inventory}
    warnings = []
    for node in topology.get("topology", {}).get("nodes", []):
        tname = node.get("template_name", "")
        ntype = node.get("node_type", "")
        name = node.get("name", "?")
        if tname and tname not in available:
            warnings.append(
                f"'{name}' uses template '{tname}' not in inventory — "
                f"deployment may fail"
            )
        elif tname and name_to_type.get(tname) and name_to_type[tname] != ntype:
            warnings.append(
                f"'{name}' node_type={ntype} but template is "
                f"{name_to_type[tname]} — will be auto-corrected at deploy"
            )
    return warnings


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")

    print("=" * 60)
    print("  Structranet AI - Natural Language to Live GNS3 Topology")
    print("  (Topology + Hardware + Software Config + Deployment)")
    print("=" * 60 + "\n")

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Deploy-only mode: skip steps 1-6, just deploy an existing JSON ──────
    if args.deploy_only:
        print(f"[DEPLOY-ONLY] Loading {args.deploy_only} ...")
        try:
            with open(args.deploy_only) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERR] {e}")
            sys.exit(1)

        try:
            inventory = fetch_available_templates()
        except FetcherError as e:
            print(f"[WARN] {e}")
            inventory = []

        for w in validate_against_inventory(data, inventory):
            print(f"[WARN] {w}")

        try:
            deploy_hybrid_topology(
                GNS3Client(args.host, args.port), data,
                argparse.Namespace(overwrite=args.overwrite, start=args.start),
                inventory=inventory,
            )
        except DeploymentError as e:
            print(f"[ERR] {e}")
            sys.exit(1)
        return

    # ── Step 1/7: Fetch inventory ───────────────────────────────────────────
    print("[1/7] Fetching hardware inventory from GNS3...")
    try:
        inventory = fetch_available_templates()
    except FetcherError as e:
        print(f"[ERR] {e}")
        sys.exit(1)

    if not inventory:
        print("[ERR] No templates found. Install at least one GNS3 appliance.")
        sys.exit(1)

    print(f"  Found {len(inventory)} template(s): "
          f"{', '.join(d['name'] for d in inventory)}")

    # ── Step 2/7: Get user input ────────────────────────────────────────────
    print(f"\n[2/7] Describe the network you want.")
    print(f"  Available: {', '.join(d['name'] for d in inventory)}")
    if args.request:
        user_request = args.request
        print(f"  Request: {user_request}")
    else:
        user_request = input("\n  > ")
    if not user_request.strip():
        print("[ERR] No input. Exiting.")
        sys.exit(1)

    # ── Step 3/7: Phase 1 — Logical topology generation ─────────────────────
    print("\n[3/7] Phase 1 — AI generating logical topology...")
    result = generate_network_topology(user_request, inventory)
    if not result:
        print("[ERR] AI generation failed. Check your API key and model config.")
        sys.exit(1)
    print(f"  Generated {len(result.topology.nodes)} node(s), "
          f"{len(result.topology.links)} link(s)")

    # Quick validation check against inventory
    topo_dict = result.model_dump()
    for w in validate_against_inventory(topo_dict, inventory):
        print(f"  [WARN] {w}")

    # ── Step 4/7: Phase 1 — Hardware injection + save ───────────────────────
    print("\n[4/7] Phase 1 — Injecting hardware expansion (slots/adapters/ports)...")
    phase1_file = os.path.join(OUTPUT_DIR, "_topology.json")
    enriched = process_and_save_topology(result, phase1_file)
    if not enriched:
        print("[ERR] Hardware injection failed. Check logs above.")
        sys.exit(1)
    print(f"  Hardware-injected topology saved to: {phase1_file}")

    # Re-validate after injection
    topo_dict = enriched.model_dump()
    for w in validate_against_inventory(topo_dict, inventory):
        print(f"  [WARN] {w}")

    # ── Step 5/7: Phase 2 — Software configuration generation ───────────────
    final_file = args.output or os.path.join(OUTPUT_DIR, "final_topology.json")

    if args.no_phase2:
        print("\n[5/7] Phase 2 — SKIPPED (--no-phase2 flag set)")
        # Use Phase 1 output as the final topology
        final_dict = topo_dict
        # Save it as final
        with open(final_file, "w") as f:
            json.dump(final_dict, f, indent=2)
        print(f"  Phase 1 output saved as final: {final_file}")
    else:
        print("\n[5/7] Phase 2 — Generating software configurations (IP/routing/startup)...")
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

    # ── Step 6/7: Save final JSON ───────────────────────────────────────────
    print(f"\n[6/7] Final topology ready: {final_file}")
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
    print(f"  Summary: {node_count} node(s), {link_count} link(s), "
          f"{configured} node(s) with software configs")

    # ── Step 7/7: Deploy to GNS3 ────────────────────────────────────────────
    if args.no_deploy:
        print(f"\n[7/7] Deployment SKIPPED (--no-deploy).")
        print(f"  Deploy later with:")
        print(f"    python assembler.py {final_file} "
              f"--host {args.host} --port {args.port} --inventory <inv.json>")
    else:
        print(f"\n[7/7] Deploying to GNS3 at {args.host}:{args.port}...")
        try:
            deploy_hybrid_topology(
                GNS3Client(args.host, args.port), final_dict,
                argparse.Namespace(overwrite=args.overwrite, start=args.start),
                inventory=inventory,
            )
        except DeploymentError as e:
            print(f"[ERR] Deployment failed: {e}")
            print(f"  Topology JSON saved at: {final_file}")
            sys.exit(1)


if __name__ == "__main__":
    main()
