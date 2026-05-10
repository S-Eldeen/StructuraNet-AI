# Structranet AI

**Natural language → live GNS3 network topology.**

Describe the network you want in plain English. Structranet AI generates the full
topology JSON, assigns hardware (Dynamips slots, adapter counts, switch port mappings),
generates Cisco IOS startup configs and VPCS scripts, and deploys everything to a
running GNS3 server — nodes wired, IPs assigned, configs loaded, devices started.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Supported Networks](#supported-networks)
- [Project Files](#project-files)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration (.env)](#configuration-env)
- [Usage](#usage)
  - [Full Pipeline](#full-pipeline-mainpy)
  - [Test Without a GNS3 Server](#test-without-a-gns3-server-test_pipelinepy)
  - [Deploy an Existing JSON](#deploy-an-existing-json-assemblerpy)
  - [Phase 2 Only](#phase-2-only-config_agentpy)
- [Pipeline Internals](#pipeline-internals)
- [Supported Hardware](#supported-hardware)
- [Output Files](#output-files)
- [Troubleshooting](#troubleshooting)

---

## How It Works

Structranet AI runs a 7-step pipeline every time you describe a network:

```
[1] Fetch inventory      gns3_fetcher   → what templates are installed in GNS3?
[2] User input           CLI prompt     → what network do you want?
[3] AI topology          ai_agent       → nodes + logical connections (no port numbers)
[4] Hardware injection   hw_config      → Dynamips slots, adapter counts, ports_mapping
[4b] Switch patching     topology_finalizer → VLAN trunk/access layout on switch ports
[5] Software configs     config_agent   → IOS startup configs, VPCS scripts, Docker cmds
[6] Save JSON            output/        → final_topology.json
[7] Deploy               assembler      → GNS3 REST API: create project, nodes, links
```

**Two AI calls, everything else is deterministic code.**

- **Phase 1 (Step 3)** — The LLM decides *what* connects to *what*. It outputs a node
  list and a list of logical connections (`R1 → SW1`). It never touches port numbers.
- **Phase 2 (Step 5)** — The LLM receives a human-readable *Configuration Brief*
  (resolved interface names, VLAN assignments, segment types) and returns software
  configs. A Three-Gate Safe Merge ensures it can never overwrite hardware properties.

Port numbers, adapter counts, slot modules, and switch VLAN layouts are all computed
deterministically by code — not by the LLM.

---

## Supported Networks

| Network Type | Description |
|---|---|
| **Flat LAN** | Single subnet, one or more switches, VPCS hosts |
| **Inter-VLAN (Router-on-a-Stick)** | Core switch + access switches, 802.1Q sub-interfaces on router |
| **Multi-router WAN** | Serial or Ethernet point-to-point links, OSPF or static routing |
| **Hub-and-spoke LAN** | Hierarchical: core switch → access switches → hosts |
| **NAT gateway** | Router with inside LAN and GNS3 NAT node (outside), PAT overload config |
| **Docker/QEMU appliances** | Multi-adapter containers/VMs with `start_command` and `environment` injection |
| **IOU topologies** | Cisco IOU L2/L3 nodes with flat adapter numbering |

**Not yet supported:** Frame Relay / ATM switched topologies, multi-area OSPF, BGP,
IPv6, redundant topologies requiring STP.

---

## Project Files

```
structranet-ai/
│
├── main.py                # Entry point — full 7-step pipeline
├── test_pipeline.py       # Test the pipeline without a GNS3 server
│
├── ai_agent.py            # Phase 1 AI: generates topology (nodes + connections)
├── config_agent.py        # Phase 2 AI: generates software configs (IOS/VPCS/Docker)
│
├── port_assigner.py       # Deterministic port assignment (no LLM)
├── hw_config.py           # Hardware injection (Dynamips slots, adapter counts, ports_mapping)
├── topology_finalizer.py  # VLAN-aware switch port patching (trunk/access)
├── context_builder.py     # Builds Configuration Brief for Phase 2 LLM call
│
├── schema.py              # Pydantic models and validation
├── assembler.py           # GNS3 REST API deployer
├── gns3_fetcher.py        # GNS3 template inventory fetcher
│
├── .env                   # API keys and server config (not committed)
├── requirements.txt       # Python dependencies
└── output/                # Generated JSON files (created automatically)
    ├── _topology.json     # Phase 1 output (hardware-injected)
    └── final_topology.json # Final output (hardware + software configs)
```

### File Responsibilities

**`main.py`**
Orchestrates the full pipeline. Parses CLI arguments, calls each step in order,
handles fallbacks (Phase 2 failure falls back to Phase 1 output), and exits cleanly
on errors. Supports `--no-deploy`, `--no-phase2`, and `--deploy-only` modes.

**`ai_agent.py`**
Makes the Phase 1 LLM call. Builds a prompt from the hardware inventory, sends the
user request, validates the response as a `TopologyRequest`, and retries up to 3 times
with specific error feedback if validation fails. Also exposes `generate_edited_topology`
(patch an existing topology) and `generate_chat_reply` (conversational mode).

**`config_agent.py`**
Makes the Phase 2 LLM call. Loads the Phase 1 JSON, calls `topology_finalizer` to
patch switch ports, builds the Configuration Brief, sends it to the LLM, and merges
the returned configs through a Three-Gate Safe Merge:
- **Gate 1 — Whitelist:** only `startup_config_content`, `startup_script`,
  `start_command`, `environment` are allowed.
- **Gate 2 — No-overwrite:** existing non-empty property values are never replaced.
- **Gate 3 — Type check:** value types are validated before writing.

**`port_assigner.py`**
Converts logical connections (`R1 → SW1`) into `Link` objects with exact
`adapter_number` and `port_number` for every node type. Rules per type:
- `dynamips` — built-in ports first (adapter 0), then expansion adapters; serial links
  use adapters after all Ethernet adapters.
- `ethernet_switch` / `ethernet_hub` — `adapter=0` always, `port_number` increments
  from 0 (0-based, GNS3 server renumbers internally).
- `vpcs` / `traceng` / `nat` — exactly one port: `adapter=0, port=0`.
- `qemu` / `docker` / `virtualbox` / `vmware` — one adapter per link, `port=0` always.
- `iou` — flat adapter numbering: Ethernet adapters first, then Serial.

**`hw_config.py`**
Expands node `properties` after port assignment:
- `dynamips` — injects `slot1`, `slot2`, … with the correct module name
  (`PA-8E`, `NM-4E`, `PA-4T+`, `NM-4T`, etc.) based on how many links of each type
  the node has.
- `qemu` / `docker` / `virtualbox` / `vmware` — sets `adapters` count.
- `ethernet_switch` / `ethernet_hub` — builds the `ports_mapping` array.

**`topology_finalizer.py`**
Rewrites `ports_mapping` on switch nodes after hardware injection. Without this,
every switch port ships as `access/vlan=1` and 802.1Q frames from the router are
silently dropped. Two pass types:
- **Access switches** — uplink port (toward router/core) → `dot1q` trunk; host ports →
  `access` with the correct VLAN id.
- **Core switches** — every linked port → `dot1q` trunk (carries all VLANs).

**`context_builder.py`**
Reads the hardware-injected topology (read-only) and produces a human-readable
*Configuration Brief*: resolved interface names (`FastEthernet0/0`, `Ethernet1/0`),
segment types (multi-access/point-to-point/trunk), VLAN assignments, NAT roles, and
routing advice. This is what the Phase 2 LLM receives instead of raw JSON.

**`schema.py`**
All Pydantic models. Two layers:
- `TopologyRequest` / `NodeRequest` / `Connection` — Phase 1 LLM output (no port numbers).
- `GNS3Project` / `Topology` / `Node` / `Link` / `LinkNode` — full validated topology
  with port numbers. All validators are hard errors — no silent auto-correction.

**`assembler.py`**
Deploys a topology JSON to GNS3 via the v2 REST API:
1. Pre-flight check — validates all `template_name` values against the live inventory.
2. Creates project.
3. Creates nodes from templates (Path A) or directly (Path B fallback for built-ins).
4. Applies hardware properties via PUT.
5. Pushes startup configs via the **Files API** (`startup-config.cfg`, `startup.vpc`)
   — the properties PUT endpoint rejects these, so they go through a separate channel.
6. Waits for nodes to settle, then creates links.
7. Starts all nodes (optional).

**`gns3_fetcher.py`**
Polls `GET /v2/templates` and returns the device inventory. Uses `template_type`
(v2 field) with a logged fallback to the legacy `type` field. Templates missing both
fields are skipped with a warning rather than silently stored as `"unknown"`.

---

## Requirements

- Python 3.10+
- GNS3 server 2.x running locally or on the network (for deployment)
- At least one GNS3 appliance template installed (Dynamips IOS image, VPCS, etc.)
- An API key for an OpenAI-compatible LLM router (OpenRouter, direct OpenAI, etc.)

Python packages (from `requirements.txt`):

```
openai
pydantic
python-dotenv
requests
```

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/structranet-ai.git
cd structranet-ai

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example env file and fill in your keys
cp .env.example .env
```

---

## Configuration (.env)

Create a `.env` file in the project root with the following variables:

```dotenv
# ── LLM Router ────────────────────────────────────────────────────────────────
# API key for your LLM provider (OpenRouter, OpenAI, etc.)
ROUTER_API_KEY=sk-or-...

# Base URL for the OpenAI-compatible API endpoint
# OpenRouter:  https://openrouter.ai/api/v1
# OpenAI:      https://api.openai.com/v1
# Local (e.g. LM Studio): http://localhost:1234/v1
ROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model identifier as expected by your provider
# Examples:
#   openrouter/owl-alpha
#   anthropic/claude-sonnet-4-5
#   openai/gpt-4o
AI_MODEL=openrouter/owl-alpha

# Maximum tokens per LLM response (default: 8192)
AI_MAX_TOKENS=8192

# ── GNS3 Server ───────────────────────────────────────────────────────────────
# URL used by gns3_fetcher.py to poll for templates
GNS3_SERVER_URL=http://127.0.0.1:3080

# Host and port used by assembler.py at deployment time
# (can also be passed as --host / --port CLI flags)
GNS3_HOST=localhost
GNS3_PORT=3080

# ── Output ────────────────────────────────────────────────────────────────────
# Directory where generated JSON files are saved (default: output)
STRUCTRANET_OUTPUT_DIR=output
```

**Minimum required:** `ROUTER_API_KEY` and `ROUTER_BASE_URL`. Everything else has a
working default.

---

## Usage

### Full Pipeline (`main.py`)

Runs all 7 steps: fetch inventory → AI topology → hardware injection → switch patching →
software configs → save JSON → deploy to GNS3.

```bash
# Interactive — prompts you to describe the network
python main.py

# Non-interactive — pass the request directly
python main.py --request "3 c3745 routers in a triangle with serial WAN links and VPCS hosts on each"

# Generate JSON only, skip deployment
python main.py --request "campus LAN with 2 VLANs" --no-deploy

# Skip Phase 2 (no IOS configs, just the wiring)
python main.py --request "simple hub-and-spoke" --no-phase2

# Overwrite an existing GNS3 project with the same name
python main.py --request "updated design" --overwrite

# Don't start nodes after deployment
python main.py --request "test lab" --no-start

# Custom output file
python main.py --request "..." --output /tmp/my_topology.json

# Deploy to a remote GNS3 server
python main.py --request "..." --host 192.168.1.50 --port 3080
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--request`, `-r` | *(prompt)* | Network description (skips interactive prompt) |
| `--output`, `-o` | `output/final_topology.json` | Output JSON path |
| `--host` | `localhost` / `$GNS3_HOST` | GNS3 server hostname |
| `--port` | `3080` / `$GNS3_PORT` | GNS3 server port |
| `--overwrite` | false | Delete existing project with same name before deploying |
| `--no-start` | false | Don't start nodes after deployment |
| `--no-deploy` | false | Stop after saving JSON, skip deployment |
| `--no-phase2` | false | Skip software config generation (Phase 1 output only) |
| `--deploy-only FILE` | — | Deploy an existing JSON file, skip all generation steps |

---

### Test Without a GNS3 Server (`test_pipeline.py`)

Runs the full AI + hardware + software config pipeline using a built-in fake inventory.
No GNS3 server needed. Produces a `final_topology.json` ready for a teammate to deploy.

```bash
python test_pipeline.py "your network description"
```

**Examples:**

```bash
python test_pipeline.py "3 routers in a triangle with serial WAN links"
python test_pipeline.py "campus network with core switch, 2 access switches, and VPCS hosts"
python test_pipeline.py "2 c3745 routers connected via serial link with VPCS on each side"
python test_pipeline.py "Router-on-a-Stick with 3 departments: HR, IT, Finance"
python test_pipeline.py "small office with NAT gateway, one router, one switch, 3 PCs"
```

The fake inventory includes: `c7200`, `c3745`, `c3725`, `c3660`, `c3640`, `Switch`,
`Hub`, `VPCS`, `NAT`, `Cloud`, `IOU-L3`, `IOU-L2`.

Output files are written to `output/`:
- `_topology.json` — Phase 1 (hardware-injected, VLAN-patched)
- `final_topology.json` — Phase 2 (with IOS configs, VPCS scripts)

---

### Deploy an Existing JSON (`assembler.py`)

Deploy a previously generated `final_topology.json` to GNS3 without re-running the AI.

```bash
python assembler.py output/final_topology.json --host localhost --port 3080

# With an inventory file for template resolution
python assembler.py output/final_topology.json \
    --host 192.168.1.50 \
    --inventory output/inventory.json

# Overwrite existing project and don't start nodes
python assembler.py output/final_topology.json --overwrite --no-start
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `topology_file` | *(required)* | Path to the topology JSON |
| `--host` | `localhost` | GNS3 server hostname |
| `--port` | `3080` | GNS3 server port |
| `--overwrite` | false | Delete existing project with same name |
| `--no-start` | false | Don't start nodes after deployment |
| `--inventory FILE` | — | JSON inventory file for template_id resolution |

**Note:** Without `--inventory`, template_id resolution and the pre-flight validation
check are disabled. The assembler will attempt direct node creation, which only works
reliably for built-in node types (ethernet_switch, vpcs, nat, cloud).

---

### Phase 2 Only (`config_agent.py`)

Run software config generation on an existing Phase 1 JSON:

```bash
python config_agent.py output/_topology.json output/final_topology.json
```

Useful if Phase 2 failed during the main run and you want to retry without regenerating
the whole topology.

---

## Pipeline Internals

### Phase 1 — Logical Topology (ai_agent.py)

The LLM receives:
- The hardware inventory (what devices are available and their link limits)
- The user's request
- A schema for the expected JSON output (`TopologyRequest`)

It returns a JSON object with `nodes` and `connections` only — no port numbers. The
prompt is deliberately minimal (~80 lines) because port assignment is handled by code.

If the output fails Pydantic validation, specific error messages are fed back to the
LLM and it retries up to **3 times**.

### Port Assignment (port_assigner.py)

A pure deterministic function. Given a `TopologyRequest`, it walks the connections in
order and allocates `(adapter_number, port_number)` pairs for each endpoint using
per-type rules. The same input always produces the same output.

### Hardware Injection (hw_config.py)

After port assignment, `inject_hardware_config()` inspects each node's link count and
type, then writes the appropriate `properties`:

| Node type | What gets injected |
|---|---|
| `dynamips` | `slot1`, `slot2`, … (e.g. `"slot1": "NM-4E"`) |
| `qemu` / `docker` / `virtualbox` / `vmware` | `"adapters": N` |
| `ethernet_switch` / `ethernet_hub` | `"ports_mapping": [...]` |
| `vpcs` / `nat` / `traceng` | Nothing (single hard-locked port) |

### Switch Port Patching (topology_finalizer.py)

After hardware injection, `apply_switch_port_patches()` rewrites `ports_mapping` on
every `ethernet_switch` node:

- **Core switches** — identified by having both router and switch neighbours, or by
  `"core"` in their name. Every linked port becomes `dot1q` trunk.
- **Access switches** — get a VLAN id assigned (derived from their name suffix or
  auto-incremented: SW1 → VLAN 10, SW2 → VLAN 20, etc.). Uplink port → `dot1q` trunk,
  host ports → `access` with the assigned VLAN.
- **Flat switches** (no VLAN context) — left unchanged (`access/vlan=1`).

### Configuration Brief (context_builder.py)

The brief gives the Phase 2 LLM everything it needs to write configs without looking
at raw JSON:

```
NODES:
  R1 (dynamips/c3745, router)
    Interfaces: FastEthernet0/0, FastEthernet0/1, Ethernet1/0..Ethernet1/3

SEGMENTS:
  Segment 1 (802.1Q trunk):
    R1     FastEthernet0/0       <->  Core-SW Ethernet0
    → Configure 802.1Q sub-interfaces on the router side, one per VLAN.

  Segment 2 (multi-access, VLAN 10, access-sw: F1-SW, 2 host(s)):
    → Router sub-interface: FastEthernet0/0.10 (encapsulation dot1Q 10)
    PC1    eth0                  <->  F1-SW  Ethernet1
    ...
```

### Phase 2 Software Configs (config_agent.py)

The LLM receives the brief and returns a flat JSON map:
```json
{
  "R1": { "startup_config_content": "hostname R1\n!\ninterface FastEthernet0/0.10\n ..." },
  "PC1": { "startup_script": "ip 10.0.10.10/24 10.0.10.1\nsave\n" }
}
```

The Three-Gate Safe Merge writes these into `node.properties` — hardware properties
(`slot1`, `adapters`, `ports_mapping`, etc.) cannot be touched by the LLM under any
circumstances.

### Deployment (assembler.py)

The assembler uses two distinct channels for config injection:

| Config type | API channel | Nodes |
|---|---|---|
| `startup_config_content` | Files API (`startup-config.cfg`) | dynamips, iou, qemu |
| `startup_script` | Files API (`startup.vpc`) | vpcs |
| `start_command`, `environment` | Properties PUT | docker |

The GNS3 properties PUT endpoint rejects `startup_config_content` and `startup_script`
outright. The Files API writes directly to the node's virtual filesystem, which the
emulator reads on startup.

---

## Supported Hardware

### Dynamips Routers

| Platform | Built-in Eth ports | Expansion module | Max total links |
|---|---|---|---|
| c7200 | 1 (FastEthernet0/0) | PA-8E (Ethernet), PA-4T+ (Serial) | 3 |
| c3745 | 2 (Fa0/0, Fa0/1) | NM-4E (Ethernet), NM-4T (Serial) | 6 |
| c3725 | 2 (Fa0/0, Fa0/1) | NM-4E, NM-4T | 6 |
| c3660 | 2 (Fa0/0, Fa0/1) | NM-4E, NM-4T | 5 |
| c3640 | 0 | NM-4E, NM-4T | 4 |
| c3620 | 0 | NM-4E, NM-1T | 4 |
| c2691 | 2 (Fa0/0, Fa0/1) | NM-4E, NM-4T | 6 |
| c2600 | 1 (Fa0/0) | NM-1E, NM-1T | 2 |
| c1700 | 1 (Fa0/0) | NM-1E, NM-1T | 2 |

The max total links limit is a Dynamips PCI bus constraint, not a software limit.
Exceeding it causes the emulator to crash.

### Other Node Types

| Type | GNS3 template | Max links | Config injection |
|---|---|---|---|
| `ethernet_switch` | Switch | 128 | `ports_mapping` (VLAN/trunk) |
| `ethernet_hub` | Hub | 128 | `ports_mapping` |
| `vpcs` | VPCS | 1 | Files API (`startup.vpc`) |
| `nat` | NAT | 1 | None (passthrough) |
| `cloud` | Cloud | 1 | None |
| `iou` | IOU-L3 / IOU-L2 | 16 (4 per adapter × 4 adapters) | Files API (`startup-config.cfg`) |
| `qemu` | Any QEMU image | up to 275 | Files API or Properties PUT |
| `docker` | Any Docker image | up to 99 | Properties PUT (`start_command`, `environment`) |

---

## Output Files

After a successful run, the `output/` directory contains:

```
output/
├── _topology.json       # Phase 1: hardware-injected + VLAN-patched topology
└── final_topology.json  # Phase 2: complete topology with software configs
```

Both files follow the `GNS3Project` schema:

```json
{
  "name": "My Network",
  "topology": {
    "nodes": [
      {
        "node_id": "R1",
        "name": "R1-Edge",
        "node_type": "dynamips",
        "template_name": "c3745",
        "compute_id": "local",
        "properties": {
          "slot1": "NM-4E",
          "startup_config_content": "hostname R1\n!..."
        }
      }
    ],
    "links": [
      {
        "nodes": [
          {"node_id": "R1", "adapter_number": 0, "port_number": 0},
          {"node_id": "SW1", "adapter_number": 0, "port_number": 0}
        ],
        "link_type": "ethernet"
      }
    ]
  }
}
```

To deploy `final_topology.json` later or on another machine:

```bash
python assembler.py output/final_topology.json --host <GNS3_HOST> --port 3080
```

---

## Troubleshooting

**`ROUTER_API_KEY missing`**
Your `.env` file is missing or not being loaded. Make sure `.env` is in the project
root and contains `ROUTER_API_KEY=...`.

**`Cannot reach GNS3 at http://127.0.0.1:3080`**
GNS3 is not running or is on a different address. Start GNS3, then check
`GNS3_SERVER_URL` in your `.env`.

**`No templates found`**
GNS3 is running but has no appliance templates installed. Open GNS3, go to
*Edit → Preferences → Dynamips*, and add at least one IOS image, or install a
built-in appliance (VPCS is always available).

**`Pre-flight check failed: template 'c3745' not found in GNS3 inventory`**
The AI chose a template that isn't installed in your GNS3. Either install the missing
appliance or describe your network using the exact names of what you have installed:
`"Use only Switch, VPCS, and c7200"`.

**`AI generation failed after 3 attempts`**
The LLM is returning invalid JSON or a topology that fails validation. Try:
- A more explicit request: `"3 c3745 routers, 3 VPCS hosts, each PC on its own switch
  connected to one router"`
- Check your API key and model name in `.env`
- Run with `DEBUG` logging: set `logging.basicConfig(level=logging.DEBUG, ...)` in `main.py`

**`Phase 2 failed — falling back to Phase 1 topology`**
Software config generation failed. The topology is still deployed but without IOS
startup configs or VPCS scripts — devices will boot unconfigured. You can retry Phase 2
alone:
```bash
python config_agent.py output/_topology.json output/final_topology.json
```

**`Port collision` or `No available port` at deployment**
This is a port_assigner bug. Run with debug logging and open an issue with the
topology JSON and the error message.

**Links are deployed but inter-VLAN routing doesn't work**
Verify the switch `ports_mapping` in `final_topology.json`. Each access switch should
have exactly one `dot1q` trunk port (toward the router/core) and `access` ports for
hosts. If all ports show `access/vlan=1`, `topology_finalizer` did not recognise the
VLAN structure — check that your access switches are named `F1-SW`, `Admin-SW`, etc.
(names with a numeric suffix help VLAN auto-assignment).