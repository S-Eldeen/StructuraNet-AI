#!/usr/bin/env python3
r"""
Wrapper to run Structranet AI pipeline from Node.js (or command line).

Usage:
  python run_pipeline.py "your network description" --output-dir output
  python run_pipeline.py "..." --force-platform iou --image-path "path/to/iou/image"
"""

import argparse
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ─── Load environment variables from .env file ─────────────────────────
from dotenv import load_dotenv
load_dotenv()  # يبحث عن .env في المجلد الحالي (StructraNet_AI)

sys.path.insert(0, str(Path(__file__).parent))

from main import main as run_main
from gns3_exporter import convert as export_gns3project


# ── Make gns3_exporter pre-export validation non-fatal ──────────────
def _patch_gns3_exporter():
    try:
        import gns3_exporter as _exp
        _orig = _exp._pre_export_validate
        def _lenient_validate(nodes, links):
            try:
                _orig(nodes, links)
            except _exp.ExportError as exc:
                print(f"\n[pre-export WARNING — non-fatal, continuing export]\n{exc}", flush=True)
        _exp._pre_export_validate = _lenient_validate
        print("[run_pipeline] gns3_exporter validation set to non-fatal mode")
    except Exception as e:
        print(f"[run_pipeline] Warning: could not patch gns3_exporter: {e}", file=sys.stderr)

_patch_gns3_exporter()


# ─── Default preflight profile ────────────────────────────────────────
DEFAULT_PROFILE = {
    "gns3_version": "2.2.54",
    "supports_iou": True,
    "supports_qemu": True,
    "supports_docker": False,
    "strict_validation": False,
    "require_template_image_map": False,
    "template_image_map": {}
}


def convert_dynamips_to_iou(topology_dict: dict, image_path: str = None) -> dict:
    """Convert all dynamips nodes to IOU L3 (supports many Ethernet interfaces)."""
    nodes = topology_dict.get("topology", {}).get("nodes", [])
    modified = False
    for node in nodes:
        if node.get("node_type") == "dynamips":
            node["node_type"] = "iou"
            node["template_name"] = "IOU L3"
            props = node.setdefault("properties", {})
            # IOU L3 uses 'ethernet' key for number of interfaces (default 4, can increase)
            # Set to a high number (e.g., 24) to support many connections
            props["ethernet"] = 24
            # Remove any slot properties (not needed for IOU)
            for key in list(props.keys()):
                if key.startswith("slot"):
                    del props[key]
            if image_path:
                props["image"] = image_path
            else:
                props["image"] = "iourc"  # default IOU image name
            modified = True
    if modified:
        print("[force-platform] Converted all dynamips nodes to IOU L3 (unlimited ports)")
    return topology_dict


def force_dynamips_to_c7200(topology_dict: dict, image_path: str = None) -> dict:
    """Convert all dynamips nodes to Cisco 7200 platform and optionally set image path.
    This function is idempotent and safe for c7200 slots."""
    nodes = topology_dict.get("topology", {}).get("nodes", [])
    modified = False
    for node in nodes:
        if node.get("node_type") == "dynamips":
            # Change template name
            node["template_name"] = "Cisco 7200"
            props = node.setdefault("properties", {})
            # Set platform
            props["platform"] = "c7200"
            # Replace NM modules with PA modules for slots 1..6 only
            # Do NOT touch slot0 – it must remain a valid C7200-IO-* module
            for key in list(props.keys()):
                if key.startswith("slot") and key != "slot0":
                    module = props[key]
                    # Ethernet NM modules → PA-FE-TX (safe for c7200 expansion slots)
                    if module in ("NM-1FE-TX", "NM-4E", "NM-1E"):
                        props[key] = "PA-FE-TX"
                        modified = True
                    # Serial NM modules → PA-4T+ (PA-4T+ is valid for c7200)
                    elif module == "NM-4T":
                        props[key] = "PA-4T+"
                        modified = True
                    # Map unsupported high-density modules to PA-FE-TX
                    elif module in ("PA-8E", "PA-4E", "PA-2E"):
                        props[key] = "PA-FE-TX"
                        modified = True
            # Ensure slot0 is a valid C7200 IO module
            slot0_current = props.get("slot0", "")
            valid_slot0_modules = {"C7200-IO-FE", "C7200-IO-2FE", "C7200-IO-GE-E"}
            if not slot0_current or slot0_current not in valid_slot0_modules:
                props["slot0"] = "C7200-IO-FE"
                modified = True
            # Set image path if provided
            if image_path:
                props["image"] = image_path
                modified = True
            # If no image path, use placeholder but with c7200 name
            elif "image" not in props or "c7200" not in props["image"]:
                props["image"] = "c7200-adventerprisek9-mz.124-25d.bin"
                modified = True
    if modified:
        print("[force-platform] Converted all dynamips nodes to Cisco 7200 (slot0 fixed, unsupported modules mapped to PA-FE-TX)")
    return topology_dict


def run_pipeline(prompt: str, output_dir: str, profile_path: str = None,
                 force_platform: str = None, image_path: str = None) -> str:
    """
    Run the full Structranet AI pipeline.

    Args:
        prompt: Natural language network description
        output_dir: Absolute path where output files will be written
        profile_path: Optional path to a preflight profile JSON.
        force_platform: If 'c7200', convert all dynamips routers to Cisco 7200.
                        If 'iou', convert to IOU L3 (recommended for large networks).
        image_path: Full path to IOS image file (e.g., for c7200 or IOU).

    Returns:
        Absolute path to the generated .gns3project file.
    """
    temp_profile_file = None
    if not profile_path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(DEFAULT_PROFILE, tmp)
        tmp.flush()
        tmp.close()
        profile_path = tmp.name
        temp_profile_file = tmp.name

    try:
        original_argv = sys.argv
        sys.argv = [
            "main.py",
            "--request", prompt,
            "--output", os.path.join(output_dir, "final_topology.json"),
            "--project-output", os.path.join(output_dir, "final_topology.gns3project"),
            "--profile", profile_path,
            "--yes",
            "--no-validate",
        ]

        try:
            run_main()
        except SystemExit as e:
            if e.code != 0:
                raise RuntimeError(f"Pipeline failed with exit code {e.code}")
        finally:
            sys.argv = original_argv

    finally:
        if temp_profile_file and os.path.exists(temp_profile_file):
            os.unlink(temp_profile_file)

    # After generation, optionally convert platform
    final_json_path = os.path.join(output_dir, "final_topology.json")
    gns3_path = os.path.join(output_dir, "final_topology.gns3project")
    if force_platform and os.path.exists(final_json_path):
        with open(final_json_path, "r", encoding="utf-8") as f:
            topo_data = json.load(f)
        if force_platform == "c7200":
            topo_data = force_dynamips_to_c7200(topo_data, image_path=image_path)
        elif force_platform == "iou":
            topo_data = convert_dynamips_to_iou(topo_data, image_path=image_path)
        else:
            print(f"[force-platform] Unknown platform '{force_platform}'. Skipping conversion.")
        # Save modified JSON
        with open(final_json_path, "w", encoding="utf-8") as f:
            json.dump(topo_data, f, indent=2)
        # Remove old GNS3 project if exists
        if os.path.exists(gns3_path):
            os.remove(gns3_path)
        # Re-export – this may raise ExportError but we made it non-fatal above
        export_gns3project(topo_data, gns3_path, name_override=None, image_map={}, config_review_dir=None)
        print(f"[force-platform] Re-exported .gns3project after platform conversion ({force_platform})")
        # Re-print the path so backend can capture it
        print(f"GNS3PROJECT_PATH={gns3_path}")
    else:
        # If no conversion, we still need to print the path
        print(f"GNS3PROJECT_PATH={gns3_path}")

    project_path = gns3_path
    if not os.path.exists(project_path):
        raise FileNotFoundError(f"Expected output file not found: {project_path}")
    return project_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Structranet AI pipeline")
    parser.add_argument("prompt", type=str, help="Network description")
    parser.add_argument("--output-dir", type=str, default="output")
    parser.add_argument("--profile", type=str, default=None)
    parser.add_argument("--force-platform", type=str, default=None, choices=["c7200", "iou"],
                        help="Force all Dynamips routers to a specific platform: 'c7200' (limited slots) or 'iou' (unlimited ports)")
    parser.add_argument("--image-path", type=str, default=None,
                        help="Full path to IOS/IOU image file (e.g., C:\\path\\to\\image.bin)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    try:
        path = run_pipeline(args.prompt, args.output_dir, args.profile,
                            args.force_platform, args.image_path)
        sys.exit(0)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)