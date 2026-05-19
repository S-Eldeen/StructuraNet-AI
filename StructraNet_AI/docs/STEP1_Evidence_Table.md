# STEP 1 — Evidence Table: Verified GNS3 Dynamips/IOU Hardware Constants

> **Source**: GNS3 2.2.x source code — `gns3-gui v2.2.59` and `gns3-server`
>
> **Purpose**: Canonical reference of all hardware constants verified against the
> official GNS3 source, with a "Current vs Correct" comparison identifying every
> error in the StructraNet AI codebase.
>
> **Date**: 2026-03-04

---

## Table of Contents

1. [RAM Defaults](#1-ram-defaults)
2. [NVRAM Defaults](#2-nvram-defaults)
3. [Module Lists](#3-module-lists)
4. [Slot Configuration](#4-slot-configuration)
5. [Module Port Counts](#5-module-port-counts)
6. [Built-in (Motherboard) Port Details](#6-built-in-motherboard-port-details)
7. [DYNAMIPS_MAX_PORTS Calculation](#7-dynamips_max_ports-calculation)
8. [IOU Constants](#8-iou-constants)
9. [Current vs Correct Comparison](#9-current-vs-correct-comparison)
10. [Code Duplication Inventory](#10-code-duplication-inventory)
11. [Structural / Architectural Issues](#11-structural--architectural-issues)

---

## 1. RAM Defaults

### 1.1 GUI Default RAM (PLATFORMS_DEFAULT_RAM)

Source: `gns3-gui/gns3/modules/dynamips/settings.py` — `PLATFORMS_DEFAULT_RAM`

| Platform | Default RAM (MB) |
|----------|-----------------|
| c1700    | 160             |
| c2600    | 160             |
| c2691    | 192             |
| c3600    | 192             |
| c3725    | 128             |
| c3745    | 256             |
| c7200    | 512             |

### 1.2 Server-Side Minimum RAM (Dynamips Hypervisor)

Source: `gns3-server` per-platform hypervisor minimums

| Platform | Min RAM (MB) |
|----------|-------------|
| c1700    | 64          |
| c2600    | 64          |
| c2691    | 128         |
| c3600    | 128         |
| c3725    | 128         |
| c3745    | 128         |
| c7200    | 256         |

### 1.3 CRITICAL FINDING: No Hardcoded RAM Ranges

GNS3's JSON template schema defines `ram` as `{"type": "integer"}` with **no
minimum/maximum bounds**. The only runtime enforcement is:

- The server rejects RAM below the hypervisor minimum for the platform.
- The GUI pre-fills `PLATFORMS_DEFAULT_RAM` as a convenience default.

**Conclusion**: The `ram_range` values in `DYNAMIPS_COMPAT` (validation.py) are
**advisory only** and are NOT sourced from the GNS3 codebase. They should not be
treated as hard limits.

---

## 2. NVRAM Defaults

Source: `gns3-gui/gns3/modules/dynamips/settings.py` — `PLATFORMS_DEFAULT_NVRAM`

| Platform | Default NVRAM (KB) |
|----------|-------------------|
| c1700    | 128               |
| c2600    | 128               |
| c2691    | 256               |
| c3600    | 256               |
| c3725    | 256               |
| c3745    | 256               |
| c7200    | 512               |

---

## 3. Module Lists

Source: `gns3-gui/gns3/modules/dynamips/settings.py`

### 3.1 C2600_NMS

Valid for: **c2600 slot 1 only**

| Module    | Type       | Ports |
|-----------|------------|-------|
| NM-1FE-TX | FastEthernet | 1   |
| NM-1E     | Ethernet   | 1     |
| NM-4E     | Ethernet   | 4     |
| NM-16ESW  | FastEthernet | 16  |

> **CRITICAL**: C2600_NMS does **NOT** include NM-4T (Serial). The c2600
> platform has no serial NM slots. Serial connectivity is only available via
> WIC subslots (WIC-1T, WIC-2T) on the motherboard, which are **NOT modeled**
> in our project.

### 3.2 C3600_NMS

Valid for: **c3620/c3640/c3660** configurable NM slots

| Module    | Type       | Ports |
|-----------|------------|-------|
| NM-1FE-TX | FastEthernet | 1   |
| NM-1E     | Ethernet   | 1     |
| NM-4E     | Ethernet   | 4     |
| NM-16ESW  | FastEthernet | 16  |
| NM-4T     | Serial     | 4     |

### 3.3 C3700_NMS

Valid for: **c3745/c3725/c2691** configurable NM slots

| Module    | Type       | Ports |
|-----------|------------|-------|
| NM-1FE-TX | FastEthernet | 1   |
| NM-4T     | Serial     | 4     |
| NM-16ESW  | FastEthernet | 16  |

> **CRITICAL**: C3700_NMS does **NOT** include NM-1E or NM-4E. These are
> C3600-only modules. Using them on c3745/c3725/c2691 will be rejected by
> the GNS3 server.

### 3.4 C7200_PAS (Port Adapters)

Valid for: **c7200** slots 1–6

| Module     | Type            | Ports |
|------------|-----------------|-------|
| PA-A1      | ATM             | 1     |
| PA-FE-TX   | FastEthernet    | 1     |
| PA-2FE-TX  | FastEthernet    | 2     |
| PA-GE      | GigabitEthernet | 1     |
| PA-4T+     | Serial          | 4     |
| PA-8T      | Serial          | 8     |
| PA-4E      | Ethernet        | 4     |
| PA-8E      | Ethernet        | 8     |
| PA-POS-OC3 | POS             | 1     |

### 3.5 IO_C7200 (I/O Controllers)

Valid for: **c7200** slot 0 only

| Module        | Type            | Ports |
|---------------|-----------------|-------|
| C7200-IO-FE   | FastEthernet    | 1     |
| C7200-IO-2FE  | FastEthernet    | 2     |
| C7200-IO-GE-E | GigabitEthernet | 1     |

### 3.6 CRITICAL: NM-1T Does NOT Exist

`NM-1T` appears in **no** GNS3 module list (C2600_NMS, C3600_NMS, C3700_NMS,
C7200_PAS, IO_C7200). It is also **absent** from the GNS3 server's
`ADAPTER_MATRIX`. Any code referencing NM-1T is generating invalid GNS3
topology data.

---

## 4. Slot Configuration

Source: `gns3-gui/gns3/modules/dynamips/settings.py` — `ADAPTER_MATRIX`

### 4.1 c1700

| Chassis  | Total Slots | Slot 0 (fixed)    | Slot 1 (fixed)      | Configurable NM Slots |
|----------|-------------|--------------------|----------------------|-----------------------|
| 1720/1721/1750 | 1    | C1700-MB-1FE (1FE) | —                    | **0**                 |
| 1751/1760     | 2    | C1700-MB-1FE (1FE) | C1700-MB-WIC1 (0 ports) | **0**              |

- Default chassis: 1760 (GUI template) or 1720 (server)
- `builtin_ifaces`: 1 (C1700-MB-1FE provides 1 FastEthernet)
- **NO NM expansion slots** — cannot accept any NM-xxx module

### 4.2 c2600

| Attribute | Value |
|-----------|-------|
| Total slots | 2 |
| Slot 0 | Chassis-dependent motherboard (fixed) |
| Slot 1 | C2600_NMS (configurable) |
| Configurable NM slots | **1** (slot 1 only) |

Motherboard options (slot 0):

| Motherboard    | Type       | Ports |
|----------------|------------|-------|
| C2600-MB-1E    | Ethernet   | 1     |
| C2600-MB-2E    | Ethernet   | 2     |
| C2600-MB-1FE   | FastEthernet | 1   |
| C2600-MB-2FE   | FastEthernet | 2   |

- Default chassis: 2651XM (GUI template, MB=C2600-MB-2FE) or 2610 (server, MB=C2600-MB-1E)
- `builtin_ifaces`: 1 (safe minimum; actual depends on chassis)
- **Serial**: C2600_NMS has NO serial modules. Serial only via WIC slots which are NOT modeled.

### 4.3 c2691

| Attribute | Value |
|-----------|-------|
| Total slots | 2 |
| Slot 0 | GT96100-FE (fixed, 2 FE) |
| Slot 1 | C3700_NMS (configurable) |
| Configurable NM slots | **1** |
| `builtin_ifaces` | 2 |

### 4.4 c3620

| Attribute | Value |
|-----------|-------|
| Total slots | 2 |
| Slot 0 | C3600_NMS (configurable) |
| Slot 1 | C3600_NMS (configurable) |
| Configurable NM slots | **2** (slots 0–1) |
| `builtin_ifaces` | 0 |
| Fixed motherboard | **None** |

### 4.5 c3640

| Attribute | Value |
|-----------|-------|
| Total slots | 4 |
| Slots 0–3 | C3600_NMS (all configurable) |
| Configurable NM slots | **4** (slots 0–3) |
| `builtin_ifaces` | 0 |
| Fixed motherboard | **None** |

### 4.6 c3660

| Attribute | Value |
|-----------|-------|
| Total slots | 7 |
| Slot 0 | Leopard-2FE (fixed, 2 FE) |
| Slots 1–6 | C3600_NMS (configurable) |
| Configurable NM slots | **6** (slots 1–6) |
| `builtin_ifaces` | 2 |

### 4.7 c3725

| Attribute | Value |
|-----------|-------|
| Total slots | 3 |
| Slot 0 | GT96100-FE (fixed, 2 FE) |
| Slots 1–2 | C3700_NMS (configurable) |
| Configurable NM slots | **2** (slots 1–2) |
| `builtin_ifaces` | 2 |

### 4.8 c3745

| Attribute | Value |
|-----------|-------|
| Total slots | 5 |
| Slot 0 | GT96100-FE (fixed, 2 FE) |
| Slots 1–4 | C3700_NMS (configurable) |
| Configurable NM slots | **4** (slots 1–4) |
| `builtin_ifaces` | 2 |

### 4.9 c7200

| Attribute | Value |
|-----------|-------|
| Total slots | 7 |
| Slot 0 | IO_C7200 (configurable I/O controller) |
| Slots 1–6 | C7200_PAS (configurable PA modules) |
| Configurable PA slots | **6** (slots 1–6) |
| Default I/O controller | C7200-IO-FE (1 FE) |
| `builtin_ifaces` | 0 (depends on I/O controller) |

For our pipeline's default (C7200-IO-FE): **1 FE port on adapter 0**.

### 4.10 c3600 (Alias)

GNS3 exports all c3620/c3640/c3660 with `platform="c3600"` and a `chassis`
field. In our codebase, the `c3600` key must be present to prevent lookups
from falling through to the fallback.

- Maps to c3660 spec (most capable): Leopard-2FE + 6 NM slots
- `builtin_ifaces`: 2
- Configurable NM slots: 6

---

## 5. Module Port Counts

Source: GNS3 server `ADAPTER_MATRIX` + Dynamips engine

### 5.1 Port Adapter (PA) Modules — c7200

| Module     | Interface Prefix  | Port Count |
|------------|-------------------|------------|
| PA-8E      | Ethernet          | 8          |
| PA-4E      | Ethernet          | 4          |
| PA-FE-TX   | FastEthernet      | 1          |
| PA-2FE-TX  | FastEthernet      | 2          |
| PA-GE      | GigabitEthernet   | 1          |
| PA-4T+     | Serial            | 4          |
| PA-8T      | Serial            | 8          |
| PA-A1      | ATM               | 1          |
| PA-POS-OC3 | POS               | 1          |

### 5.2 Network Module (NM) — c3600/c3700/c2600

| Module    | Interface Prefix  | Port Count |
|-----------|-------------------|------------|
| NM-4E     | Ethernet          | 4          |
| NM-1E     | Ethernet          | 1          |
| NM-1FE-TX | FastEthernet      | 1          |
| NM-16ESW  | FastEthernet      | 16         |
| NM-4T     | Serial            | 4          |

### 5.3 Motherboard / I/O Controllers

| Module        | Interface Prefix  | Port Count | Used By |
|---------------|-------------------|------------|---------|
| GT96100-FE    | FastEthernet      | 2          | c2691, c3725, c3745 slot 0 |
| Leopard-2FE   | FastEthernet      | 2          | c3660 slot 0 |
| C1700-MB-1FE  | FastEthernet      | 1          | c1700 slot 0 |
| C1700-MB-WIC1 | (none)            | 0          | c1751/1760 slot 1 (WIC carrier) |
| C2600-MB-1E   | Ethernet          | 1          | c2600 slot 0 |
| C2600-MB-2E   | Ethernet          | 2          | c2600 slot 0 |
| C2600-MB-1FE  | FastEthernet      | 1          | c2600 slot 0 |
| C2600-MB-2FE  | FastEthernet      | 2          | c2600 slot 0 |
| C7200-IO-FE   | FastEthernet      | 1          | c7200 slot 0 |
| C7200-IO-2FE  | FastEthernet      | 2          | c7200 slot 0 |
| C7200-IO-GE-E | GigabitEthernet   | 1          | c7200 slot 0 |

---

## 6. Built-in (Motherboard) Port Details

Source: GNS3 server `ADAPTER_MATRIX` + `builtin_ifaces` field

| Platform | Motherboard / Slot 0 Module | Built-in ETH Ports | Built-in SER Ports |
|----------|-----------------------------|--------------------|--------------------|
| c7200    | C7200-IO-FE (default)       | 1 (FE)             | 0                  |
| c3745    | GT96100-FE                  | 2 (FE)             | 0                  |
| c3725    | GT96100-FE                  | 2 (FE)             | 0                  |
| c3660    | Leopard-2FE                 | 2 (FE)             | 0                  |
| c3640    | (none — slot 0 configurable)| 0                  | 0                  |
| c3620    | (none — slot 0 configurable)| 0                  | 0                  |
| c2691    | GT96100-FE                  | 2 (FE)             | 0                  |
| c2600    | chassis-dependent           | 1 (safe min)       | 0                  |
| c1700    | C1700-MB-1FE                | 1 (FE)             | 0                  |
| c3600    | Leopard-2FE (alias)         | 2 (FE)             | 0                  |

---

## 7. DYNAMIPS_MAX_PORTS Calculation

### Formula

```
DYNAMIPS_MAX_PORTS = builtin_eth_ports
                   + (default_eth_module_ports_per_slot × configurable_nm_slots)
```

Where `default_eth_module_ports_per_slot` is the highest-port-count Ethernet
module available for that platform's NM/PA slots:

| Platform   | Default Eth Module | Ports/Module |
|------------|-------------------|--------------|
| c7200      | PA-8E             | 8            |
| c3745      | NM-1FE-TX         | 1            |
| c3725      | NM-1FE-TX         | 1            |
| c3660      | NM-4E             | 4            |
| c3640      | NM-4E             | 4            |
| c3620      | NM-4E             | 4            |
| c2691      | NM-1FE-TX         | 1            |
| c2600      | NM-1FE-TX*        | 1            |
| c1700      | N/A (no NM slots) | —            |

*\*c2600 uses C2600_NMS, which includes NM-1FE-TX (1 port) as the
highest-port-count Ethernet NM. NM-4E is also in C2600_NMS with 4 ports, so
the theoretical max for c2600 would be 1 + (4 × 1) = 5 if NM-4E is used.
The "default" expansion module our code picks is NM-1E (1 port), giving
1 + (1 × 1) = 2.*

### Computed Values

| Platform | builtin_eth | eth_module_ports | nm_slots | MAX_PORTS | Rounding Note |
|----------|-------------|------------------|----------|-----------|---------------|
| c7200    | 1           | 8 (PA-8E)        | 6        | **49**    |               |
| c3745    | 2           | 1 (NM-1FE-TX)    | 4        | **6**     |               |
| c3725    | 2           | 1 (NM-1FE-TX)    | 2        | **4**     |               |
| c3660    | 2           | 4 (NM-4E)        | 6        | **26**    |               |
| c3640    | 0           | 4 (NM-4E)        | 4        | **16**    |               |
| c3620    | 0           | 4 (NM-4E)        | 2        | **8**     |               |
| c2691    | 2           | 1 (NM-1FE-TX)    | 1        | **3**     |               |
| c2600    | 1           | 1 (NM-1E)        | 1        | **2**     | using default NM-1E |
| c1700    | 1           | N/A              | 0        | **1**     | no NM slots   |
| c3600    | 2           | 4 (NM-4E)        | 6        | **26**    | alias (=c3660)|

### Alternative: Maximum-Theoretical (using best module per slot)

| Platform | Best Eth Module | Ports/Module | nm_slots | MAX_THEORETICAL |
|----------|----------------|--------------|----------|-----------------|
| c7200    | PA-8E          | 8            | 6        | 49              |
| c3745    | NM-16ESW       | 16           | 4        | 66              |
| c3725    | NM-16ESW       | 16           | 2        | 34              |
| c3660    | NM-16ESW       | 16           | 6        | 98              |
| c3640    | NM-16ESW       | 16           | 4        | 64              |
| c3620    | NM-16ESW       | 16           | 2        | 32              |
| c2691    | NM-16ESW       | 16           | 1        | 18              |
| c2600    | NM-16ESW       | 16           | 1        | 17              |
| c1700    | N/A            | —            | 0        | 1               |

> **Design decision**: Our pipeline uses `default_eth_module_ports_per_slot`
> (the module we actually inject), NOT the maximum theoretical. This gives
> conservative, accurate MAX_PORTS values that match real topology output.

---

## 8. IOU Constants

Source: GNS3 server IOU template schema

| Constant               | Value |
|------------------------|-------|
| IOU_PORTS_PER_ADAPTER  | 4     |
| IOU_MAX_ADAPTERS        | 16    |
| Default eth adapters    | 2     |
| Default ser adapters    | 2     |

- Maximum Ethernet ports: 16 adapters × 4 ports = 64
- Maximum Serial ports: 16 adapters × 4 ports = 64
- IOU uses **flat adapter numbering**: Ethernet adapters 0..N-1, Serial
  adapters N..N+M-1 (where N = `ethernet_adapters`).

---

## 9. Current vs Correct Comparison

### 9.1 `_DYNAMIPS_MAX_PORTS` in `schema.py` (line 203)

| Platform | Current | Correct | Delta | Status |
|----------|---------|---------|-------|--------|
| c7200    | 3       | 49      | +46   | **WRONG** — massively under-counted |
| c3745    | 6       | 6       | 0     | Correct (coincidence) |
| c3725    | 6       | 4       | −2    | **WRONG** — over-counted |
| c3660    | 5       | 26      | +21   | **WRONG** — massively under-counted |
| c3640    | 4       | 16      | +12   | **WRONG** — under-counted |
| c3620    | 4       | 8       | +4    | **WRONG** — under-counted |
| c2691    | 6       | 3       | −3    | **WRONG** — over-counted |
| c2600    | 2       | 2       | 0     | Correct (coincidence) |
| c1700    | 2       | 1       | −1    | **WRONG** — over-counted |

**Impact**: The `link_count_must_not_exceed_max_ports` validator (schema.py
line 314) will either:
- **Reject valid topologies** (c7200: limits to 3 links, should allow 49)
- **Accept invalid topologies** (c3725: allows 6 links, max is 4; c2691: allows 6, max is 3)

### 9.2 `_DYNAMIPS_ADAPTER0_MAX_ETH_PORT` in `schema.py` (line 190)

| Platform | Current | Correct | Status |
|----------|---------|---------|--------|
| c7200    | 0       | 0       | Correct (slot 0 is IO controller, not "builtin") |
| c3745    | 1       | 1       | Correct (GT96100-FE: ports 0–1, so max port index = 1) |
| c3725    | 1       | 1       | Correct |
| c3660    | 1       | 1       | Correct (Leopard-2FE: ports 0–1) |
| c3640    | -1      | -1      | Correct (no fixed slot 0) |
| c3620    | -1      | -1      | Correct (no fixed slot 0) |
| c2691    | 1       | 1       | Correct |
| c2600    | 0       | 0       | Correct (1 FE, so max port index = 0) |
| c1700    | 0       | 0       | Correct (1 FE, so max port index = 0) |

> **Verdict**: `_DYNAMIPS_ADAPTER0_MAX_ETH_PORT` values are all correct.

### 9.3 NM-1T References (INVALID MODULE)

| File | Line | Current | Correct |
|------|------|---------|---------|
| constants/hardware.py | 101 | `DYNAMIPS_SERIAL_MODULES["c3620"]["module"] = "NM-1T"` | **NM-4T** (c3620 uses C3600_NMS which includes NM-4T) |
| constants/hardware.py | 103 | `DYNAMIPS_SERIAL_MODULES["c2600"]["module"] = "NM-1T"` | **No serial module** (C2600_NMS has no NM-4T; serial only via WIC) |
| constants/hardware.py | 104 | `DYNAMIPS_SERIAL_MODULES["c1700"]["module"] = "NM-1T"` | **No serial module** (c1700 has no NM slots at all) |
| constants/hardware.py | 165 | `DYNAMIPS_MODULE_INTERFACES["NM-1T"]` | **Delete entry** — module does not exist in GNS3 |
| context_builder.py | 50 | `DYNAMIPS_MODULE_INTERFACES["NM-1T"]` | **Delete entry** — duplicate of hardware.py, also invalid |
| gns3_exporter.py | 167 | `_DYN_MODULE["NM-1T"]` | **Delete entry** — duplicate, also invalid |

**Impact**: Any topology that injects NM-1T into a slot will produce an
**invalid .gns3project** — GNS3 will reject the module at import time or
fail to create the interface at runtime.

### 9.4 C2600 Serial Module Classification

| Item | Current Code | Correct |
|------|-------------|---------|
| c2600 serial module | NM-1T (1 port) | **None** — C2600_NMS has no serial NM |
| c2600 serial slots | 1 (slot 1) | **0** — slot 1 can only take C2600_NMS modules, none of which are serial |

**Impact**: `DYNAMIPS_SERIAL_MODULES["c2600"]` should either be removed or
have `max_slots: 0`. The current code will inject NM-1T into c2600 slot 1
for serial links, producing invalid topology.

### 9.5 C1700 Serial Module Classification

| Item | Current Code | Correct |
|------|-------------|---------|
| c1700 serial module | NM-1T (1 port) | **None** — no NM slots |
| c1700 serial slots | 0 (max_slots=0) | Correct (max_slots is already 0) |

**Impact**: Low — `max_slots=0` prevents injection, but the entry is
misleading and should be cleaned up.

### 9.6 DYNAMIPS_COMPAT `ram_range` Values

Source: `constants/validation.py` — `DYNAMIPS_COMPAT`

| Platform | Current `ram_range` | GNS3 Source | Status |
|----------|---------------------|-------------|--------|
| c7200    | (256, 1024)         | No bounds in schema | **Advisory only** |
| c3745    | (128, 512)          | No bounds in schema | **Advisory only** |
| c3725    | (128, 512)          | No bounds in schema | **Advisory only** |
| c3660    | (128, 512)          | No bounds in schema | **Advisory only** |
| c3640    | (128, 512)          | No bounds in schema | **Advisory only** |
| c3620    | (64, 256)           | No bounds in schema | **Advisory only** |
| c2691    | (128, 512)          | No bounds in schema | **Advisory only** |
| c2600    | (64, 256)           | No bounds in schema | **Advisory only** |
| c1700    | (128, 256)          | No bounds in schema | **Advisory only** |
| c3600    | (64, 512)           | No bounds in schema | **Advisory only** |

### 9.7 DYNAMIPS_COMPAT `builtin_ifaces` for c7200

| Item | Current | Correct | Source |
|------|---------|---------|--------|
| c7200 `builtin_ifaces` | 0 | 0 | Correct — GNS3 treats c7200 slot 0 as configurable I/O controller, not "builtin" |

> However, for our pipeline's **default** I/O controller (C7200-IO-FE), the
> effective built-in count is 1. The `builtin_ifaces: 0` in DYNAMIPS_COMPAT
> is technically correct per GNS3's internal model, but downstream code must
> account for the I/O controller providing 1 port on adapter 0.

### 9.8 c2600 Slot 0 in DYNAMIPS_COMPAT

| Item | Current | Correct |
|------|---------|---------|
| c2600 slot 0 | `_C3600_NMS` | Should be **motherboard list** (C2600-MB-1E, C2600-MB-2E, C2600-MB-1FE, C2600-MB-2FE) |

The current code lists C3600_NMS as valid for c2600 slot 0, implying that
NM modules like NM-4E can go in slot 0. In reality, slot 0 is the fixed
motherboard — you can only **choose** which motherboard chip, not install
an NM module.

---

## 10. Code Duplication Inventory

### 10.1 DYNAMIPS_MODULE_INTERFACES — Duplicated 4 Times

| File | Variable Name | Lines | Notes |
|------|---------------|-------|-------|
| constants/hardware.py | `DYNAMIPS_MODULE_INTERFACES` | 143–166 | **Canonical** — includes NM-1T (invalid) |
| context_builder.py | `DYNAMIPS_MODULE_INTERFACES` | 36–51 | **Duplicate** — also includes NM-1T |
| gns3_exporter.py | `_DYN_MODULE` | 142–168 | **Duplicate** — different name, also includes NM-1T |
| hw_config.py | `DYNAMIPS_SERIAL_MODULE_INTERFACES` | 72–76 | Derived subset (Serial only) — not a full duplicate |

**Risk**: Any correction to module data must be applied in 3+ places. The
context_builder.py and gns3_exporter.py copies are already out of sync with
constants/hardware.py (missing Leopard-2FE, C1700-MB-1FE, C7200-IO-* entries).

### 10.2 DYNAMIPS_BUILTIN_INTERFACE_DETAILS — Duplicated 3 Times

| File | Variable Name | Lines | Notes |
|------|---------------|-------|-------|
| constants/hardware.py | `DYNAMIPS_BUILTIN_INTERFACE_DETAILS` | 171–182 | **Canonical** — includes c3600 alias |
| context_builder.py | `DYNAMIPS_BUILTIN_INTERFACES` | 53–63 | **Duplicate** — missing c3600 alias |
| gns3_exporter.py | `_DYN_BUILTIN` | 125–137 | **Duplicate** — includes c3600 alias |

### 10.3 Hardware Defaults — Duplicated 2 Times

| File | Variable Name | Lines | Notes |
|------|---------------|-------|-------|
| constants/hardware.py | `DYNAMIPS_SLOT_MODULES` | 46–83 | **Canonical** — uses `module`, `ports_per_module`, `first_configurable`, `max_slots` |
| gns3_exporter.py | `_DYN_HW_DEFAULTS` | 170–215 | **Duplicate** — uses `ram`, `slot0`, `default_nm`, `max_slots` (different schema) |

### 10.4 DYNAMIPS_COMPAT — Wrong Home

| File | Lines | Issue |
|------|-------|-------|
| constants/validation.py | 94–231 | `DYNAMIPS_COMPAT` contains both validation data (slot compatibility) AND hardware defaults (ram_range). The hardware defaults portion should live in `constants/hardware.py`. |

---

## 11. Structural / Architectural Issues

### 11.1 Summary of All Code Errors

| # | Error | Severity | File(s) | Impact |
|---|-------|----------|---------|--------|
| 1 | `_DYNAMIPS_MAX_PORTS` values are wrong for 7 of 9 platforms | **HIGH** | schema.py:203 | Validator rejects valid topologies or accepts invalid ones |
| 2 | NM-1T referenced in 6 places but does not exist in GNS3 | **HIGH** | hardware.py, context_builder.py, gns3_exporter.py | Invalid .gns3project output |
| 3 | C2600_NMS not distinguished from C3600_NMS — NM-4T listed as valid serial for c2600 | **HIGH** | hardware.py:103 | GNS3 will reject NM-4T in c2600 |
| 4 | DYNAMIPS_MODULE_INTERFACES duplicated in 4 places | **MEDIUM** | hardware.py, context_builder.py, gns3_exporter.py, hw_config.py | Divergent copies; maintenance burden |
| 5 | DYNAMIPS_BUILTIN_INTERFACE_DETAILS duplicated in 3 places | **MEDIUM** | hardware.py, context_builder.py, gns3_exporter.py | Divergent copies |
| 6 | DYNAMIPS_COMPAT in validation.py contains hardware defaults that should be in hardware.py | **LOW** | validation.py | Architectural concern; no functional impact |
| 7 | gns3_exporter.py `_DYN_HW_DEFAULTS` uses different field names than `DYNAMIPS_SLOT_MODULES` | **LOW** | gns3_exporter.py | Confusing; two parallel schemas for same data |
| 8 | c2600 slot 0 in DYNAMIPS_COMPAT lists C3600_NMS instead of motherboard list | **MEDIUM** | validation.py:196 | Pre-export validator may accept invalid c2600 slot 0 modules |
| 9 | context_builder.py duplicate DYNAMIPS_BUILTIN_INTERFACES missing c3600 alias | **LOW** | context_builder.py:53 | Port name resolution fails for platform="c3600" |

### 11.2 Recommended Fix Priority

1. **P0 (Blocker)**: Fix `_DYNAMIPS_MAX_PORTS` in schema.py — directly affects
   topology validation and will cause deployment failures.
2. **P0 (Blocker)**: Remove all NM-1T references — produces invalid GNS3 output.
3. **P1 (High)**: Fix c2600 serial module — C2600_NMS has no serial NM; serial
   links on c2600 are not possible via NM slots.
4. **P1 (High)**: Fix c2600 slot 0 in DYNAMIPS_COMPAT — use motherboard list
   instead of C3600_NMS.
5. **P2 (Medium)**: Deduplicate DYNAMIPS_MODULE_INTERFACES — make
   context_builder.py and gns3_exporter.py import from constants/hardware.py.
6. **P2 (Medium)**: Deduplicate DYNAMIPS_BUILTIN_INTERFACE_DETAILS — same.
7. **P3 (Low)**: Move DYNAMIPS_COMPAT hardware defaults to hardware.py.
8. **P3 (Low)**: Align _DYN_HW_DEFAULTS field names with DYNAMIPS_SLOT_MODULES.

---

## Appendix A: Complete Verified Constants (Copy-Ready)

### A.1 Correct _DYNAMIPS_MAX_PORTS

```python
_DYNAMIPS_MAX_PORTS: ClassVar[dict[str, int]] = {
    "c7200": 49, "c3745": 6, "c3725": 4, "c3660": 26,
    "c3640": 16, "c3620": 8, "c2691": 3, "c2600": 2, "c1700": 1,
    "c3600": 26,
}
```

### A.2 Correct DYNAMIPS_SERIAL_MODULES (without NM-1T)

```python
DYNAMIPS_SERIAL_MODULES: Dict[str, Dict[str, Any]] = {
    "c7200":  {"module": "PA-4T+",  "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3745":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3725":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 2},
    "c3660":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3640":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 0, "max_slots": 4},
    "c3620":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 0, "max_slots": 2},
    "c2691":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 1},
    # c2600: NO serial NM (C2600_NMS has no serial modules; serial only via WIC)
    # c1700: NO NM slots at all
    "c3600":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
}
```

### A.3 Correct DYNAMIPS_MODULE_INTERFACES (without NM-1T)

```python
DYNAMIPS_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    "PA-8E":          {"prefix": "Ethernet",        "count": 8},
    "PA-4E":          {"prefix": "Ethernet",        "count": 4},
    "PA-FE-TX":       {"prefix": "FastEthernet",    "count": 1},
    "PA-2FE-TX":      {"prefix": "FastEthernet",    "count": 2},
    "PA-GE":          {"prefix": "GigabitEthernet", "count": 1},
    "NM-4E":          {"prefix": "Ethernet",        "count": 4},
    "NM-1E":          {"prefix": "Ethernet",        "count": 1},
    "NM-1FE-TX":      {"prefix": "FastEthernet",    "count": 1},
    "NM-16ESW":       {"prefix": "FastEthernet",    "count": 16},
    "NM-4T":          {"prefix": "Serial",          "count": 4},
    "GT96100-FE":     {"prefix": "FastEthernet",    "count": 2},
    "Leopard-2FE":    {"prefix": "FastEthernet",    "count": 2},
    "C7200-IO-FE":    {"prefix": "FastEthernet",    "count": 1},
    "C7200-IO-2FE":   {"prefix": "FastEthernet",    "count": 2},
    "C7200-IO-GE-E":  {"prefix": "GigabitEthernet", "count": 1},
    "C1700-MB-1FE":   {"prefix": "FastEthernet",    "count": 1},
    "PA-4T+":         {"prefix": "Serial",          "count": 4},
    "PA-8T":          {"prefix": "Serial",          "count": 8},
    "PA-A1":          {"prefix": "ATM",             "count": 1},
    "PA-POS-OC3":     {"prefix": "POS",             "count": 1},
    "C2600-MB-1E":    {"prefix": "Ethernet",        "count": 1},
    "C2600-MB-2E":    {"prefix": "Ethernet",        "count": 2},
    "C2600-MB-1FE":   {"prefix": "FastEthernet",    "count": 1},
    "C2600-MB-2FE":   {"prefix": "FastEthernet",    "count": 2},
}
# NOTE: NM-1T is deliberately absent — it does not exist in GNS3.
```

---

*End of Evidence Table*
