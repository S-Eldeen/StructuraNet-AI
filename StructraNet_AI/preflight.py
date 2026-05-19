"""
preflight.py — Environment profile collection and compatibility checks.

Collects the minimum user-specific information needed to generate portable
.gns3project files that are likely to run on the user's machine.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class PreflightProfile:
    gns3_version: str
    supports_iou: bool
    supports_qemu: bool
    supports_docker: bool
    strict_validation: bool = True
    require_template_image_map: bool = False
    template_image_map: Dict[str, str] | None = None

    @property
    def unsupported_node_types(self) -> set[str]:
        blocked: set[str] = set()
        if not self.supports_iou:
            blocked.add("iou")
        if not self.supports_qemu:
            blocked.add("qemu")
        if not self.supports_docker:
            blocked.add("docker")
        return blocked

    @property
    def normalized_template_image_map(self) -> Dict[str, str]:
        raw = self.template_image_map or {}
        return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip()}


def profile_from_dict(data: Dict[str, Any]) -> PreflightProfile:
    """Build a PreflightProfile from a plain dictionary."""
    return PreflightProfile(
        gns3_version=str(data.get("gns3_version", "2.2")),
        supports_iou=bool(data.get("supports_iou", False)),
        supports_qemu=bool(data.get("supports_qemu", True)),
        supports_docker=bool(data.get("supports_docker", False)),
        strict_validation=bool(data.get("strict_validation", True)),
        require_template_image_map=bool(data.get("require_template_image_map", False)),
        template_image_map=dict(data.get("template_image_map") or {}),
    )


def profile_to_dict(profile: PreflightProfile) -> Dict[str, Any]:
    """Convert profile to serializable dictionary."""
    return asdict(profile)


def _ask_bool(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


def load_profile(path: str) -> PreflightProfile:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return profile_from_dict(data)


def save_profile(profile: PreflightProfile, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile_to_dict(profile), indent=2), encoding="utf-8")


def collect_profile_interactive() -> PreflightProfile:
    print("\n[Preflight] Tell me about your GNS3 environment:")
    version = input("  GNS3 version (example: 2.2.54) [2.2]: ").strip() or "2.2"
    supports_iou = _ask_bool("  Is IOU usable on your setup?", default=False)
    supports_qemu = _ask_bool("  Is QEMU usable on your setup?", default=True)
    supports_docker = _ask_bool("  Is Docker usable on your setup?", default=False)
    strict = _ask_bool("  Fail fast on compatibility issues?", default=True)
    require_map = _ask_bool("  Enforce exact template->image mapping?", default=False)
    template_map: Dict[str, str] = {}
    if require_map:
        print("  Enter template=image pairs (empty line to finish), e.g. Cisco 3745=c3745-adventerprise.bin")
        while True:
            line = input("  mapping> ").strip()
            if not line:
                break
            if "=" not in line:
                print("    Invalid mapping. Use template=image")
                continue
            k, v = line.split("=", 1)
            template_map[k.strip()] = v.strip()
    return PreflightProfile(
        gns3_version=version,
        supports_iou=supports_iou,
        supports_qemu=supports_qemu,
        supports_docker=supports_docker,
        strict_validation=strict,
        require_template_image_map=require_map,
        template_image_map=template_map,
    )


def check_topology_compatibility(
    topology_dict: Dict[str, Any],
    profile: PreflightProfile,
) -> List[str]:
    issues: List[str] = []
    nodes = topology_dict.get("topology", {}).get("nodes", [])
    blocked = profile.unsupported_node_types

    if not str(profile.gns3_version).startswith("2.2"):
        issues.append(
            f"GNS3 version '{profile.gns3_version}' may be incompatible "
            "with revision 9 exports (recommended: 2.2.x)."
        )

    for node in nodes:
        ntype = str(node.get("node_type", "")).lower()
        name = node.get("name", node.get("node_id", "?"))
        if ntype in blocked:
            issues.append(
                f"Node '{name}' uses unsupported type '{ntype}' "
                "for your declared environment profile."
            )

    if profile.require_template_image_map:
        mapping = profile.normalized_template_image_map
        appliance_types = {"dynamips", "iou", "qemu", "docker", "virtualbox", "vmware"}
        for node in nodes:
            ntype = str(node.get("node_type", "")).lower()
            if ntype not in appliance_types:
                continue
            template = str(node.get("template_name", "")).strip()
            name = node.get("name", node.get("node_id", "?"))
            if not template:
                issues.append(
                    f"Node '{name}' ({ntype}) is missing template_name, cannot verify image mapping."
                )
                continue
            if template not in mapping:
                issues.append(
                    f"Node '{name}' template '{template}' is not in preflight template_image_map."
                )
    return issues


def filter_inventory_by_profile(
    inventory: List[Dict[str, Any]],
    profile: PreflightProfile,
) -> Tuple[List[Dict[str, Any]], set[str]]:
    """Return inventory filtered by profile support and blocked type set.

    When ``profile.require_template_image_map`` is True, a strict
    shift-left filter is applied in addition to the type-based block:

      * ``ethernet_switch`` and ``ethernet_hub`` always pass (built-in,
        no external image required).
      * Every other node type MUST have its ``name`` present as a key
        in ``profile.normalized_template_image_map`` — otherwise it is
        silently dropped so the LLM can never see or select it.
    """
    blocked = profile.unsupported_node_types
    filtered = [
        d for d in inventory
        if str(d.get("gns3_type", "")).lower() not in blocked
    ]

    # ── Shift-left image-map gate ──────────────────────────────────────────
    if profile.require_template_image_map:
        allowed_names = profile.normalized_template_image_map
        builtin_types = {"ethernet_switch", "ethernet_hub"}
        filtered = [
            d for d in filtered
            if str(d.get("gns3_type", "")).lower() in builtin_types
            or str(d.get("name", "")).strip() in allowed_names
        ]

    return filtered, blocked
