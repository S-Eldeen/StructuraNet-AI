"""
Structranet AI — AI Agent

Translates a natural language request into a validated GNS3Project object.
Uses OpenRouter (OpenAI-compatible) API with structured output + JSON fallback.

Pipeline:
  1. LLM generates logical topology (nodes + links, properties left empty)
  2. Pydantic schema validates structure
  3. inject_hardware_config() expands ports/adapters/slots as needed
  4. Final JSON saved for the assembler

Phase 2 (future): A separate agent will populate software configs
(startup_config_content, startup_script, etc.) AFTER hardware ports
are finalised, avoiding circular dependencies.
"""

import os
import json
import re
import time
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, InternalServerError

from hw_config import inject_hardware_config
from schema import GNS3Project

load_dotenv()
logger = logging.getLogger("structranet.ai_agent")

ROUTER_BASE_URL = os.getenv("ROUTER_BASE_URL")
DEFAULT_MODEL = os.getenv("AI_MODEL", "openrouter/owl-alpha")
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "8192"))

# Lazy client singleton
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("ROUTER_API_KEY")
        base_url = os.getenv("ROUTER_BASE_URL")
        if not key:
            raise ValueError("API Key missing! Check your .env file.")

        _client = OpenAI(base_url=base_url, api_key=key, timeout=500.0)
    return _client


def _build_prompt(devices: list[dict]) -> str:
    """Build the system prompt with real inventory and port counts."""
    inventory = []
    port_lines = []
    for d in devices:
        inventory.append({"name": d["name"], "type": d["gns3_type"],
                          "category": d.get("category", ""), "port_count": d.get("port_count")})
        pc = d.get("port_count")
        gns3_type = d["gns3_type"]

        if gns3_type == "dynamips" and pc is not None:
            # Dynamips routers use a SLOT model, NOT flat ports.
            # adapter_number == slot_number. Each adapter provides a FIXED
            # number of ports. The AI MUST increment adapter_number for each
            # additional link — it CANNOT stack multiple ports on adapter 0.
            #
            # Concrete assignment table (LLM must follow this EXACTLY):
            #   Link #1 -> adapter=0, port=0   (built-in)
            #   Link #2 -> adapter=1, port=0   (slot 1 module)
            #   Link #3 -> adapter=2, port=0   (slot 2 module)
            #   Link #4 -> adapter=3, port=0   (slot 3 module)
            #   ...and so on. ALWAYS port=0 on each new adapter.
            port_lines.append(
                f"  - {d['name']} (dynamips): EACH ADAPTER HAS 1 PORT "
                f"(port_number=0 ONLY). For N links, use adapters "
                f"0,1,2,...N-1 each with port=0. "
                f"NEVER use port>0 on ANY adapter. "
                f"Link 1: adapter=0,port=0 | Link 2: adapter=1,port=0 | "
                f"Link 3: adapter=2,port=0 | Link 4: adapter=3,port=0"
            )
        elif gns3_type == "iou" and pc is not None:
            # IOU also uses slots but each slot has 4 ports
            port_lines.append(
                f"  - {d['name']} (iou): adapter 0 has 4 ports (0-3). "
                f"For additional ports, use adapter 1 ports 0-3, then adapter 2, etc."
            )
        elif gns3_type == "ethernet_switch" and pc is not None:
            port_lines.append(
                f"  - {d['name']} (ethernet_switch): adapter_number MUST be 0 "
                f"ALWAYS. Expand ports via port_number only: port=0,1,2,3... "
                f"NEVER set adapter>0 on a switch. "
                f"Example: Link 1: adapter=0,port=0 | Link 2: adapter=0,port=1 | "
                f"Link 3: adapter=0,port=2"
            )
        elif gns3_type in ("qemu", "docker", "virtualbox", "vmware") and pc is not None:
            # QEMU/Docker/VBox/VMware: each adapter has exactly 1 port (port_number=0).
            # Use adapter 0, then adapter 1, etc. NOT adapter=0 with multiple ports.
            port_lines.append(
                f"  - {d['name']} ({gns3_type}): each adapter has 1 port "
                f"(port_number=0). Use adapter 0, then adapter 1, etc. "
                f"Up to {pc} adapter(s) available."
            )
        elif gns3_type in ("vpcs", "traceng", "nat") and pc is not None:
            # VPCS/TraceNG/NAT: hard-locked to exactly 1 port — no expansion.
            port_lines.append(
                f"  - {d['name']} ({gns3_type}): exactly 1 port — "
                f"use adapter=0, port=0 ONLY. Max 1 link."
            )
        elif gns3_type == "ethernet_hub" and pc is not None:
            port_lines.append(
                f"  - {d['name']} (ethernet_hub): adapter_number MUST be 0 "
                f"ALWAYS. Expand ports via port_number only: port=0,1,2,3... "
                f"NEVER set adapter>0 on a hub. "
                f"Example: Link 1: adapter=0,port=0 | Link 2: adapter=0,port=1"
            )
        elif pc is not None:
            # Generic fallback for any unhandled type
            port_lines.append(
                f"  - {d['name']} ({gns3_type}): {pc} port(s), "
                f"use adapter=0, ports 0..{pc-1}"
            )
            
    inv_json = json.dumps(inventory, indent=2)
    port_text = "\n".join(port_lines) if port_lines else "  (port counts unavailable — use conservative values)"

    return f"""You are the Core Architect Agent for Structranet AI.
Translate the user's natural language request into a GNS3 network topology JSON.

AVAILABLE HARDWARE (you MUST only use these):
{inv_json}

PORT LIMITS (do NOT exceed these per device):
{port_text}

RULES:
1. ZERO HALLUCINATION: Only use devices from the inventory above.
2. node_type must be a GNS3 type literal: dynamips, qemu, vpcs, ethernet_switch, ethernet_hub, docker, iou, cloud, traceng, frame_relay_switch, atm_switch, virtualbox, vmware, nat. NOT hardware names.
3. template_name must be the exact inventory name (e.g., 'c7200', 'Switch').
4. name must be a human-readable label (e.g., 'R1-Edge', 'Core-SW1', 'PC1').
5. Every link needs two distinct endpoints with adapter_number and port_number.
6. Don't reuse the same (adapter, port) pair on one node across different links.
7. If a requested device isn't available, substitute with the closest match.
8. CRITICAL: You MUST output a <thought_process> block FIRST, then the JSON.
9. CRITICAL: Do NOT wrap the JSON in markdown code blocks (no ```json).
10. CRITICAL: Do NOT include any conversational text outside the <thought_process> block and the JSON.
11. CRITICAL: The JSON must start exactly with '{{' and end exactly with '}}'.
12. Do NOT create more than one link between the same pair of nodes. Each pair of nodes must have at most one direct link between them.
13. DYNAMIPS ADAPTER RULE (CRITICAL — MOST COMMON ERROR):
    Dynamips routers use a SLOT model where adapter_number == slot_number.
    Each adapter provides EXACTLY 1 Ethernet port (port_number=0).
    
    FOR EVERY DYNAMIPS LINK: port_number MUST be 0. ALWAYS.
    To add more links, INCREMENT the adapter_number, NOT the port_number.
    
    MANDATORY ASSIGNMENT PATTERN for N links on a dynamips router:
      Link 1: adapter=0, port=0
      Link 2: adapter=1, port=0
      Link 3: adapter=2, port=0
      Link N: adapter=N-1, port=0
    
    ❌ ABSOLUTELY FORBIDDEN on dynamips:
      adapter=0, port=1  ← port>0 is NEVER valid on dynamips
      adapter=0, port=2  ← WRONG! Each adapter has exactly 1 port
      adapter=0, port=3  ← WRONG! Increment adapter instead
    
    NEVER skip adapter numbers. Use 0,1,2,3 sequentially.
    
14. SWITCH PORT RULE (CRITICAL — SECOND MOST COMMON ERROR):
    Switches and hubs ALWAYS use adapter_number=0. NO EXCEPTIONS.
    Expand ports by increasing port_number (0, 1, 2, 3...), NOT adapter_number.
    
    FOR EVERY SWITCH/HUB LINK: adapter_number MUST be 0. ALWAYS.
    
    MANDATORY ASSIGNMENT PATTERN for N links on a switch:
      Link 1: adapter=0, port=0
      Link 2: adapter=0, port=1
      Link 3: adapter=0, port=2
      Link N: adapter=0, port=N-1
    
    ❌ ABSOLUTELY FORBIDDEN on switches/hubs:
      adapter=1, port=0  ← adapter>0 is NEVER valid on switches
      adapter=2, port=0  ← WRONG! Switches have no slot expansion
15. CONNECTIVITY RULE: Every node MUST be reachable from every other node.
    Do NOT create isolated pairs of nodes (e.g., two VPCS linked only to
    each other with no switch or router uplink). All nodes must connect
    to the network through switches or routers.
16. NETWORK SEGMENTATION (LAYER 3 BOUNDARIES):
    - If the user asks for separate groups, floors, or departments,
      each group MUST be on a separate subnet — NO exceptions.
    - HIERARCHICAL DESIGN (DEFAULT for multi-subnet): When the router needs
      more than 3 links, use the Core-SW + Router-on-a-Stick pattern (Rule 18).
      This is the preferred approach for any topology with 2+ subnet switches.
    - DIRECT LINKS (only for ≤3 subnets): When the router can handle all
      subnet switches within its 3-link limit, you MAY connect each group's
      switch DIRECTLY to the router with a dedicated link. This guarantees
      physical segmentation with no VLAN config.
    - INVARIANT: A router with only ONE interface on ONE flat subnet
      serving multiple groups is architecturally wrong — there is no
      L3 boundary, and the router serves no purpose.

SINGLE-LINK DEVICES (HARD LIMIT — never exceed 1 link on these):
  - vpcs: exactly 1 Ethernet port, max 1 link
  - traceng: exactly 1 Ethernet port, max 1 link
  - nat: exactly 1 Ethernet port, max 1 link
If a VPCS/TraceNG/NAT node needs multiple connections, you MUST insert a
switch between it and the rest of the network. Do NOT attach >1 link directly.

17. HARDWARE AWARENESS — GNS3 PCI BUS CONSTRAINT (CRITICAL):
    Dynamips routers in GNS3 emulate a PCI bus. If you force too many Port
    Adapters (PA-8E on c7200) or too many active physical links, the emulated
    PCI bus bandwidth is EXCEEDED and the router CRASHES — all ports shut down.

    PRACTICAL SAFE LIMITS (derived from GNS3/Dynamips testing):
      c7200:  max 3 links   ← Most restrictive! 1 builtin + 1 PA-8E only
      c3745:  max 6 links   c3725:  max 6 links   c2691:  max 6 links
      c3660:  max 5 links   c3640:  max 4 links   c3620:  max 4 links
      c2600:  max 2 links   c1700:  max 2 links
    IOU: max 8 links      QEMU: max 8 links     Docker: max 8 links
    Ethernet switch/hub: max 128 ports

    ⚠️ The c7200 can ONLY handle 3 links safely! If your topology needs the
    router to connect to more than 3 subnets, you MUST use the hierarchical
    design pattern described in Rule 18 below.

18. HIERARCHICAL DESIGN PATTERN (MANDATORY for multi-subnet topologies):
    When the user requests a network with multiple subnets/groups/floors and
    the total number of subnet switches exceeds the router's practical link
    limit (3 for c7200), you MUST use this architecture:

    ┌─────────────────────────────────────────────────────────┐
    │  HIERARCHICAL PATTERN: Core Switch + Router-on-a-Stick  │
    │                                                         │
    │  Router (R1)                                            │
    │    │                                                    │
    │    └─── 1 physical link (802.1Q trunk) ─── Core-SW      │
    │              │          │          │                     │
    │           F1-SW     F2-SW     Admin-SW                  │
    │           │││       │││       │││                        │
    │          hosts     hosts     hosts                      │
    └─────────────────────────────────────────────────────────┘

    HOW IT WORKS:
    a) Create ONE "Core-SW" (ethernet_switch) as the distribution layer
    b) Connect the Router to Core-SW with a SINGLE physical link
    c) Connect ALL subnet switches (F1-SW, F2-SW, Admin-SW) to Core-SW
    d) Each subnet switch connects its end-devices (VPCS, etc.)
    e) Layer 3 segmentation is achieved via 802.1Q VLANs on the
       Router-Core-SW trunk link (one subinterface per VLAN)

    ADVANTAGES:
    - Router only needs 1 physical link regardless of subnet count
    - No PCI bus crash risk
    - All subnets remain L3-separated via VLANs
    - Scales to dozens of subnets without changing the router config

    WHEN TO USE THIS PATTERN:
    - If the router needs >3 links -> USE THIS PATTERN (mandatory)
    - If the router needs <=3 links -> direct links are fine
    - If unsure -> use this pattern anyway (it's always safe)

    VLAN ASSIGNMENT RULE for this pattern:
    - Assign VLAN IDs starting from 10, incrementing by 10:
      VLAN 10 = first subnet, VLAN 20 = second subnet, etc.
    - The Router-Core-SW link is an 802.1Q trunk carrying all VLANs
    - Each subnet switch's uplink to Core-SW is an access port in that
      subnet's VLAN
    - The router uses one subinterface per VLAN (e.g., Fa0/0.10, Fa0/0.20)

NAMING-TO-SWITCH ASSIGNMENT RULE:
  - If a node name starts with a prefix followed by a dash (e.g., 'F1-Class1',
    'F2-Teacher3', 'Admin-PC2'), the prefix identifies the switch it MUST
    connect to. Examples:
      * 'F1-Class1' -> MUST connect to the switch named 'F1-SW'
      * 'F2-Teacher3' -> MUST connect to the switch named 'F2-SW'
      * 'Admin-PC2' -> MUST connect to the switch named 'Admin-SW'
  - This means you must plan switch assignments FIRST: decide which switch
    each group of end-devices connects to, then name those devices with the
    matching prefix.
  - NEVER connect a device to a switch with a different prefix. For example,
    'F2-Class4' MUST go to 'F2-SW', NOT to 'F3-SW'.
  - If a switch does not exist for a prefix, you MUST create it. For example,
    if you name devices 'HR-PC1' and 'HR-PC2', you MUST also create an 'HR-SW'
    switch and connect them to it.

PROPERTIES RULE (PHASE 1):
  - Every node MUST include "properties": {{}} (an empty object).
  - Do NOT put IP addresses, subnets, routing commands, startup configs,
    or any software configuration inside properties.
  - Hardware port expansion (slots, adapters, ports_mapping) is injected
    automatically AFTER you generate the topology.
  - Software configuration (startup_config_content, startup_script, etc.)
    will be handled in Phase 2 by a separate agent.

WORKED EXAMPLE — Correct link assignments for R1 (dynamips) connected to 4 switches:
  R1 <-> SW-Admin: R1 side adapter=0, port=0 | SW-Admin side adapter=0, port=0
  R1 <-> SW-F1:    R1 side adapter=1, port=0 | SW-F1 side    adapter=0, port=0
  R1 <-> SW-F2:    R1 side adapter=2, port=0 | SW-F2 side    adapter=0, port=0
  R1 <-> SW-F3:    R1 side adapter=3, port=0 | SW-F3 side    adapter=0, port=0
  ⚠️ BUT WAIT — c7200 with 4 links (3 PA-8E cards) will CRASH due to PCI bus!
  ✅ CORRECT APPROACH: Use Core-SW + Router-on-a-Stick (Rule 18) instead:
    R1 <-> Core-SW: R1 adapter=0,port=0 | Core-SW adapter=0,port=0 (trunk)
    Core-SW <-> F1-SW: Core-SW adapter=0,port=1 | F1-SW adapter=0,port=0
    Core-SW <-> F2-SW: Core-SW adapter=0,port=2 | F2-SW adapter=0,port=0
    Core-SW <-> Admin-SW: Core-SW adapter=0,port=3 | Admin-SW adapter=0,port=0
    ...each subnet switch connects its hosts
  This uses only 1 router link — no PCI bus crash!

OUTPUT FORMAT (MANDATORY):
  You MUST output your response in TWO parts:

  PART 1: <thought_process>
    Before generating the JSON, reason step-by-step inside this block:
    1. How many total subnets/switches are needed for this request?
    2. Will connecting all these switches directly to the Router violate
       the Router's PCI bus hardware constraint (max 3 links for c7200)?
    3. If yes, deduce the correct hierarchical design (Core-SW + router-on-a-stick)
       that connects all subnets using only 1 physical router link.
    4. List the exact nodes and links you will create.
  </thought_process>

  PART 2: The JSON topology object (as specified by the schema).

  Example output structure:
    <thought_process>
    1. Subnets needed: F1 (4 classrooms + teachers), F2 (4 classrooms + teachers),
       Admin (10 PCs). Total: 3 subnet switches.
    2. Router (c7200) can only handle 3 links safely. With 3 subnet switches
       plus possible other connections, this is at the boundary.
    3. Decision: Use hierarchical design with Core-SW. Router connects to Core-SW
       via 1 trunk link. All 3 subnet switches connect to Core-SW.
    4. Nodes: R1, Core-SW, F1-SW, F2-SW, Admin-SW, + VPCS hosts
       Links: R1<->Core-SW, Core-SW<->F1-SW, Core-SW<->F2-SW, Core-SW<->Admin-SW,
              F1-SW<->hosts, F2-SW<->hosts, Admin-SW<->hosts
    </thought_process>
    {{"name": "...", "topology": {{...}}}}"""

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


def _extract_json(text: str) -> str:
    """Extract JSON from potentially messy LLM output.

    Handles four cases:
      1. Clean JSON (starts with '{', ends with '}')
      2. <thought_process> block before the JSON (strip it)
      3. JSON wrapped in markdown code fences (```json ... ```)
      4. JSON buried inside conversational text (regex extraction)
    """
    # Strip <thought_process>...</thought_process> blocks
    cleaned = re.sub(r'<thought_process>.*?</thought_process>', '', text.strip(), flags=re.DOTALL)

    # Strip markdown code fences
    cleaned = re.sub(r'^```\w*\n?', '', cleaned.strip()).rstrip('`').strip()

    # If it already looks like clean JSON, return as-is
    if cleaned.startswith('{') and cleaned.endswith('}'):
        return cleaned

    # Last resort: find the outermost { ... } block
    match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
    if match:
        return match.group(1)

    # Nothing found — return original and let json.loads fail with a clear error
    return text


def generate_network_topology(user_request: str, devices: list[dict]) -> Optional[GNS3Project]:
    """
    Generate a GNS3Project from a natural language request.
    Tries structured output first, falls back to JSON mode.
    """
    client = _get_client()
    prompt = _build_prompt(devices)
    logger.info("Calling AI model=%s ...", DEFAULT_MODEL)

    # --- Strategy 1: Structured Output ---
    try:
        def _structured():
            return client.beta.chat.completions.parse(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_request},
                ],
                response_format=GNS3Project,
                max_tokens=MAX_TOKENS,
            )

        response = _call_with_retry(_structured)
        if response and response.choices[0].message.parsed is not None:
            raw = response.choices[0].message.parsed
            # Re-validate: Pydantic model_validators don't run server-side
            result = GNS3Project.model_validate(raw.model_dump())
            logger.info("Structured output succeeded.")
            return result
    except Exception as e:
        logger.warning("Structured output failed: %s", e)

    # --- Strategy 2: JSON Mode Fallback ---
    logger.info("Falling back to JSON mode...")
    raw_text = ""
    try:
        schema_json = json.dumps(GNS3Project.model_json_schema(), indent=2)
        full_prompt = prompt + (
            f"\n\nJSON Schema:\n{schema_json}\n\n"
            "Respond with ONLY the JSON object. No markdown code fences."
        )

        def _json_mode():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": user_request},
                ],
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
            )

        response = _call_with_retry(_json_mode)
        if response:
            if getattr(response, "choices", None) is None or len(response.choices) == 0:
                logger.error("OpenRouter returned empty choices! Full response: %s", response)
                return None

            raw_text = response.choices[0].message.content or ""
            clean_text = _extract_json(raw_text)

            result = GNS3Project.model_validate(json.loads(clean_text))
            logger.info("JSON fallback succeeded.")
            return result

    except Exception as e:
        logger.error("JSON fallback also failed: %s", e)
        logger.error("\n%s\nRAW AI OUTPUT THAT CAUSED THE ERROR:\n%s\n%s",
                     "=" * 40, raw_text, "=" * 40)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Post-generation pipeline: hardware injection + save
# ═══════════════════════════════════════════════════════════════════════════════

def process_and_save_topology(raw_topology: GNS3Project, output_file: str) -> Optional[GNS3Project]:
    """Run hardware injection on a validated topology and save to disk.

    Steps:
      1. Convert Pydantic model -> dict
      2. Call inject_hardware_config() to expand ports/adapters/slots
      3. Re-validate through Pydantic (catches any corruption from injection)
      4. Save the final JSON to output_file
      5. Return the enriched GNS3Project

    Returns None if re-validation fails.
    """
    # Step 1–2: Inject hardware configuration
    raw_dict = raw_topology.model_dump()
    enriched_dict = inject_hardware_config(raw_dict)

    # Step 3: Re-validate to ensure injection didn't corrupt the structure
    try:
        result = GNS3Project.model_validate(enriched_dict)
    except Exception as e:
        logger.error("Re-validation failed after hardware injection: %s", e)
        return None

    # Step 4: Save to disk
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Topology saved to %s", output_path)
    except OSError as e:
        logger.error("Failed to save topology file: %s", e)
        return None

    # Step 5: Return enriched model
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")

    mock_devices = [
        {"name": "c7200", "gns3_type": "dynamips", "template_id": "x",
         "builtin": False, "category": "router", "port_count": 4},
        {"name": "Ethernet switch", "gns3_type": "ethernet_switch", "template_id": "y",
         "builtin": True, "category": "switch", "port_count": 128},
        {"name": "VPCS", "gns3_type": "vpcs", "template_id": "z",
         "builtin": True, "category": "guest", "port_count": 1},
    ]

    test_request = (
        "Create a simple network named 'test1'. I have a three-story school building. "
        "The principal needs access to everything. The administration has ~10 computers. "
        "Each floor has 4 classrooms and a teachers' room with 3 computers, all networked."
    )

    result = generate_network_topology(test_request, mock_devices)

    if result:
        print("\n=== AI Generation Succeeded ===\n")
        final = process_and_save_topology(result, "output/_topology.json")
        if final:
            print(final.model_dump_json(indent=2))
        else:
            print("Hardware injection or save failed.")
    else:
        print("\nFailed to generate topology.")
