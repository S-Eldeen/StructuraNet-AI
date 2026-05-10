"""
test_pipeline.py — Run the Structranet AI pipeline WITHOUT a GNS3 server.

Uses a fake hardware inventory so you can test the full pipeline
(ai_agent → hardware injection → config_agent) and get a JSON file
ready for deployment by your teammate.

Usage:
    python test_pipeline.py "3 routers in a triangle with serial WAN links"
    python test_pipeline.py "campus network with 2 VLANs and VPCS hosts"
"""

import json
import logging
import os
import sys

# Ensure project directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_agent import generate_network_topology, process_and_save_topology
from topology_finalizer import apply_switch_port_patches
from config_agent import run_phase2
from schema import GNS3Project

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("structranet.test")

# ── Fake inventory (simulates what gns3_fetcher would return) ──────────────────
# These are common GNS3 built-in templates. Add/remove to match what your
# teammate actually has installed in their GNS3 server.
FAKE_INVENTORY = [
    {"name": "c7200",          "gns3_type": "dynamips",        "template_id": "fake-c7200",          "category": "router",     "port_count": 3,  "builtin": True},
    {"name": "c3745",          "gns3_type": "dynamips",        "template_id": "fake-c3745",          "category": "router",     "port_count": 6,  "builtin": True},
    {"name": "c3725",          "gns3_type": "dynamips",        "template_id": "fake-c3725",          "category": "router",     "port_count": 6,  "builtin": True},
    {"name": "c3660",          "gns3_type": "dynamips",        "template_id": "fake-c3660",          "category": "router",     "port_count": 5,  "builtin": True},
    {"name": "c3640",          "gns3_type": "dynamips",        "template_id": "fake-c3640",          "category": "router",     "port_count": 4,  "builtin": True},
    {"name": "Switch",         "gns3_type": "ethernet_switch", "template_id": "fake-switch",         "category": "switch",     "port_count": 128,"builtin": True},
    {"name": "Hub",            "gns3_type": "ethernet_hub",    "template_id": "fake-hub",            "category": "switch",     "port_count": 128,"builtin": True},
    {"name": "VPCS",           "gns3_type": "vpcs",            "template_id": "fake-vpcs",           "category": "guest",      "port_count": 1,  "builtin": True},
    {"name": "NAT",            "gns3_type": "nat",             "template_id": "fake-nat",            "category": "guest",      "port_count": 1,  "builtin": True},
    {"name": "Cloud",          "gns3_type": "cloud",           "template_id": "fake-cloud",          "category": "guest",      "port_count": 1,  "builtin": True},
    {"name": "IOU-L3",         "gns3_type": "iou",             "template_id": "fake-iou-l3",         "category": "router",     "port_count": 16, "builtin": False},
    {"name": "IOU-L2",         "gns3_type": "iou",             "template_id": "fake-iou-l2",         "category": "switch",     "port_count": 16, "builtin": False},
]

OUTPUT_DIR = "output"


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_pipeline.py \"your network description\"")
        print()
        print("Examples:")
        print('  python test_pipeline.py "3 routers in a triangle with serial WAN links"')
        print('  python test_pipeline.py "campus network with core switch, 2 access switches, and VPCS hosts"')
        print('  python test_pipeline.py "2 c3745 routers connected via serial link with VPCS on each side"')
        sys.exit(1)

    user_request = " ".join(sys.argv[1:])
    inventory = FAKE_INVENTORY

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  Structranet AI — Pipeline Test (No GNS3 Server)")
    print("=" * 60)
    print()
    print(f"  Request: {user_request}")
    print(f"  Inventory: {len(inventory)} device(s)")
    print(f"  Available: {', '.join(d['name'] for d in inventory)}")
    print()

    # ── Step 1: AI topology generation ──────────────────────────────────────
    print("[1/5] AI generating logical topology...")
    result = generate_network_topology(user_request, inventory)
    if not result:
        print("[ERR] AI generation failed. Check your .env file (ROUTER_API_KEY).")
        sys.exit(1)
    print(f"  Generated {len(result.topology.nodes)} node(s), "
          f"{len(result.topology.links)} link(s)")

    # ── Step 2: Hardware injection + save ───────────────────────────────────
    print("\n[2/5] Injecting hardware expansion (slots/adapters/ports)...")
    phase1_file = os.path.join(OUTPUT_DIR, "_topology.json")
    enriched = process_and_save_topology(result, phase1_file)
    if not enriched:
        print("[ERR] Hardware injection failed.")
        sys.exit(1)
    print(f"  Saved to: {phase1_file}")

    # ── Step 3: Switch port patches ─────────────────────────────────────────
    print("\n[3/5] Patching switch ports (VLAN trunk/access layout)...")
    topo_dict = enriched.model_dump()
    apply_switch_port_patches(topo_dict)
    with open(phase1_file, "w", encoding="utf-8") as f:
        json.dump(topo_dict, f, indent=2)
    print("  Switch port patches applied")

    # ── Step 4: Phase 2 — Software configs ──────────────────────────────────
    final_file = os.path.join(OUTPUT_DIR, "final_topology.json")
    print("\n[4/5] Generating software configurations (IP/routing/startup)...")
    final_dict = run_phase2(phase1_file, final_file)
    if final_dict is None:
        print("[WARN] Phase 2 failed — saving Phase 1 topology (no software configs).")
        final_dict = topo_dict
        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(final_dict, f, indent=2)
    else:
        print(f"  Phase 2 complete.")

    # ── Step 5: Summary ─────────────────────────────────────────────────────
    print(f"\n[5/5] Done! Final topology saved to: {final_file}")
    node_count = len(final_dict.get("topology", {}).get("nodes", []))
    link_count = len(final_dict.get("topology", {}).get("links", []))
    configured = sum(
        1 for n in final_dict.get("topology", {}).get("nodes", [])
        if n.get("properties") and any(
            k in n["properties"]
            for k in ("startup_config_content", "startup_script", "start_command")
        )
    )
    print(f"  Summary: {node_count} node(s), {link_count} link(s), "
          f"{configured} node(s) with software configs")
    print()
    print("  Your teammate can deploy this with:")
    print(f"    python assembler.py {final_file} --host <GNS3_HOST> --port 3080")


if __name__ == "__main__":
    main()
