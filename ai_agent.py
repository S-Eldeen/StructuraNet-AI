"""
Structranet AI — AI Agent  (V3.0)

Translates a natural language request into a validated GNS3Project.

Two-step pipeline (replaces the single giant LLM call):
  Step 1: LLM → TopologyRequest (nodes + logical connections, NO port numbers)
  Step 2: port_assigner.py → Link objects with correct adapter/port numbers
  Step 3: hw_config.inject_hardware_config → slot/adapter expansion
  Step 4: Pydantic validation (hard errors, no silent fixes)
  Step 5: If errors → feed them back to LLM and retry (max 3 attempts)

The LLM prompt is now ~80 lines instead of 250.  The LLM only needs to decide
WHAT connects to WHAT — not how to compute adapter/port numbers.

Edit mode: generate_edited_topology patches an existing TopologyRequest using
the same two-step pipeline.  safe_merge_edited_topology handles node_id integrity.

Chat mode: generate_chat_reply for conversational responses.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import (
    OpenAI, APITimeoutError, APIConnectionError,
    RateLimitError, InternalServerError,
)

from hw_config import inject_hardware_config
from port_assigner import build_topology_from_request
from schema import (
    GNS3Project, TopologyRequest, validate_topology_request, validate_topology,
)

load_dotenv()
logger = logging.getLogger("structranet.ai_agent")

DEFAULT_MODEL = os.getenv("AI_MODEL", "openrouter/owl-alpha")
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "8192"))
MAX_RETRIES = 3

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("ROUTER_API_KEY")
        base_url = os.getenv("ROUTER_BASE_URL")
        if not key:
            raise ValueError("ROUTER_API_KEY missing. Check your .env file.")
        _client = OpenAI(base_url=base_url, api_key=key, timeout=500.0)
    return _client


def _call_with_retry(func, max_retries: int = 2):
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("Transient API error (attempt %d/%d): %s — retry in %ds",
                               attempt, max_retries, type(e).__name__, wait)
                time.sleep(wait)
            else:
                raise
    return None


def _extract_json(text: str) -> str:
    """Strip thought blocks and markdown fences, return raw JSON string."""
    cleaned = re.sub(r"<thought_process>.*?</thought_process>", "",
                     text.strip(), flags=re.DOTALL)
    cleaned = re.sub(r"^```\w*\n?", "", cleaned.strip()).rstrip("`").strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    return match.group(1) if match else text


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1 prompt: nodes + connections only
# ═══════════════════════════════════════════════════════════════════════════════

# Hardware port limits — shown to LLM only to prevent topologically impossible
# designs (e.g. 10 links to a c7200).  Port NUMBERS are not the LLM's concern.
_DYNAMIPS_MAX_LINKS = {
    "c7200": 3, "c3745": 6, "c3725": 6, "c3660": 5,
    "c3640": 4, "c3620": 4, "c2691": 6, "c2600": 2, "c1700": 2,
}
_SINGLE_LINK_TYPES = {"vpcs", "traceng", "nat"}


def _build_step1_prompt(devices: list[dict]) -> str:
    inventory = [
        {"name": d["name"], "type": d["gns3_type"],
         "category": d.get("category", ""), "max_links": d.get("port_count")}
        for d in devices
    ]

    # Build per-device link-limit lines
    limit_lines = []
    for d in devices:
        gtype = d["gns3_type"]
        name = d["name"]
        pc = d.get("port_count")
        if gtype in _SINGLE_LINK_TYPES:
            limit_lines.append(f"  - {name} ({gtype}): MAX 1 link. Insert a switch if more needed.")
        elif gtype == "dynamips":
            platform = name.lower()
            max_l = _DYNAMIPS_MAX_LINKS.get(platform, 3)
            limit_lines.append(
                f"  - {name} (dynamips): MAX {max_l} total links (PCI bus limit). "
                f"Use Core-SW + Router-on-a-Stick if you need more subnets."
            )
        elif pc is not None:
            limit_lines.append(f"  - {name} ({gtype}): MAX {pc} links.")

    limit_text = "\n".join(limit_lines) or "  (counts unavailable — be conservative)"
    inv_json = json.dumps(inventory, indent=2)

    return f"""You are the Core Architect Agent for Structranet AI.
Translate the user's natural language request into a network topology.

IMPORTANT: You produce ONLY the logical design — which devices connect to which.
DO NOT produce adapter numbers, port numbers, or any port assignments.
Those are computed automatically by the system after you respond.

AVAILABLE HARDWARE (use ONLY these):
{inv_json}

LINK LIMITS (do NOT exceed):
{limit_text}

RULES:
1. ZERO HALLUCINATION: Only use device names from the inventory above.
2. node_type must be a GNS3 literal: dynamips, qemu, vpcs, ethernet_switch,
   ethernet_hub, docker, iou, cloud, traceng, frame_relay_switch, atm_switch,
   virtualbox, vmware, nat.
3. template_name must be the exact inventory name (e.g. "c7200", "Switch").
4. name is a human-readable label (e.g. "R1-Edge", "Core-SW1", "PC1").
5. node_id is a short unique key (e.g. "R1", "SW1", "PC1").
6. DO NOT assign port numbers — just list connections as "from_node → to_node".
7. No two connections may link the same pair of nodes (no parallel links).
8. Every node must be reachable from every other node (fully connected graph).
9. VPCS/TraceNG/NAT nodes may have AT MOST 1 connection. Use a switch if more needed.
10. If a router needs more subnet switches than its link limit allows, use the
    Core-SW + Router-on-a-Stick pattern (router → 1 core switch → N access switches).
11. link_type is "ethernet" (default) or "serial" (for WAN router-to-router links).
12. If a device isn't available, substitute with the closest available match.

OUTPUT: A JSON object matching this schema exactly:
{{
  "name": "<project name>",
  "nodes": [
    {{"node_id": "R1", "name": "R1-Main", "node_type": "dynamips",
      "template_name": "<exact inventory name>", "compute_id": "local"}}
  ],
  "connections": [
    {{"from_node": "R1", "to_node": "SW1", "link_type": "ethernet"}}
  ]
}}

Respond with ONLY the JSON object. No markdown fences. No explanation."""


def _call_step1(
    user_request: str,
    devices: list[dict],
    previous_errors: list[str] = None,
) -> Optional[TopologyRequest]:
    """Call the LLM to generate nodes + connections."""
    client = _get_client()
    prompt = _build_step1_prompt(devices)

    messages = [{"role": "system", "content": prompt}]

    if previous_errors:
        error_text = "\n".join(f"  - {e}" for e in previous_errors)
        messages.append({
            "role": "user",
            "content": (
                f"{user_request}\n\n"
                f"PREVIOUS ATTEMPT FAILED WITH THESE ERRORS — fix them:\n{error_text}"
            ),
        })
    else:
        messages.append({"role": "user", "content": user_request})

    schema_json = json.dumps(TopologyRequest.model_json_schema(), indent=2)
    messages[0]["content"] += f"\n\nJSON Schema:\n{schema_json}"

    raw_text = ""
    try:
        def _call():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
            )

        response = _call_with_retry(_call)
        if not response or not response.choices:
            logger.error("LLM returned empty response")
            return None

        raw_text = response.choices[0].message.content or ""
        clean = _extract_json(raw_text)
        data = json.loads(clean)
        result = TopologyRequest.model_validate(data)
        logger.info("Step 1 succeeded: %d nodes, %d connections",
                    len(result.nodes), len(result.connections))
        return result

    except Exception as e:
        logger.warning("Step 1 failed: %s", e)
        if raw_text:
            logger.debug("Raw output: %s", raw_text[:500])
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Main generation pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def generate_network_topology(
    user_request: str, devices: list[dict]
) -> Optional[GNS3Project]:
    """
    Generate a GNS3Project from a natural language request.

    Pipeline:
      1. LLM generates TopologyRequest (nodes + connections, NO port numbers)
      2. port_assigner.py assigns adapter/port numbers deterministically
      3. Pydantic validation (hard errors)
      4. If errors → feed back to LLM and retry (max MAX_RETRIES times)
    """
    previous_errors: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Generation attempt %d/%d", attempt, MAX_RETRIES)

        # Step 1: LLM generates nodes + logical connections
        topo_request = _call_step1(user_request, devices, previous_errors or None)
        if topo_request is None:
            logger.error("LLM call failed on attempt %d", attempt)
            continue

        # Step 2: Validate the topology request
        req_errors = validate_topology_request(topo_request.model_dump())
        if req_errors:
            logger.warning("TopologyRequest validation failed: %s", req_errors)
            previous_errors = req_errors
            continue

        # Step 3: Deterministic port assignment
        try:
            project_dict = build_topology_from_request(topo_request)
        except ValueError as e:
            logger.warning("Port assignment failed: %s", e)
            previous_errors = [str(e)]
            continue

        # Step 4: Validate the full topology
        topo_errors = validate_topology(project_dict)
        if topo_errors:
            logger.warning("Topology validation failed: %s", topo_errors)
            # Feed errors back to LLM — but note: port errors are code bugs,
            # not LLM errors.  Only feed back structural errors (node/link counts,
            # connectivity, etc.)
            structural_errors = [
                e for e in topo_errors
                if "port_assigner.py" not in e
            ]
            previous_errors = structural_errors or topo_errors
            continue

        # All good
        logger.info("Generation succeeded on attempt %d", attempt)
        try:
            return GNS3Project.model_validate(project_dict)
        except Exception as e:
            logger.error("Final model_validate failed: %s", e)
            previous_errors = [str(e)]
            continue

    logger.error("All %d generation attempts failed", MAX_RETRIES)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Post-generation: hardware injection + save
# ═══════════════════════════════════════════════════════════════════════════════

def process_and_save_topology(
    raw_topology: GNS3Project, output_file: str
) -> Optional[GNS3Project]:
    """Run hardware injection and save to disk.

    Steps:
      1. Pydantic model → dict
      2. inject_hardware_config() — expands slots/adapters/ports_mapping
      3. Re-validate through Pydantic
      4. Save JSON to output_file
      5. Return enriched GNS3Project
    """
    raw_dict = raw_topology.model_dump()
    enriched_dict = inject_hardware_config(raw_dict)

    try:
        result = GNS3Project.model_validate(enriched_dict)
    except Exception as e:
        logger.error("Re-validation after hardware injection failed: %s", e)
        return None

    try:
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Topology saved to %s", out)
    except OSError as e:
        logger.error("Failed to save topology: %s", e)
        return None

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Edit mode
# ═══════════════════════════════════════════════════════════════════════════════

def _build_edit_prompt(current_topology_json: str, instruction: str,
                       devices: list[dict]) -> str:
    inventory = [
        {"name": d["name"], "type": d["gns3_type"], "category": d.get("category", "")}
        for d in devices
    ]
    return f"""You are the Topology Patcher Agent for Structranet AI.
Modify an EXISTING network topology based on the user's edit instruction.

AVAILABLE HARDWARE:
{json.dumps(inventory, indent=2)}

CURRENT TOPOLOGY (nodes + connections only — no port numbers):
{current_topology_json}

RULES:
1. Preserve ALL existing node_id values for unchanged nodes.
2. Only modify nodes/connections explicitly mentioned in the instruction.
3. For NEW nodes, assign a new unique node_id by incrementing from the maximum
   existing numeric suffix (e.g. if R3 exists, next router is R4).
4. Output the COMPLETE patched topology — not just the changes.
5. DO NOT assign port numbers — just list connections as from_node/to_node pairs.
6. No two connections may link the same pair of nodes.
7. The patched topology must remain fully connected.
8. New nodes must have "compute_id": "local".
9. Respond with ONLY the JSON object. No markdown fences.

Output schema: same as the input (name, nodes, connections)."""


def generate_edited_topology(
    instruction: str,
    current_topology: dict,
    devices: list[dict],
) -> Optional[GNS3Project]:
    """Patch an existing topology based on an edit instruction.

    Works on the TopologyRequest level (nodes + connections, no port numbers).
    Port numbers are recomputed from scratch after the edit.
    """
    client = _get_client()

    # Strip down to just nodes + connections (remove port assignments if present)
    topo = current_topology.get("topology", current_topology)
    nodes_raw = topo.get("nodes", [])

    # Convert Link format → Connection format for the LLM prompt
    connections_raw = []
    for link in topo.get("links", []):
        eps = link.get("nodes", [])
        if len(eps) >= 2:
            connections_raw.append({
                "from_node": eps[0]["node_id"],
                "to_node": eps[1]["node_id"],
                "link_type": link.get("link_type", "ethernet"),
            })

    simplified = {
        "name": current_topology.get("name", "Network"),
        "nodes": [
            {
                "node_id": n["node_id"],
                "name": n["name"],
                "node_type": n["node_type"],
                "template_name": n["template_name"],
                "compute_id": n.get("compute_id", "local"),
            }
            for n in nodes_raw
        ],
        "connections": connections_raw,
    }

    prompt = _build_edit_prompt(json.dumps(simplified, indent=2), instruction, devices)
    schema_json = json.dumps(TopologyRequest.model_json_schema(), indent=2)
    full_prompt = prompt + f"\n\nJSON Schema:\n{schema_json}"

    previous_errors: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        messages = [{"role": "system", "content": full_prompt}]
        content = instruction
        if previous_errors:
            error_text = "\n".join(f"  - {e}" for e in previous_errors)
            content += f"\n\nPREVIOUS ATTEMPT ERRORS — fix them:\n{error_text}"
        messages.append({"role": "user", "content": content})

        raw_text = ""
        try:
            def _call():
                return client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=messages,
                    max_tokens=MAX_TOKENS,
                    response_format={"type": "json_object"},
                )

            response = _call_with_retry(_call)
            if not response or not response.choices:
                continue

            raw_text = response.choices[0].message.content or ""
            clean = _extract_json(raw_text)
            data = json.loads(clean)
            topo_request = TopologyRequest.model_validate(data)

        except Exception as e:
            logger.warning("Edit attempt %d parse/validate failed: %s", attempt, e)
            previous_errors = [str(e)]
            continue

        # Run safe_merge to catch node_id integrity issues
        patched_dict, issues = safe_merge_edited_topology(simplified, topo_request.model_dump())
        for issue in issues:
            logger.warning("safe_merge: %s", issue)

        # Re-validate after merge
        errors = validate_topology_request(patched_dict)
        if errors:
            previous_errors = [e for e in errors if "port_assigner" not in e]
            continue

        # Assign ports deterministically
        try:
            merged_request = TopologyRequest.model_validate(patched_dict)
            project_dict = build_topology_from_request(merged_request)
        except Exception as e:
            logger.warning("Port assignment failed on edit attempt %d: %s", attempt, e)
            previous_errors = [str(e)]
            continue

        topo_errors = validate_topology(project_dict)
        if topo_errors:
            previous_errors = [e for e in topo_errors if "port_assigner" not in e]
            continue

        logger.info("Edit succeeded on attempt %d", attempt)
        return GNS3Project.model_validate(project_dict)

    logger.error("Edit failed after %d attempts", MAX_RETRIES)
    return None


def safe_merge_edited_topology(
    original: dict,
    patched: dict,
) -> tuple[dict, list[str]]:
    """Verify node_id integrity between original and patched TopologyRequest dicts.

    Checks:
      1. Warn about deleted node_ids (may be intentional or LLM error)
      2. Remove dangling connections referencing deleted node_ids
      3. Detect duplicate node_ids in patched topology
      4. Revert node_type / template_name drift on surviving nodes

    Returns:
        (patched_dict, issues) — patched_dict may be auto-corrected
    """
    issues: list[str] = []

    orig_nodes = original.get("nodes", [])
    patch_nodes = patched.get("nodes", [])
    patch_conns = patched.get("connections", [])

    orig_map = {n.get("node_id"): n for n in orig_nodes if n.get("node_id")}
    patch_map = {n.get("node_id"): n for n in patch_nodes if n.get("node_id")}
    orig_ids = set(orig_map.keys())
    patch_ids = set(patch_map.keys())

    # Check 1: deleted nodes
    deleted = orig_ids - patch_ids
    if deleted:
        issues.append(f"WARNING: Node IDs removed: {sorted(deleted)}")

    # Check 2: dangling connections
    clean_conns = []
    for c in patch_conns:
        a, b = c.get("from_node", ""), c.get("to_node", "")
        if a not in patch_ids or b not in patch_ids:
            issues.append(f"AUTO-CORRECTED: Removed dangling connection {a}<->{b}")
        else:
            clean_conns.append(c)
    if len(clean_conns) != len(patch_conns):
        patched = dict(patched)
        patched["connections"] = clean_conns

    # Check 3: duplicate node_ids
    seen: dict[str, str] = {}
    for n in patch_nodes:
        nid = n.get("node_id", "")
        if nid in seen:
            issues.append(f"ERROR: Duplicate node_id '{nid}' in patched topology")
        else:
            seen[nid] = n.get("name", "?")

    # Check 4: attribute drift on surviving nodes
    surviving = orig_ids & patch_ids
    for nid in surviving:
        orig_n = orig_map[nid]
        patch_n = patch_map[nid]
        for attr in ("node_type", "template_name"):
            if orig_n.get(attr) != patch_n.get(attr):
                issues.append(
                    f"AUTO-CORRECT: Node '{nid}' {attr} changed "
                    f"'{orig_n.get(attr)}' → '{patch_n.get(attr)}'. Reverting."
                )
                patch_n[attr] = orig_n.get(attr)

    return patched, issues


# ═══════════════════════════════════════════════════════════════════════════════
#  Chat mode
# ═══════════════════════════════════════════════════════════════════════════════

def generate_chat_reply(user_message: str, chat_history: list = None) -> str:
    """Generate a conversational reply for non-topology questions."""
    client = _get_client()

    system_prompt = """You are Structranet AI, an intelligent network topology assistant.
You help users design GNS3 network topologies using natural language.

You can create topologies, modify them, and answer questions about networking,
GNS3, Cisco IOS, and network architecture. Be concise and technically accurate."""

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        for msg in chat_history[-10:]:
            messages.append({"role": msg.get("role", "user"),
                              "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    try:
        def _call():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
            )

        response = _call_with_retry(_call)
        if response and response.choices:
            return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("Chat reply failed: %s", e)

    return "I'm having trouble responding right now. Please try again."