"""
config_agent.py — Phase 2 Software Configuration Agent for Structranet AI

Takes the finalized Phase 1 JSON (hardware-injected topology) and generates
software configurations (IP addressing, routing, startup scripts) using the LLM.

Pipeline:
  1. Build Configuration Brief via context_builder
  2. Send brief + strict prompt to LLM
  3. LLM returns {node_id: {config_key: config_value}} flat map
  4. Three-Gate Safe Merge into Phase 1 JSON
  5. Save final integrated topology

Safety guarantee: The whitelist merge makes it IMPOSSIBLE for the LLM to
overwrite hardware properties (slots, adapters, ports_mapping), regardless
of what it returns.
"""

import os
import json
import re
import time
import logging
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from dotenv import load_dotenv
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, InternalServerError

from context_builder import build_configuration_brief
from schema import GNS3Project

load_dotenv()
logger = logging.getLogger("structranet.config_agent")

ROUTER_BASE_URL = os.getenv("ROUTER_BASE_URL")
DEFAULT_MODEL = os.getenv("AI_MODEL", "openrouter/owl-alpha")
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "8192"))

# Lazy client singleton (separate from ai_agent's to avoid state coupling)
_client: Optional[OpenAI] = None


# ═══════════════════════════════════════════════════════════════════════════════
#  Gate 1: Software Config Key Whitelist
# ═══════════════════════════════════════════════════════════════════════════════

# ONLY these keys are allowed to be written by the LLM.
# Any key not on this list (e.g. slot1, adapters, ports_mapping) is REJECTED.
#
# Source — GNS3 server verified:
#   startup_config_content  → dynamips, iou, qemu  (Cisco IOS / device config)
#   startup_script          → vpcs                  (NOT startup_script_content!)
#   start_command           → docker                (container entrypoint)
#   environment             → docker                (env vars dict)
SOFTWARE_CONFIG_KEYS: FrozenSet[str] = frozenset([
    "startup_config_content",
    "startup_script",
    "start_command",
    "environment",
])

# Allowed value types per config key (Gate 3)
ALLOWED_VALUE_TYPES: Dict[str, tuple] = {
    "startup_config_content": (str,),
    "startup_script":         (str,),
    "start_command":          (str,),
    "environment":            (dict, str),  # dict preferred, str accepted for flexibility
}


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM Client
# ═══════════════════════════════════════════════════════════════════════════════

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("ROUTER_API_KEY")
        base_url = os.getenv("ROUTER_BASE_URL")
        if not key:
            raise ValueError("API Key missing! Check your .env file.")
        _client = OpenAI(base_url=base_url, api_key=key, timeout=500.0)
    return _client


def _call_with_retry(func, max_retries: int = 2):
    """Call an OpenAI API function with retry on transient errors."""
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("Transient error (attempt %d/%d): %s — retrying in %ds",
                               attempt, max_retries, type(e).__name__, wait)
                time.sleep(wait)
            else:
                raise
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompt Builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_phase2_prompt(brief: str) -> str:
    """Build the system prompt for the Phase 2 configuration LLM call.

    Enforces the output format and Three-Gate Safe Merge rules so the LLM
    knows exactly what it can and cannot write.
    """
    return f"""You are the Software Configuration Agent for Structranet AI.
Your job is to generate IP addressing, routing, and startup configurations
for the network topology described in the brief below.

{brief}

OUTPUT FORMAT:
Return a JSON object where:
  - Keys are node_id values from the brief (e.g., "R1", "PC1")
  - Values are objects containing ONLY software config properties
  - Do NOT include nodes that need no config (switches, hubs, NAT, cloud)

Example output (Router-on-a-Stick with 3 VLANs):
{{
  "R1": {{
    "startup_config_content": "hostname R1\\n!\\ninterface FastEthernet0/0.10\\n encapsulation dot1Q 10\\n ip address 10.0.10.1 255.255.255.0\\n!\\ninterface FastEthernet0/0.20\\n encapsulation dot1Q 20\\n ip address 10.0.20.1 255.255.255.0\\n!\\ninterface FastEthernet0/0.30\\n encapsulation dot1Q 30\\n ip address 10.0.30.1 255.255.255.0\\n!\\nrouter ospf 1\\n network 10.0.0.0 0.0.255.255 area 0\\n!"
  }},
  "PC1": {{
    "startup_script": "ip 10.0.10.10/24 10.0.10.1\\nsave\\n"
  }}
}}

CONFIG KEY RULES (use EXACTLY these property names):
  - dynamips / iou / qemu routers → "startup_config_content" (Cisco IOS string)
  - vpcs hosts                     → "startup_script" (NOT startup_script_content!)
  - docker containers              → "start_command" + "environment"

══════════════════════════════════════════════════════════════
  GENERALIZED L3 ARCHITECTURE RULES
══════════════════════════════════════════════════════════════

Rule A — ONE SUBNET PER BROADCAST DOMAIN / ACCESS SWITCH
  Every distinct access switch in the topology MUST be assigned its own
  unique VLAN and its own unique /24 subnet.  NEVER place two access
  switches or their end-devices in the same subnet.
  Example: Admin-SW → VLAN 10 → 10.0.10.0/24
           F1-SW    → VLAN 20 → 10.0.20.0/24
           F2-SW    → VLAN 30 → 10.0.30.0/24

Rule B — ROUTER-ON-A-STICK (802.1Q SUB-INTERFACES)
  When a single router connects to multiple access switches through a
  core switch, you MUST configure 802.1Q sub-interfaces on the router's
  physical interface.  Each sub-interface maps to exactly one VLAN:
    interface FastEthernet0/0.10
      encapsulation dot1Q 10
      ip address 10.0.10.1 255.255.255.0
  The sub-interface number SHOULD match the VLAN ID for clarity
  (e.g., Fa0/0.10 = VLAN 10, Fa0/0.20 = VLAN 20).

Rule C — VPCS GATEWAYS MUST MATCH THEIR VLAN'S SUB-INTERFACE
  Every VPCS host must use the IP of the router sub-interface for its
  VLAN as the default gateway.  Example:
    PC on VLAN 10 → gateway 10.0.10.1 (matches Fa0/0.10)
    PC on VLAN 20 → gateway 10.0.20.1 (matches Fa0/0.20)
  NEVER use the same gateway for hosts on different VLANs.

Rule D — SUBNET ALLOCATION SCHEME
  Use a structured allocation scheme derived from VLAN IDs:
    VLAN 10 → 10.0.10.0/24  (third octet = VLAN ID)
    VLAN 20 → 10.0.20.0/24
    VLAN 30 → 10.0.30.0/24
  Router sub-interface IPs are always .1 in each subnet.
  Host IPs start from .10 upward (.10, .11, .12, ...).

Rule E — SIMPLE NETWORK EXCEPTION
  If the brief states this is a "simple single-department network" or
  there is only ONE access switch, a flat subnet is acceptable and
  Router-on-a-Stick is NOT required.

══════════════════════════════════════════════════════════════

STRICT RULES:
1. ONLY use the config keys listed above. Any other key will be REJECTED.
2. Do NOT include "slot1", "adapters", "ports_mapping", "platform", "ram",
   or any hardware property — those are already injected and PROTECTED.
3. Do NOT include "name", "node_type", "template_name", "compute_id" —
   those are topology properties, not config properties.
4. Use the EXACT interface names from the brief (e.g., FastEthernet0/0, eth0).
5. Each segment gets one unique subnet. Multi-access segments use /24,
   point-to-point segments use /30.
5a. ALL devices on the same multi-access segment (switch + all connected
    hosts + router interface) MUST share the SAME subnet and SAME mask.
    A router interface on a /24 segment MUST be /24 — NEVER assign /30
    to a router interface that serves hosts through a switch.
6. Include routing protocols (OSPF or static routes) for multi-segment routers.
7. Do NOT include markdown code fences. Return ONLY raw JSON.
8. The JSON must start with '{{' and end with '}}'.
9. Skip switches, hubs, NAT, and cloud nodes — they need no IP config."""


# ═══════════════════════════════════════════════════════════════════════════════
#  JSON Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> str:
    """Extract JSON from potentially messy LLM output.

    Handles three cases:
      1. Clean JSON (starts with '{{', ends with '}}')
      2. JSON wrapped in markdown code fences
      3. JSON buried inside conversational text (regex rescue)
    """
    cleaned = re.sub(r'^```\w*\n?', '', text.strip()).rstrip('`').strip()

    if cleaned.startswith('{') and cleaned.endswith('}'):
        return cleaned

    # Last resort: find the outermost {{ ... }} block
    match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
    if match:
        return match.group(1)

    return text


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM Call
# ═══════════════════════════════════════════════════════════════════════════════

def generate_software_configs(brief: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Call the LLM to generate software configurations from the brief.

    Returns a flat map: {{node_id: {config_key: config_value}}} or None.
    """
    client = _get_client()
    prompt = _build_phase2_prompt(brief)
    logger.info("Calling Phase 2 LLM (model=%s) ...", DEFAULT_MODEL)

    # --- Strategy 1: JSON Mode (preferred for Phase 2) ---
    try:
        def _json_call():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Generate the software configurations now."},
                ],
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
            )

        response = _call_with_retry(_json_call)
        if response and response.choices:
            raw_text = response.choices[0].message.content or ""
            clean_text = _extract_json(raw_text)
            configs = json.loads(clean_text)

            # Validate it's a dict of dicts
            if not isinstance(configs, dict):
                logger.error("LLM returned non-dict top-level: %s", type(configs).__name__)
                return None

            for nid, cfg in configs.items():
                if not isinstance(cfg, dict):
                    logger.error("LLM returned non-dict for node '%s': %s",
                                 nid, type(cfg).__name__)
                    return None

            logger.info("Phase 2 LLM succeeded — configs for %d node(s)", len(configs))
            return configs

    except Exception as e:
        logger.warning("Phase 2 JSON mode failed: %s", e)

    # --- Strategy 2: Plain text fallback (no response_format) ---
    logger.info("Retrying Phase 2 without response_format...")
    raw_text = ""
    try:
        def _plain_call():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Generate the software configurations now. Return ONLY raw JSON."},
                ],
                max_tokens=MAX_TOKENS,
            )

        response = _call_with_retry(_plain_call)
        if response and response.choices:
            raw_text = response.choices[0].message.content or ""
            clean_text = _extract_json(raw_text)
            configs = json.loads(clean_text)

            if isinstance(configs, dict):
                logger.info("Phase 2 plain fallback succeeded — configs for %d node(s)",
                            len(configs))
                return configs

    except Exception as e:
        logger.error("Phase 2 plain fallback also failed: %s", e)
        logger.error("\n%s\nRAW AI OUTPUT:\n%s\n%s",
                     "=" * 40, raw_text, "=" * 40)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Three-Gate Safe Merge
# ═══════════════════════════════════════════════════════════════════════════════

def safe_merge_configs(
    phase1_dict: Dict[str, Any],
    llm_configs: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """Merge LLM-generated software configs into the Phase 1 JSON.

    Three-Gate Safety:
      Gate 1 — Whitelist:  key must be in SOFTWARE_CONFIG_KEYS
      Gate 2 — No-overwrite: key must NOT already exist in node.properties
      Gate 3 — Type check:  value type must match ALLOWED_VALUE_TYPES

    Returns:
      (merged_dict, rejection_log)
      - merged_dict: the Phase 1 dict with approved configs merged in
      - rejection_log: {node_id: [reason1, reason2, ...]} for any rejected keys
    """
    topology = phase1_dict.get("topology", phase1_dict)
    nodes = topology.get("nodes", [])

    # Index nodes by node_id for O(1) lookup
    node_index: Dict[str, dict] = {}
    for node in nodes:
        nid = node.get("node_id")
        if nid:
            node_index[nid] = node

    rejection_log: Dict[str, List[str]] = {}
    merged_count = 0

    for node_id, config in llm_configs.items():
        node = node_index.get(node_id)
        if node is None:
            rejection_log.setdefault(node_id, []).append(
                f"Node '{node_id}' not found in topology — entire config skipped"
            )
            continue

        properties = node.setdefault("properties", {})

        for key, value in config.items():
            # ── Gate 1: Whitelist ──
            if key not in SOFTWARE_CONFIG_KEYS:
                reason = (f"Key '{key}' rejected — not in whitelist "
                          f"({', '.join(sorted(SOFTWARE_CONFIG_KEYS))})")
                rejection_log.setdefault(node_id, []).append(reason)
                logger.warning("MERGE REJECT [Gate 1]: %s.%s — %s",
                               node_id, key, reason)
                continue

            # ── Gate 2: No-overwrite (with empty-placeholder exception) ──
            if key in properties:
                existing_val = properties[key]
                # Allow overwriting empty placeholder values ("", {}, [], None).
                # These are not meaningful hardware configs — they're defaults
                # from the LLM or template that Phase 2 is meant to replace.
                # Non-empty hardware values (slot1="PA-8E", adapters=4) remain
                # protected because they're never empty strings or empty dicts.
                if existing_val == "" or existing_val == {} or existing_val == [] or existing_val is None:
                    logger.info("MERGE ALLOW [Gate 2 relaxed]: %s.%s — "
                                "existing value is empty placeholder, "
                                "allowing Phase 2 overwrite",
                                node_id, key)
                    # Fall through to Gate 3 check below
                else:
                    reason = (f"Key '{key}' rejected — already exists in properties "
                              f"with non-empty value: {repr(existing_val)[:80]})")
                    rejection_log.setdefault(node_id, []).append(reason)
                    logger.warning("MERGE REJECT [Gate 2]: %s.%s — %s",
                                   node_id, key, reason)
                    continue

            # ── Gate 3: Type check ──
            allowed_types = ALLOWED_VALUE_TYPES.get(key, (str,))
            if not isinstance(value, allowed_types):
                reason = (f"Key '{key}' rejected — value type {type(value).__name__} "
                          f"not in {tuple(t.__name__ for t in allowed_types)}")
                rejection_log.setdefault(node_id, []).append(reason)
                logger.warning("MERGE REJECT [Gate 3]: %s.%s — %s",
                               node_id, key, reason)
                continue

            # ── All gates passed — safe to merge ──
            properties[key] = value
            merged_count += 1
            logger.debug("MERGE OK: %s.%s (%d chars)",
                         node_id, key, len(str(value)))

    logger.info("Safe merge complete: %d key(s) merged, %d node(s) with rejections",
                merged_count, len(rejection_log))

    return phase1_dict, rejection_log


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API — Full Phase 2 Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_phase2(
    phase1_json_path: str,
    output_path: str = "output/final_topology.json",
) -> Optional[Dict[str, Any]]:
    """Execute the complete Phase 2 pipeline.

    Steps:
      1. Build Configuration Brief from Phase 1 JSON
      2. Send brief to LLM → get software configs
      3. Three-Gate Safe Merge into Phase 1 JSON
      4. Re-validate through Pydantic schema
      5. Save final integrated JSON

    Parameters
    ----------
    phase1_json_path : str
        Path to the Phase 1 output JSON (hardware-injected topology)
    output_path : str
        Path to save the final integrated topology JSON

    Returns
    -------
    dict or None
        The final integrated topology dict, or None on failure
    """
    # ── Step 1: Load Phase 1 JSON ──
    p1_path = Path(phase1_json_path)
    if not p1_path.exists():
        logger.error("Phase 1 JSON not found: %s", phase1_json_path)
        return None

    with open(p1_path, "r", encoding="utf-8") as f:
        phase1_dict = json.load(f)

    logger.info("Loaded Phase 1 JSON: %s", phase1_json_path)

    # ── Step 2: Build Configuration Brief ──
    brief = build_configuration_brief(phase1_json_path)
    logger.info("Configuration brief: %d chars", len(brief))

    # ── Step 3: Generate Software Configs via LLM ──
    llm_configs = generate_software_configs(brief)
    if llm_configs is None:
        logger.error("LLM failed to generate software configs — aborting Phase 2")
        return None

    # ── Step 4: Three-Gate Safe Merge ──
    merged_dict, rejection_log = safe_merge_configs(phase1_dict, llm_configs)

    if rejection_log:
        logger.warning("Some LLM configs were rejected:")
        for nid, reasons in rejection_log.items():
            for reason in reasons:
                logger.warning("  %s: %s", nid, reason)

    # ── Step 5: Re-validate through Pydantic ──
    try:
        validated = GNS3Project.model_validate(merged_dict)
        logger.info("Pydantic re-validation passed")
    except Exception as e:
        logger.error("Pydantic re-validation FAILED after merge: %s", e)
        logger.error("Saving unvalidated JSON for manual inspection")
        # Still save so the user can debug — but return None to signal failure
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(merged_dict, indent=2), encoding="utf-8")
        return None

    # ── Step 6: Save final integrated JSON ──
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(validated.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Final topology saved to %s", output_path)

    return validated.model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")

    # Accept paths as CLI args, or use defaults
    phase1_path = sys.argv[1] if len(sys.argv) > 1 else "output/_topology.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output/final_topology.json"

    result = run_phase2(phase1_path, output_file)

    if result:
        print("\n=== Phase 2 Complete ===\n")
        print(json.dumps(result, indent=2))
    else:
        print("\nPhase 2 failed. Check logs for details.")
