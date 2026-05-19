"""
constants/ai.py — AI Pipeline Constants for Structranet AI

DYNAMIPS_MAX_LINKS recalculated after slot module corrections:

  Platform    builtin  slots  ports/slot  max_total  AI limit (conservative)
  ─────────────────────────────────────────────────────────────────────────
  c7200         1       6       8 (PA-8E)    49        keep 3  (PCI bus limit)
  c3745         2       4       1 (NM-1FE)    6        6
  c3725         2       2       1 (NM-1FE)    4        4   ← was wrong (6)
  c3660         2       6       4 (NM-4E)    26        8   (practical limit)
  c3640         0       4       4 (NM-4E)    16        6
  c3620         0       2       4 (NM-4E)     8        4
  c2691         2       1       1 (NM-1FE)    3        3   ← was wrong (6)
  c2600         1       1       1 (NM-1E)     2        2
  c1700         1       0       —             1        1   ← no NM slots

Note: c7200 limit is kept low (3) due to PCI bus contention, not port count.
      c3660/c3640 limits are conservative to avoid overloading the AI prompt.
"""
from typing import Dict, FrozenSet

MAX_RETRIES: int = 3

# Prompt-side conservative link limits — prevent impossible designs.
# Updated to match corrected hardware constants.
DYNAMIPS_MAX_LINKS: Dict[str, int] = {
    # c7200: 1 builtin + up to 48 PA ports — kept low due to PCI bus limit
    "c7200": 3,
    # c3745: 2 builtin + 4 slots × 1 port (NM-1FE-TX) = 6 max
    "c3745": 6,
    # c3725: 2 builtin + 2 slots × 1 port (NM-1FE-TX) = 4 max
    "c3725": 4,
    # c3660: 2 builtin + 6 slots × 4 ports (NM-4E) = 26 — cap at 8 for sanity
    "c3660": 8,
    # c3640: 0 builtin + 4 slots × 4 ports (NM-4E) = 16 — cap at 6
    "c3640": 6,
    # c3620: 0 builtin + 2 slots × 4 ports (NM-4E) = 8 — cap at 4
    "c3620": 4,
    # c2691: 2 builtin + 1 slot × 1 port (NM-1FE-TX) = 3 max
    "c2691": 3,
    # c2600: 1 builtin + 1 slot × 1 port (NM-1E) = 2 max
    "c2600": 2,
    # c1700: 1 builtin only — no NM slots
    "c1700": 1,
    # c3600 alias (covers c3620/c3640/c3660 when platform="c3600")
    "c3600": 8,
}

SINGLE_LINK_TYPES: FrozenSet[str] = frozenset({"vpcs", "traceng", "nat"})