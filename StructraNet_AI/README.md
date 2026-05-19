# Structranet AI

**Natural Language → AI Designs Network → Interactive Review → Validates → Exports Portable `.gns3project`**

Structranet AI is an AI-powered virtual network engineer that transforms natural language descriptions into fully configured, offline GNS3 network topologies. Describe the network you want in plain English, and Structranet AI designs the topology, assigns hardware, generates IP addressing and routing configurations, and exports it as a portable `.gns3project` ZIP file that can be imported directly into GNS3.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Pipeline](#pipeline)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Interactive Review Loop](#interactive-review-loop)
- [Chain-of-Thought Reasoning](#chain-of-thought-reasoning)
- [Image Verification Manifest](#image-verification-manifest)
- [Rich Node Context](#rich-node-context)
- [Multi-Turn Chat History](#multi-turn-chat-history)
- [Security Profiles](#security-profiles)
- [Supported Device Types](#supported-device-types)
- [Key Design Decisions](#key-design-decisions)
- [Validation & Testing](#validation--testing)
- [Export Format](#export-format)
- [Configuration Reference](#configuration-reference)
- [Known Issues & Roadmap](#known-issues--roadmap)

---

## Overview

Network engineering is repetitive: spin up routers, assign IPs, configure routing protocols, wire switches. Structranet AI automates this entire workflow. A user describes their intent — *"Build a campus network with 3 VLANs, a core router, and 6 PCs"* — and the system:

1. Uses an LLM to reason step-by-step about the design (Chain-of-Thought), then generates the logical topology
2. Presents the draft design to the user and pauses for approval or edit feedback
3. Accepts iterative feedback and regenerates until the user approves (interactive Edit loop)
4. Deterministically assigns adapter/port numbers (no LLM guesswork)
5. Injects the correct hardware expansion modules (slot modules, adapter counts)
6. Enriches every node with full interface maps, hardware summaries, and security metadata
7. Generates an image verification manifest so users know exactly which GNS3 images are needed
8. Generates full software configurations (IPs, routing, VLANs, startup scripts)
9. Exports a portable `.gns3project` ZIP that can be imported into any GNS3 installation

Every constant, path format, and schema field has been validated against the **GNS3 2.2 server source code** to ensure the exported project files import cleanly without errors.

---

## Architecture

Structranet AI uses a **two-phase pipeline** with an interactive checkpoint loop separating them:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: Topology + Hardware  (Interactive Loop)                  │
│                                                                     │
│  User Input ──► AI Agent (LLM) ──► CoT Reasoning + TopologyRequest │
│       │              │                   (nodes + connections)      │
│       │              │                        │                     │
│       │    ┌─────────▼──────────┐             │                     │
│       │    │  CHECKPOINT PAUSE  │             │                     │
│       │    │  Display Thinking  │             │                     │
│       │    │  Display Topology  │             │                     │
│       │    │  Continue / Edit   │             │                     │
│       │    └──────┬──────┬──────┘             │                     │
│       │     Edit  │      │ Continue           │                     │
│       │     with  │      └────────────────────┘                     │
│       │  feedback │             │                                    │
│       │     (chat history       │                                    │
│       │      preserved) ◄───────┘                                   │
│       │                        │                                     │
│       │                  Port Assigner                               │
│       │                   (deterministic)                            │
│       │                        │                                     │
│       │              Hardware Injector                               │
│       │           (slots, adapters, ports_mapping)                  │
│       │                        │                                     │
│       │              Node Enrichment                                 │
│       │       (_interfaces, _hardware_summary,                      │
│       │        _security_role, _zone, _link_count)                  │
│       │                        │                                     │
│       │              Switch Port Patcher                            │
│       │           (VLAN trunk/access assignments)                   │
│       │                        │                                     │
│       │              Image Manifest Writer                          │
│       │           (image_manifest.txt)                              │
│       └────────────────────────│────────────────────────────────────┘
                                 │
┌────────────────────────────────│─────────────────────────────────────┐
│  Phase 2: Software Configuration                                    │
│                                ▼                                    │
│  Context Builder ──► Config Brief ──► AI Agent (LLM)              │
│       │                                         │                   │
│       │                                  Software Configs           │
│       │                                   (IPs, routing, VLANs)    │
│       │                                         │                   │
│       └──────── Three-Gate Safe Merge ◄──────────┘                 │
│                  (whitelist → no-overwrite → type check)            │
│                  (underscore keys always dropped)                   │
│                        │                                            │
│                  Final Topology JSON                                │
└────────────────────────│────────────────────────────────────────────┘
                         │
                         ▼
              .gns3project ZIP Export
              (GNS3 object graph +
            config file extraction)
           (portable offline project)
```

---

## Pipeline

The full CLI pipeline runs in 6 steps:

| Step | Module | Description |
|------|--------|-------------|
| 1/6 | Load catalog | Load built-in + custom appliance definitions |
| 2/6 | User input + Preflight | CLI argument or interactive prompt; collect environment profile |
| 3/6 | `ai_agent` | LLM reasons step-by-step (CoT), then generates `TopologyRequest`; pipeline **pauses** for user approval or edit feedback; loop repeats with full chat history until approved |
| 4/6 | `port_assigner` → `hw_config` → `_enrich_nodes` → `topology_finalizer` | Deterministic port assignment + hardware slot injection + node metadata enrichment + VLAN switch-port patching + image manifest generation |
| 5/6 | `config_agent` | LLM generates software configs (IPs, routing, startup scripts); security hardening applied if profile != "none" |
| 6/6 | `gns3_exporter` → `gns3project_validator` | Convert final topology JSON to portable `.gns3project` ZIP; run 11 structural checks to ensure import safety |

---

## Project Structure

```
structranet-ai/
├── main.py                     # Grand orchestrator — 6-step CLI pipeline with interactive loop
│
├── preflight.py                # Environment profile collection + compatibility gate + security profile
│
├── ai_agent.py                 # Phase 1: LLM topology generation
│                               #   SessionState dataclass (chat history, topology, thinking text)
│                               #   CoT envelope parsing (thinking + topology keys)
│                               #   _enrich_nodes() — rich node metadata injection
│                               #   generate_image_manifest() — image_manifest.txt writer
├── config_agent.py             # Phase 2: LLM software config generation
├── security_prompts.py         # Security profile prompt injection (none/basic/enterprise)
├── schema.py                   # Pydantic models (TopologyRequest, GNS3Project, etc.)
│
├── port_assigner.py            # Deterministic adapter/port number assignment
├── hw_config.py                # Hardware injection (slots, adapters, ports_mapping)
├── topology_finalizer.py       # VLAN switch port patching (trunk/access)
├── context_builder.py          # Configuration brief builder + port name resolution
├── llm_utils.py                # Shared LLM utilities (client, retry logic, JSON extraction)
│
├── constants/                  # Shared constants package (single source of truth)
│   ├── gns3.py                 # GNS3 format constants
│   ├── hardware.py             # Hardware and node-type constants (SSOT)
│   ├── appliances.py           # Built-in appliance catalog constants
│   ├── phase2.py               # Phase 2 safe-merge constants
│   ├── ai.py                   # AI pipeline constants (retry/limits)
│   ├── validation.py           # Validation constants (backward-compat re-exports)
│   └── __init__.py             # Constants package init
├── appliance_catalog.py        # Static appliance definitions (Cisco 7200, IOU, VPCS, etc.)
│
├── gns3_exporter.py            # .gns3project ZIP archive packaging + verification
│
├── gns3project_validator.py    # Deep structural validator for .gns3project files
│
├── tests/
│   ├── test_golden_export.py   # Golden export + validator regression test
│   └── fixtures/
│       └── golden_minimal_topology.json
│
├── requirements.txt            # Python dependencies
└── output/                     # Generated topology files
    ├── _topology.json          # Phase 1 output (hardware-injected, enriched)
    ├── final_topology.json     # Phase 2 output (software configs merged)
    ├── image_manifest.txt      # Image verification manifest (new in V4.0)
    ├── preflight_profile.json  # Saved environment profile
    ├── generation_report.json  # Structured per-run report (includes CoT + iterations)
    └── configs_review/         # Optional raw config export for pre-GNS3 review
```

### Module Responsibilities

| Module | Role | Key Functions / Types |
|--------|------|----------------------|
| `main.py` | Entry point, pipeline orchestration, interactive loop | `_checkpoint_loop()`, `_print_thinking()`, `_print_topology_summary()`, `parse_args()`, `main()` |
| `preflight.py` | Environment readiness + security profile | `collect_profile_interactive()`, `check_topology_compatibility()`, `filter_inventory_by_profile()` |
| `ai_agent.py` | LLM topology design, CoT, history, enrichment, manifest | `SessionState`, `generate_network_topology()`, `process_and_save_topology()`, `_enrich_nodes()`, `generate_image_manifest()` |
| `config_agent.py` | LLM config generation + safe merge | `run_phase2()`, `safe_merge_configs()`, `generate_software_configs()` |
| `security_prompts.py` | Security profile prompt templates | `get_topology_security_prompt()`, `get_config_security_prompt()` |
| `schema.py` | Data contracts | `TopologyRequest`, `GNS3Project`, `validate_topology()`, `validate_topology_request()` |
| `port_assigner.py` | Port number math | `assign_ports()`, `build_topology_from_request()` |
| `hw_config.py` | Hardware expansion | `inject_hardware_config()` |
| `topology_finalizer.py` | VLAN switching | `apply_switch_port_patches()` |
| `context_builder.py` | LLM context builder | `build_configuration_brief()`, `resolve_port_name()`, `build_segments()` |
| `llm_utils.py` | Shared LLM utilities (SSOT) | `_get_client()`, `_call_with_retry()`, `_extract_json()` |

---

## Getting Started

### Prerequisites

- Python 3.10+
- GNS3 2.2+ (for importing the exported project)
- An OpenAI-compatible LLM API key

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/structranet-ai.git
cd structranet-ai

# Install dependencies
pip install openai pydantic python-dotenv

# Create .env file
cat > .env << 'EOF'
ROUTER_API_KEY=your-api-key-here
ROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=openrouter/owl-alpha
AI_MAX_TOKENS=8192
EOF
```

---

## Usage

### Basic interactive run (with checkpoint loop)

```bash
python main.py --request "Build a campus network with 2 routers, a core switch, 3 access switches, and 9 PCs across 3 VLANs"
```

During Phase 1 you will see:

1. The AI's **chain-of-thought reasoning** printed in a delimited box
2. A **node and link table** showing the draft topology
3. A prompt asking you to **Continue**, **Edit**, or **Quit**

If you choose **Edit**, type your modification feedback (e.g. *"Add a second router for redundancy and connect it to the core switch via serial"*). The pipeline re-runs Phase 1 with your feedback incorporated into the conversation history.

### Common flags

```bash
# Skip the checkpoint loop (non-interactive / CI mode)
python main.py --request "3-router topology" --auto-continue

# Limit edit iterations
python main.py --request "3-router topology" --max-edits 3

# Skip Phase 2 (topology-only, no IOS configs)
python main.py --request "3-router topology" --no-phase2

# Apply security hardening
python main.py --request "3-router topology" --security-profile basic
python main.py --request "enterprise network" --security-profile enterprise

# Custom output paths
python main.py --request "3-router topology" --output output/my_topo.json --project-output output/my_lab.gns3project

# Export raw configs for human review
python main.py --request "3-router topology" --configs ./config_review

# Use a saved preflight profile (non-interactive environment info)
python main.py --request "3-router topology" --profile output/preflight_profile.json

# Skip structural validation
python main.py --request "3-router topology" --no-validate
```

### CLI flag reference

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--request` | `-r` | *(prompt)* | Network description (skips interactive prompt) |
| `--output` | `-o` | `output/final_topology.json` | Output JSON file path |
| `--catalog` | | | Path to custom appliance catalog JSON overlay |
| `--profile` | | | Path to preflight environment profile JSON |
| `--security-profile` | | `none` | Security hardening: `none` \| `basic` \| `enterprise` |
| `--no-phase2` | | off | Skip Phase 2 (software configuration generation) |
| `--project-output` | | auto | Output `.gns3project` path |
| `--no-validate` | | off | Skip post-export structural validation |
| `--configs` | | `output/configs_review` | Export raw configs to directory for pre-GNS3 review |
| `--auto-continue` | | off | Skip interactive checkpoint loop |
| `--yes` | | off | Alias for `--auto-continue` (also skips export confirmation) |
| `--max-edits` | | `5` | Maximum Edit loop iterations before forced Continue |

### Programmatic export

```python
from gns3_exporter import convert
import json

with open("output/final_topology.json") as f:
    topology = json.load(f)

path = convert(topology, "my_network.gns3project")
print(f"Exported to: {path}")
# Import: GNS3 GUI → File → Import portable project
```

---

## Interactive Review Loop

The Phase 1 checkpoint loop is the core of the V4.0 interactive experience.

### Flow

```
Phase 1 runs
    │
    ▼
AI Thinking displayed (chain-of-thought box)
    │
    ▼
Draft topology table displayed (nodes + links)
    │
    ▼
User prompt: [C]ontinue / [E]dit / [Q]uit
    │
    ├── Continue → hardware injection → manifest → Phase 2
    │
    ├── Edit → capture feedback → append to chat history → re-run Phase 1
    │             (loop, up to --max-edits times)
    │
    └── Quit → exit pipeline
```

### Edit feedback examples

```
  Your choice [C/e/q]: e

  Describe your changes:
  > Add a redundant second router connected to Core-SW via serial link
  > Add a DMZ switch between the router and the internet NAT node
  > Replace the three access switches with two — merge F2-SW and F3-SW
  > Use IOU L3 instead of Cisco 3745 for the router
```

Each piece of feedback is appended to the chat history as a user message. The LLM receives the entire conversation context and modifies the existing design rather than generating an entirely new one from scratch.

### Non-interactive mode

Pass `--auto-continue` or `--yes` to skip all prompts. The first generated topology is accepted automatically. Useful for CI pipelines, batch generation, and testing.

---

## Chain-of-Thought Reasoning

When generating a topology, the LLM is required to reason step-by-step before committing to a design. The reasoning covers:

- Which device types best fit the request and why
- How many of each device is needed
- The topology pattern (star, hierarchical, ring, etc.)
- VLAN, security, and redundancy considerations
- Link-limit constraints being worked around

### Output contract

The LLM returns a two-key JSON envelope:

```json
{
  "thinking": "Step 1: The user wants a campus network...\nStep 2: I'll use a Router-on-a-Stick pattern...",
  "topology": {
    "name": "Campus-Network",
    "nodes": [...],
    "connections": [...]
  }
}
```

The `thinking` string is displayed to the user at the checkpoint. The `topology` object is passed through the existing Pydantic validation gates unchanged. If a model returns the topology at the top level (skipping the envelope), the parser falls back gracefully.

The thinking text is also stored in `output/generation_report.json` under the `last_thinking` key for post-run analysis.

---

## Image Verification Manifest

After Phase 1 hardware injection, `output/image_manifest.txt` is generated. It cross-references every node against the preflight profile's `template_image_map` and clearly states what is needed before import.

### Example output

```
======================================================================
  STRUCTRANET AI — IMAGE VERIFICATION MANIFEST
======================================================================

  Nodes: 8
  Images in map: 2

  Node ID      Name                 Template                  Status / Image File
  ------------------------------------------------------------------
  R1           R1-Main              Cisco 3745                ✓  c3745-adventerprisek9-mz.124-25d.image
  R2           R2-Branch            Cisco 3745                ✓  c3745-adventerprisek9-mz.124-25d.image
  Core-SW      Core-SW              Ethernet Switch           ✓  Built-in — no image required
  F1-SW        F1-SW                Ethernet Switch           ✓  Built-in — no image required
  PC1          PC1                  VPCS                      ✓  Built-in — no image required
  ...

  ✓  All appliance nodes have image mappings.
======================================================================
```

If any appliance node's template name is not in the `template_image_map`, it is flagged with ⚠ and listed in a "MISSING IMAGE MAPPINGS" section at the bottom.

A compact summary is also printed inline during the pipeline run so users don't need to open the file to see if there are issues.

---

## Rich Node Context

Every node in the topology is enriched with metadata after hardware injection. This data is embedded directly in the node's `properties` dict under underscore-prefixed keys so it travels through the entire pipeline — including into the exported `final_topology.json` — without being touched by the Phase 2 safe-merge.

### Enrichment fields

| Field | Type | Description |
|-------|------|-------------|
| `_interfaces` | `list[str]` | All canonical interface names (e.g. `["FastEthernet0/0", "FastEthernet0/1", "Serial1/0"]`) |
| `_hardware_summary` | `str` | Compact slot/adapter summary (e.g. `platform=c3745 ram=128MB \| slot1=NM-1FE-TX`) |
| `_image_required` | `bool` | `True` for appliance types (dynamips, iou, qemu, etc.), `False` for built-ins |
| `_security_role` | `str` | Security role assigned by the LLM (e.g. `perimeter`, `core-switch`, `host`) |
| `_zone` | `str` | Security zone (e.g. `OUTSIDE`, `INSIDE`, `DMZ`, `MANAGEMENT`) |
| `_vlan_id` | `int` | VLAN ID for access switches (0 for routers/core) |
| `_link_count` | `int` | Number of links connected to this node |

These fields are intentionally outside `SOFTWARE_CONFIG_KEYS` so Phase 2 can never overwrite them. A UI inspector or frontend can read them directly from `final_topology.json` to show full node details when a user clicks on a node.

---

## Multi-Turn Chat History

The `SessionState` dataclass carries the accumulated OpenAI message list across all Edit loop iterations:

```python
@dataclass
class SessionState:
    chat_history: List[Dict[str, str]]   # OpenAI message dicts
    topology_dict: Optional[Dict]        # Last approved hardware-injected topology
    thinking_text: str                   # Last CoT reasoning text
    iteration: int                       # How many Phase 1 calls have run
    last_request: str                    # Original user request (never mutated)
```

On every call to `generate_network_topology()`, the accumulated history is prepended to the LLM's message array:

```
[system prompt]
[user: original request]              ← iteration 1
[assistant: first topology JSON]      ← iteration 1
[user: edit feedback]                 ← iteration 2
[assistant: second topology JSON]     ← iteration 2
[user: second edit feedback]          ← iteration 3
...
```

This gives the LLM full context to refine rather than restart. The original request always anchors the conversation, and each piece of feedback builds on the previous design.

---

## Security Profiles

Structranet AI includes three built-in security profiles selected via `--security-profile` or the preflight profile JSON.

### Profile: "none" (Default)

No security rules injected. Pure lab/universal mode.

### Profile: "basic"

Lightweight hardening applied to every router:

- Mandatory NAT node for Internet edge
- Dedicated management VPCS host
- SSH v2, AAA, login rate-limiting
- Syslog/NTP with standard servers
- Service hardening and banner enforcement

### Profile: "enterprise"

Full security archetype:

**Mandatory topology roles:** Perimeter Router (ZBF), Core Switch, DMZ Switch, Management Switch, SIEM, NAT-ISP, optional Secondary Router (HSRP)

**VLAN segmentation** auto-detected from switch names:

| Segment | VLAN | Switch name contains |
|---------|------|---------------------|
| Management | 10 | `MGMT` or `Mgmt` |
| Users / LAN | 20 | `USER` or `LAN` |
| Servers | 30 | `SRV` or `Server` |
| VoIP | 40 | `VOIP` or `Voice` |
| IoT | 50 | `IOT` |
| DMZ | 60 | `DMZ` |
| Guest | 100 | `GUEST` |
| Native unused | 999 | trunk ports |

**Config hardening per node role:** ZBF zones/policies, anti-spoofing ACLs, TCP intercept, OSPF MD5 auth, NAT PAT overload, HSRP with MD5, DHCP Snooping, DAI, port-security, storm-control, SNMPv3, loopback interfaces, NTP auth.

### Preflight Profile JSON with security

```json
{
  "gns3_version": "2.2.54",
  "supports_iou": false,
  "supports_qemu": true,
  "supports_docker": false,
  "strict_validation": true,
  "require_template_image_map": false,
  "template_image_map": {
    "Cisco 3745": "c3745-adventerprisek9-mz.124-25d.image"
  },
  "security_profile": "enterprise"
}
```

---

## Supported Device Types

### Routers (L3)

| Type | Platforms | Expansion | Built-in Ports |
|------|-----------|-----------|----------------|
| **Dynamips** | c7200, c3745, c3725, c3660, c3640, c3620, c2691, c2600, c1700 | Slot-based modules (PA-8E, NM-4E, PA-4T+, NM-4T, etc.) | 0–2 per platform |
| **IOU** | IOU L3, IOU L2 | Count-based (`ethernet_adapters`, `serial_adapters`, 4 ports each) | — |
| **QEMU** | CSR1000v, etc. | `adapters` integer (max 275) | — |
| **Docker** | Custom containers | `adapters` integer (max 99) | — |

### Switches & Hubs (L2)

| Type | Expansion | Port Format |
|------|-----------|-------------|
| **Ethernet Switch** | `ports_mapping` array (VLAN-aware: access/dot1q) | `Ethernet{N}` |
| **Ethernet Hub** | `ports_mapping` array | `Ethernet{N}` |

### End Devices

| Type | Ports | Config |
|------|-------|--------|
| **VPCS** | 1 (fixed) | `startup_script` |
| **TraceNG** | 1 (fixed) | — |
| **NAT** | 1 (fixed) | — |
| **Cloud** | Variable | — |

---

## Key Design Decisions

### 1. Pause-and-Resume Loop Without an API Server

All state is carried in a single `SessionState` dataclass that is passed explicitly through the pipeline. There are no global variables and no external server required. The loop lives entirely in `main.py`'s `_checkpoint_loop()` function, which calls `generate_network_topology()` and reads user input in a `for` loop. This keeps the architecture simple, testable, and easy to extend into a web API later by replacing `input()` calls with HTTP request handlers.

### 2. CoT Envelope — Thinking Separate from Validated Data

The LLM returns `{"thinking": "...", "topology": {...}}`. The `thinking` string is extracted and displayed but never passed to Pydantic. The `topology` object goes through all the same validation gates as before. This means CoT reasoning is purely additive — it cannot break existing validation behaviour regardless of what the model writes in the thinking field.

### 3. LLM Only Designs, Code Assigns Ports

The single largest source of deployment failures in previous versions was the LLM computing adapter/port numbers incorrectly. This architecture strictly separates concerns: the LLM decides *what* connects to *what*; `port_assigner.py` computes *where* on each device.

### 4. Underscore-Prefixed Metadata Keys

All node enrichment fields are prefixed with `_` (`_interfaces`, `_hardware_summary`, etc.). This convention ensures they are outside `SOFTWARE_CONFIG_KEYS` and will never be touched by Phase 2's Three-Gate Safe Merge. A UI inspector can read them directly from `final_topology.json` without any additional API calls.

### 5. Three-Gate Safe Merge

Phase 2 merges LLM output with three safety gates:

1. **Whitelist Gate**: only `startup_config_content`, `startup_script`, `start_command`, and `environment` are accepted; keys starting with `_` are silently dropped
2. **No-Overwrite Gate**: existing non-empty hardware properties can never be replaced
3. **Type Gate**: value types must match expected types

### 6. Deterministic Output

The same topology JSON always produces the same `.gns3project` file. UUIDs are derived via UUID5, canvas coordinates are computed from device role priority, and port assignments follow deterministic rules.

### 7. Single Source of Truth for Constants

The `constants/` package is the authoritative reference. All values are verified against the GNS3 2.2 server source code.

---

## Validation & Testing

### Structural Validator

`gns3project_validator.py` performs 11 deep validation checks on any `.gns3project` file:

1. ZIP structure
2. JSON schema conformity (revision 9, required keys)
3. Node validation
4. Dynamips compatibility matrix
5. Port reference integrity
6. Config file path consistency
7. Template ID format
8. Compute cross-referencing
9. Switch VLAN sanity
10. Link integrity
11. UUID format validation

```bash
python gns3project_validator.py <file.gns3project>
python gns3project_validator.py <file.gns3project> --verbose
```

### Golden End-to-End Test

```bash
python -m unittest tests.test_golden_export
```

### Post-Generation Report

Each run writes `output/generation_report.json` containing:

- Request text and timestamp
- Effective preflight profile
- `phase1_iterations` — how many Edit loop rounds were needed
- `last_thinking` — the final chain-of-thought text from the LLM
- Compatibility findings
- Output paths (phase1 JSON, final JSON, `.gns3project`, image manifest)
- Validator result

---

## Export Format

The `.gns3project` export produces a GNS3 revision 9 portable project ZIP:

```
my_network.gns3project
├── project.gns3                                                   # Main topology JSON
├── project-files/dynamips/<uuid>/configs/startup-config.cfg      # Dynamips startup config
├── project-files/dynamips/<uuid>/configs/private-config.cfg      # Dynamips private config
├── project-files/iou/<uuid>/startup-config.cfg                   # IOU startup config
├── project-files/vpcs/<uuid>/startup.vpc                         # VPCS startup script
└── project-files/<node_type>/<uuid>/                             # Node directory
```

Node properties in `project.gns3` include the full enrichment metadata (`_interfaces`, `_hardware_summary`, etc.) so any tool that reads the JSON can display complete node information without additional lookups.

---

## Configuration Reference

### Appliance Catalog

The built-in appliance catalog (`appliance_catalog.py`) defines mandatory creation properties for each supported device. Users can override or extend it by providing a JSON overlay:

```python
from appliance_catalog import load_catalog
catalog = load_catalog("my_custom_appliances.json")
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ROUTER_API_KEY` | *(required)* | OpenAI-compatible API key |
| `ROUTER_BASE_URL` | *(required)* | LLM API base URL |
| `AI_MODEL` | `openrouter/owl-alpha` | LLM model identifier |
| `AI_MAX_TOKENS` | `8192` | Max tokens per LLM call |
| `STRUCTRANET_OUTPUT_DIR` | `output` | Output directory for topology files |

---

## Known Issues & Roadmap

### Completed in V4.0

- ✅ **Interactive Phase 1 checkpoint loop** — pause, display thinking, Edit or Continue
- ✅ **Chain-of-Thought reasoning** — LLM reasons before generating; displayed at checkpoint
- ✅ **Multi-turn chat history** — Edit feedback preserved across iterations; LLM refines not restarts
- ✅ **Rich node context** — `_interfaces`, `_hardware_summary`, `_security_role`, `_zone`, `_link_count` on every node
- ✅ **Image verification manifest** — `image_manifest.txt` cross-references every appliance against preflight image map
- ✅ **Security profiles** ("none", "basic", "enterprise")
- ✅ **LLM utilities consolidation** — `llm_utils.py` is SSOT for client, retry, JSON extraction
- ✅ **Constants SSOT** — `constants/` package is authoritative
- ✅ **VLAN patching guarantee** — `apply_switch_port_patches()` runs even with `--no-phase2`

### Planned Improvements

- **Web API mode** — replace `input()` with HTTP endpoints; `SessionState` is already serialization-ready
- **Session persistence** — serialize `SessionState` to disk so Edit loops survive process restarts
- **Topology diff display** — show a before/after diff at the checkpoint instead of the full table after each Edit
- **Topology visualizer** — render the draft topology as an ASCII or SVG diagram at the checkpoint
- **Expand security profiles** — add "industrial", "healthcare", and "cloud-edge" archetypes
- **Broader test fixtures** — integration tests covering multi-VLAN, serial WAN, and enterprise security topologies

---

## License

This project is proprietary software. All rights reserved.