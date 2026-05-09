"""
Structuranet AI — AI Agent

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
            # adapter 0 = built-in (1-2 Ethernet ports only), adapter 1+ = slot modules.
            # The AI MUST fill adapter 1 ports first before using adapter 2.
            port_lines.append(
                f"  - {d['name']} (dynamips): adapter 0 has 1 built-in Ethernet port "
                f"(port 0 ONLY). For additional Ethernet ports, use adapter 1 with "
                f"ports 0,1,2... Fill adapter 1 completely before using adapter 2."
            )
            port_lines.append(
                f"  - {d['name']} (dynamips): For SERIAL/WAN links, use a SEPARATE "
                f"adapter (e.g., adapter 2) and set link_type='serial'. "
                f"Serial ports are named Serial1/0, Serial2/0, etc. "
                f"Each serial module provides 4 serial ports (0-3)."
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
    
    ABSOLUTELY FORBIDDEN on dynamips:
      adapter=0, port=1  <- port>0 is NEVER valid on dynamips
      adapter=0, port=2  <- WRONG! Each adapter has exactly 1 port
      adapter=0, port=3  <- WRONG! Increment adapter instead
    
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
    
    ABSOLUTELY FORBIDDEN on switches/hubs:
      adapter=1, port=0  <- adapter>0 is NEVER valid on switches
      adapter=2, port=0  <- WRONG! Switches have no slot expansion
15. CONNECTIVITY RULE: Every node MUST be reachable from every other node.
    Do NOT create isolated pairs of nodes (e.g., two VPCS linked only to
    each other with no switch or router uplink). All nodes must connect
    to the network through switches or routers.
16. SERIAL/WAN LINK RULE: For WAN connections between routers, use
    link_type='serial' instead of 'ethernet'. Serial links MUST use
    adapter_number >= 1 (no built-in serial ports exist on any platform).
    Use a separate adapter from Ethernet links — do NOT mix serial and
    Ethernet links on the same adapter.
    Example: R1 adapter 1 = Ethernet (LAN), R1 adapter 2 = Serial (WAN)
17. NETWORK SEGMENTATION (LAYER 3 BOUNDARIES):
    - If the user asks for separate groups, floors, or departments,
      each group MUST be on a separate subnet — NO exceptions.
    - HIERARCHICAL DESIGN (DEFAULT for multi-subnet): When the router needs
      more than 3 links, use the Core-SW + Router-on-a-Stick pattern (Rule 19).
      This is the preferred approach for any topology with 2+ subnet switches.
    - DIRECT LINKS (only for <=3 subnets): When the router can handle all
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

18. HARDWARE AWARENESS — GNS3 PCI BUS CONSTRAINT (CRITICAL):
    Dynamips routers in GNS3 emulate a PCI bus. If you force too many Port
    Adapters (PA-8E on c7200) or too many active physical links, the emulated
    PCI bus bandwidth is EXCEEDED and the router CRASHES — all ports shut down.

    PRACTICAL SAFE LIMITS (derived from GNS3/Dynamips testing):
      c7200:  max 3 links   <- Most restrictive! 1 builtin + 1 PA-8E only
      c3745:  max 6 links   c3725:  max 6 links   c2691:  max 6 links
      c3660:  max 5 links   c3640:  max 4 links   c3620:  max 4 links
      c2600:  max 2 links   c1700:  max 2 links
    IOU: max 8 links      QEMU: max 8 links     Docker: max 8 links
    Ethernet switch/hub: max 128 ports

    WARNING: The c7200 can ONLY handle 3 links safely! If your topology needs the
    router to connect to more than 3 subnets, you MUST use the hierarchical
    design pattern described in Rule 19 below.

19. HIERARCHICAL DESIGN PATTERN (MANDATORY for multi-subnet topologies):
    When the user requests a network with multiple subnets/groups/floors and
    the total number of subnet switches exceeds the router's practical link
    limit (3 for c7200), you MUST use this architecture:

    +-------------------------------------------------------------+
    |  HIERARCHICAL PATTERN: Core Switch + Router-on-a-Stick      |
    |                                                             |
    |  Router (R1)                                                |
    |    |                                                        |
    |    +--- 1 physical link (802.1Q trunk) --- Core-SW          |
    |              |          |          |                         |
    |           F1-SW     F2-SW     Admin-SW                      |
    |           |||       |||       |||                            |
    |          hosts     hosts     hosts                          |
    +-------------------------------------------------------------+

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
  WARNING: BUT WAIT — c7200 with 4 links (3 PA-8E cards) will CRASH due to PCI bus!
  CORRECT APPROACH: Use Core-SW + Router-on-a-Stick (Rule 19) instead:
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


# ==============================================================================
#  Post-generation pipeline: hardware injection + save
# ==============================================================================

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
    # Step 1-2: Inject hardware configuration
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


# ==============================================================================
#  V3.0 — Autonomous Agent Extensions
# ==============================================================================

MAX_REACT_RETRIES = 3  # Maximum self-correction retries on ValidationError


# -- Intent Classification ---------------------------------------------------

_EDIT_KEYWORDS = frozenset([
    "change", "modify", "add a", "remove", "delete", "replace", "update",
    "rename", "move", "swap", "connect", "disconnect", "edit", "replace",
    "add router", "add switch", "add pc", "add host", "remove router",
    "remove switch", "remove pc", "change ip", "add link", "remove link",
    # "configure" belongs here too: "configure R1 with NAT" / "configure
    # the router with OSPF" are edit instructions on an existing node.
    # Having it only in _GENERATE_KEYWORDS caused gen_score=1, edit_score=0
    # whenever the user typed "configure X" with a topology loaded, routing
    # the request to GENERATE and silently discarding the existing topology.
    "configure",
])

_GENERATE_KEYWORDS = frozenset([
    "create", "build", "design", "generate", "make", "set up",
    "deploy", "draw", "construct", "implement", "i need a network",
    "i want a network", "new network", "new topology",
])

_CHAT_KEYWORDS = frozenset([
    "what", "how", "why", "explain", "can you", "help", "tell me",
    "what is", "what are", "how does", "how do", "difference between",
])


def classify_intent(user_message: str, chat_history: list = None,
                    has_existing_topology: bool = False) -> str:
    """Classify user intent as GENERATE, EDIT, or CHAT.
    
    Uses keyword-based heuristics first (fast, free), falls back to LLM
    if ambiguous.
    
    Args:
        user_message: The user's message text.
        chat_history: Optional list of {"role": ..., "content": ...} dicts.
        has_existing_topology: Whether a topology already exists in the session.
    
    Returns:
        One of: "GENERATE", "EDIT", "CHAT"
    """
    msg_lower = user_message.lower().strip()
    
    # Score each intent category
    edit_score = sum(1 for kw in _EDIT_KEYWORDS if kw in msg_lower)
    gen_score = sum(1 for kw in _GENERATE_KEYWORDS if kw in msg_lower)
    chat_score = sum(1 for kw in _CHAT_KEYWORDS if kw in msg_lower)
    
    # Decision logic with context awareness
    if has_existing_topology and edit_score > 0 and edit_score >= gen_score:
        return "EDIT"
    
    if gen_score > 0 and gen_score >= edit_score and gen_score >= chat_score:
        return "GENERATE"
    
    if chat_score > 0 and chat_score > gen_score and chat_score > edit_score:
        return "CHAT"
    
    # If there's an existing topology and the message is short/ambiguous,
    # lean toward EDIT (user is likely modifying)
    if has_existing_topology and edit_score > 0:
        return "EDIT"
    
    # If no topology exists and message is substantive, assume GENERATE
    if not has_existing_topology and len(msg_lower.split()) >= 3:
        return "GENERATE"
    
    # Ambiguous — use LLM classification
    try:
        return _llm_classify_intent(user_message, chat_history, has_existing_topology)
    except Exception as e:
        logger.warning("LLM intent classification failed: %s — defaulting to CHAT", e)
        return "CHAT"


def _llm_classify_intent(user_message: str, chat_history: list = None,
                         has_existing_topology: bool = False) -> str:
    """Use the LLM to classify intent when heuristics are ambiguous."""
    client = _get_client()
    
    topo_status = ("An existing topology IS present in this session."
                   if has_existing_topology
                   else "No topology exists yet in this session.")
    
    system_prompt = f"""You are an intent classifier for Structranet AI, a network topology generator.
Classify the user's message into exactly ONE of these categories:

- GENERATE: The user wants to create a NEW network topology from scratch.
- EDIT: The user wants to MODIFY an existing topology (add/remove/change devices or links).
- CHAT: The user is asking a question, needs help, or making conversation (not a topology action).

{topo_status}

Respond with ONLY one word: GENERATE, EDIT, or CHAT. No explanation."""

    messages = [{"role": "system", "content": system_prompt}]
    
    # Add recent chat history for context (last 4 messages)
    if chat_history:
        for msg in chat_history[-4:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    
    messages.append({"role": "user", "content": user_message})
    
    def _classify_call():
        return client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            max_tokens=10,
            temperature=0.0,
        )
    
    response = _call_with_retry(_classify_call)
    if response and response.choices:
        raw = response.choices[0].message.content.strip().upper()
        if raw in ("GENERATE", "EDIT", "CHAT"):
            logger.info("LLM classified intent as: %s", raw)
            return raw
    
    return "CHAT"


# -- Function Calling / Tool Selection ---------------------------------------

def decide_tool(intent: str, user_message: str, chat_history: list = None,
                has_existing_topology: bool = False) -> dict:
    """Map classified intent to a tool call specification.
    
    Returns:
        dict with "tool" and "args" keys:
        - {"tool": "generate_network_topology", "args": {"user_request": ...}}
        - {"tool": "generate_edited_topology", "args": {"instruction": ..., "current_topology": ...}}
        - {"tool": "reply_text", "args": {"message": ...}}
    """
    if intent == "GENERATE":
        return {
            "tool": "generate_network_topology",
            "args": {"user_request": user_message}
        }
    elif intent == "EDIT":
        return {
            "tool": "generate_edited_topology",
            "args": {
                "instruction": user_message,
                "current_topology": None,  # Filled by orchestrator from session state
            }
        }
    else:  # CHAT
        return {
            "tool": "reply_text",
            "args": {"message": user_message}
        }


# -- Edit Mode: Topology Patcher --------------------------------------------

def _build_edit_prompt(current_topology_json: str, instruction: str, devices: list[dict]) -> str:
    """Build the system prompt for edit/patch mode."""
    inventory = []
    for d in devices:
        inventory.append({"name": d["name"], "type": d["gns3_type"],
                          "category": d.get("category", ""), "port_count": d.get("port_count")})
    inv_json = json.dumps(inventory, indent=2)
    
    return f"""You are the Topology Patcher Agent for Structranet AI.
Your job is to modify an EXISTING network topology based on the user's edit instruction.

AVAILABLE HARDWARE (you MUST only use these):
{inv_json}

CURRENT TOPOLOGY:
{current_topology_json}

USER EDIT INSTRUCTION: {instruction}

RULES:
1. PRESERVE ALL existing node_id values for unchanged nodes. Do NOT rename or renumber them.
2. Only modify nodes/links that the user explicitly mentions in their instruction.
3. For NEW nodes, assign a new unique node_id by incrementing from the maximum existing
   numeric suffix (e.g., if R3 exists, the next router is R4; if PC5 exists, next is PC6).
4. Output the COMPLETE patched topology JSON — not just the changes.
5. The output must follow the exact same schema as the input.
6. Do NOT wrap the JSON in markdown code fences.
7. Do NOT include any conversational text outside the JSON.
8. The JSON must start exactly with '{{' and end exactly with '}}'.
9. Every new link must have valid (adapter_number, port_number) assignments following
   the same rules as the original topology (dynamips: port=0 always, increment adapter;
   switches: adapter=0 always, increment port).
10. Do NOT create duplicate links between the same pair of nodes.
11. Ensure the patched topology remains fully connected (all nodes reachable).
12. Properties for new nodes must be empty: "properties": {{}}

Respond with ONLY the complete patched JSON topology object."""


def generate_edited_topology(instruction: str, current_topology: dict,
                              devices: list) -> Optional[GNS3Project]:
    """Generate a patched topology by editing an existing one.
    
    Sends the current topology JSON + edit instruction to the LLM.
    The LLM acts as a JSON patcher — modifying only requested nodes/links
    while preserving all unmodified node_id values.
    
    Args:
        instruction: The user's edit instruction (natural language).
        current_topology: The current topology dict (from _topology.json or session).
        devices: The GNS3 hardware inventory list.
    
    Returns:
        A validated GNS3Project with the patched topology, or None on failure.
    """
    client = _get_client()
    current_json = json.dumps(current_topology, indent=2)
    prompt = _build_edit_prompt(current_json, instruction, devices)
    logger.info("Calling AI for topology edit (model=%s) ...", DEFAULT_MODEL)
    
    # --- Strategy 1: JSON Mode (preferred for edits) ---
    try:
        schema_json = json.dumps(GNS3Project.model_json_schema(), indent=2)
        full_prompt = prompt + f"\n\nJSON Schema:\n{schema_json}"
        
        def _json_edit():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": instruction},
                ],
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
            )
        
        response = _call_with_retry(_json_edit)
        if response and response.choices:
            raw_text = response.choices[0].message.content or ""
            clean_text = _extract_json(raw_text)
            patched = json.loads(clean_text)
            result = GNS3Project.model_validate(patched)
            logger.info("Edit mode JSON succeeded — patched topology validated.")
            return result
    except Exception as e:
        logger.warning("Edit mode JSON failed: %s", e)
    
    # --- Strategy 2: Plain text fallback ---
    logger.info("Retrying edit mode without response_format...")
    raw_text = ""
    try:
        def _plain_edit():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": instruction},
                ],
                max_tokens=MAX_TOKENS,
            )
        
        response = _call_with_retry(_plain_edit)
        if response and response.choices:
            raw_text = response.choices[0].message.content or ""
            clean_text = _extract_json(raw_text)
            patched = json.loads(clean_text)
            result = GNS3Project.model_validate(patched)
            logger.info("Edit mode plain fallback succeeded.")
            return result
    except Exception as e:
        logger.error("Edit mode plain fallback also failed: %s", e)
        logger.error("\n%s\nRAW AI OUTPUT:\n%s\n%s",
                     "=" * 40, raw_text, "=" * 40)
    
    return None


# ==============================================================================
#  V3.0 FIX — Node ID Pre-Validation Guard (Edit Mode Integrity)
# ==============================================================================

def safe_merge_edited_topology(
    original_topology: dict,
    patched_topology: dict,
) -> tuple[dict, list[str]]:
    """Pre-validation guard for edited topologies.

    Verifies node_id integrity between original and patched topologies.
    Runs BEFORE schema.py validation to catch LLM patcher mistakes that
    Pydantic alone cannot detect (e.g., silently renamed node_ids,
    orphaned links, or attribute corruption on surviving nodes).

    Checks performed:
      1. DELETED NODE DETECTION: Identifies node_ids present in the original
         but absent from the patched topology.  These are logged as warnings
         since the user may have intentionally requested deletion, but if
         the count is unexpectedly high the LLM may have dropped nodes.
      2. DANGLING LINK REMOVAL: Any link in the patched topology that
         references a node_id not present in the patched nodes list is
         automatically removed.  The LLM sometimes forgets to remove links
         when it deletes a node, producing a topology that would fail
         schema validation anyway — this pre-empts that failure.
      3. DUPLICATE NODE_ID DETECTION: Ensures no two nodes share the same
         node_id.  This should be caught by Pydantic as well, but detecting
         it here produces a clearer diagnostic message.
      4. SURVIVING NODE ATTRIBUTE DRIFT: For nodes present in both the
         original and patched topologies (same node_id), verifies that
         core attributes (node_type, template_name) were not silently
         changed by the LLM.  node_type changes are auto-reverted because
         the same node_id should never change its device type.  template_name
         changes are also auto-reverted to prevent hardware mismatches.
      5. NEW NODE VALIDATION: Verifies that newly added node_ids do not
         collide with any existing node_id from the original topology
         (beyond what Pydantic's uniqueness check covers).

    Auto-corrections applied:
      - Dangling links are silently removed (logged as warning)
      - node_type drift on surviving nodes is auto-reverted to original
      - template_name drift on surviving nodes is auto-reverted to original

    Args:
        original_topology: The original topology dict (before edit).
        patched_topology: The LLM-patched topology dict (after edit).

    Returns:
        Tuple of (patched_topology, issues) where:
          - patched_topology: The (possibly auto-corrected) topology dict.
          - issues: List of warning/error strings for logging and diagnostics.
    """
    issues: list[str] = []

    # Normalise: handle both {"topology": {...}} and bare {...} forms
    orig_topo = original_topology.get("topology", original_topology)
    patch_topo = patched_topology.get("topology", patched_topology)

    orig_nodes = orig_topo.get("nodes", [])
    patch_nodes = patch_topo.get("nodes", [])
    patch_links = patch_topo.get("links", [])

    # Build index maps for O(1) lookups
    orig_id_map: dict[str, dict] = {
        n.get("node_id"): n for n in orig_nodes if n.get("node_id")
    }
    patch_id_map: dict[str, dict] = {
        n.get("node_id"): n for n in patch_nodes if n.get("node_id")
    }
    orig_ids = set(orig_id_map.keys())
    patch_ids = set(patch_id_map.keys())

    # ── Check 1: Deleted nodes (original - patched) ──────────────────────
    deleted_ids = orig_ids - patch_ids
    if deleted_ids:
        issues.append(
            f"WARNING: Node IDs removed from topology: {sorted(deleted_ids)}. "
            f"If this was not intended by the edit instruction, the LLM may have "
            f"unintentionally dropped these nodes."
        )
        for nid in sorted(deleted_ids):
            logger.warning(
                "safe_merge: Node '%s' was present in original but missing "
                "from patched topology", nid
            )

    # ── Check 2: New nodes (patched - original) ──────────────────────────
    added_ids = patch_ids - orig_ids
    if added_ids:
        # Verify no collision with surviving nodes (shouldn't happen but
        # check anyway — the LLM might reuse an existing node_id for a
        # completely different node)
        issues.append(
            f"INFO: New node IDs added by edit: {sorted(added_ids)}"
        )

    # ── Check 3: Dangling links ──────────────────────────────────────────
    # Links referencing node_ids not present in the patched nodes list.
    # These MUST be removed or schema validation will reject the topology.
    valid_patch_ids = patch_ids
    clean_links = []
    dangling_count = 0
    for link in patch_links:
        endpoints = link.get("nodes", [])
        if len(endpoints) < 2:
            issues.append(
                f"WARNING: Link with fewer than 2 endpoints removed"
            )
            dangling_count += 1
            continue

        ep_ids = {ep.get("node_id") for ep in endpoints}
        missing = ep_ids - valid_patch_ids
        if missing:
            issues.append(
                f"WARNING: Dangling link removed — references non-existent "
                f"node_id(s): {missing}. Endpoints: {ep_ids}"
            )
            logger.warning(
                "safe_merge: Removing dangling link referencing %s", missing
            )
            dangling_count += 1
            continue

        clean_links.append(link)

    if dangling_count > 0:
        # Apply auto-correction: replace links with cleaned version
        patch_topo["links"] = clean_links
        issues.append(
            f"AUTO-CORRECTED: Removed {dangling_count} dangling link(s)"
        )
        logger.info(
            "safe_merge: Auto-removed %d dangling link(s)", dangling_count
        )

    # ── Check 4: Duplicate node_ids in patched topology ──────────────────
    seen_ids: dict[str, str] = {}  # node_id -> name
    for n in patch_nodes:
        nid = n.get("node_id")
        if nid in seen_ids:
            issues.append(
                f"ERROR: Duplicate node_id '{nid}' found in patched topology. "
                f"First occurrence: '{seen_ids[nid]}', second: '{n.get('name', '?')}'. "
                f"This will cause schema validation to fail."
            )
            logger.error(
                "safe_merge: Duplicate node_id '%s' in patched topology", nid
            )
        else:
            seen_ids[nid] = n.get("name", "?")

    # ── Check 5: Surviving node attribute drift ──────────────────────────
    # For nodes that exist in BOTH original and patched, verify that core
    # attributes were not silently changed by the LLM.
    surviving_ids = orig_ids & patch_ids
    drift_reverts = 0
    for nid in surviving_ids:
        orig_node = orig_id_map[nid]
        patch_node = patch_id_map[nid]

        # node_type should NEVER change for the same node_id
        orig_type = orig_node.get("node_type", "")
        patch_type = patch_node.get("node_type", "")
        if orig_type != patch_type:
            issues.append(
                f"AUTO-CORRECT: Node '{nid}' changed node_type from "
                f"'{orig_type}' to '{patch_type}'. Reverting — the same "
                f"node_id should not change device type."
            )
            logger.warning(
                "safe_merge: Node '%s' node_type drift '%s' -> '%s', "
                "reverting to original", nid, orig_type, patch_type
            )
            patch_node["node_type"] = orig_type
            drift_reverts += 1

        # template_name should not change for the same node_id
        orig_template = orig_node.get("template_name", "")
        patch_template = patch_node.get("template_name", "")
        if orig_template != patch_template:
            issues.append(
                f"AUTO-CORRECT: Node '{nid}' changed template_name from "
                f"'{orig_template}' to '{patch_template}'. Reverting — "
                f"template changes on existing nodes cause hardware mismatches."
            )
            logger.warning(
                "safe_merge: Node '%s' template_name drift '%s' -> '%s', "
                "reverting to original", nid, orig_template, patch_template
            )
            patch_node["template_name"] = orig_template
            drift_reverts += 1

    if drift_reverts > 0:
        issues.append(
            f"AUTO-CORRECTED: Reverted {drift_reverts} attribute drift(s) "
            f"on surviving nodes"
        )

    # ── Check 6: New node collision with original nodes ──────────────────
    # If a "new" node_id in the patched topology collides with an existing
    # node_id that was DELETED, it means the LLM may have replaced the node
    # rather than editing it.  This isn't necessarily wrong, but we flag it
    # so the operator knows.
    if added_ids and deleted_ids:
        # Check if any added ID looks like a renamed version of a deleted ID
        # (same base type, similar name).  This is a heuristic check.
        for added_id in added_ids:
            for deleted_id in deleted_ids:
                # Heuristic: same first character (e.g., R1 -> R4, PC1 -> PC5)
                # or similar naming pattern
                if (added_id[0:1] == deleted_id[0:1]
                        and added_id != deleted_id):
                    issues.append(
                        f"INFO: New node '{added_id}' may be a rename of "
                        f"deleted node '{deleted_id}'. If this was intentional "
                        f"(e.g., the user asked to replace a device), no "
                        f"action is needed."
                    )

    logger.info(
        "safe_merge: Completed — %d deleted, %d added, %d dangling links "
        "removed, %d drift reverts, %d total issues",
        len(deleted_ids), len(added_ids), dangling_count,
        drift_reverts, len(issues)
    )

    return patched_topology, issues


# -- Conversational Reply ----------------------------------------------------

def generate_chat_reply(user_message: str, chat_history: list = None) -> str:
    """Generate a conversational reply for CHAT intent.
    
    Used when the user is asking questions, needs clarification, or chatting.
    Returns a text string (not JSON).
    """
    client = _get_client()
    
    system_prompt = """You are Structranet AI, an intelligent network topology assistant.
You help users design, create, and modify GNS3 network topologies using natural language.

You can:
- Create new network topologies from descriptions
- Modify existing topologies (add/remove devices, change links)
- Answer questions about networking concepts, GNS3, Cisco IOS, and topology design
- Provide guidance on best practices for network architecture

When a user asks you to create or modify a topology, let them know you can do that
and suggest they describe what they need. Be helpful, concise, and technically accurate.

If they ask about your capabilities, explain that you can generate GNS3 topologies
including Router-on-a-Stick, Campus LAN, Serial WAN, NAT, DHCP, and ACL configurations."""

    messages = [{"role": "system", "content": system_prompt}]
    
    # Add chat history for context
    if chat_history:
        for msg in chat_history[-10:]:  # Last 10 messages for context window
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        def _chat_call():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
            )
        
        response = _call_with_retry(_chat_call)
        if response and response.choices:
            return response.choices[0].message.content or "I'm not sure how to help with that. Could you rephrase?"
    except Exception as e:
        logger.error("Chat reply generation failed: %s", e)
    
    return "I'm having trouble responding right now. Please try again."


# ==============================================================================
#  CLI entry point
# ==============================================================================

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
