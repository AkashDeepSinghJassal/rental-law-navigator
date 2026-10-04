"""B1 Facts normalizer: building facts from assessor rows. Derived facts are always tagged as derived.

Unit ranges come ONLY from what each dataset's own use-code description states (a data dictionary, not law).
"""

from __future__ import annotations

import re

ALWAYS_MISSING = ["owner_type", "certificate_of_occupancy", "owner_occupied"]


def _int(v: str | None) -> int | None:
    try:
        n = int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None
    return n if n and n > 0 else None


def units_range_from_use(dataset: str, use_code: str, desc: str) -> tuple[int | None, int | None, str] | None:
    """(min, max, basis) inferred from the use-code description, or None."""
    d = (desc or "").upper()
    if m := re.search(r"(\d+)\s*-\s*(\d+)[- ]UNIT", d) or re.search(r"(\d+) TO (\d+) UNITS", d):
        return int(m[1]), int(m[2]), f"use description '{desc}'"
    if m := re.search(r"APT (\d+)-(\d+) UNITS", d):
        return int(m[1]), int(m[2]), f"use description '{desc}'"
    if m := re.search(r">\s*(\d+)-UNIT", d):
        return int(m[1]) + 1, None, f"use description '{desc}'"
    if m := re.search(r"(\d+) UNITS OR MORE|(\d+)\+ UNITS", d):
        return int(m[1] or m[2]), None, f"use description '{desc}'"
    if "FIVE OR MORE" in d:
        return 5, None, f"use description '{desc}'"
    if m := re.search(r"(\d+) UNITS OR LESS", d):
        return None, int(m[1]), f"use description '{desc}'"
    if "NJOGIS" in dataset or "MOD-IV" in dataset:
        # MOD-IV building descriptions encode unit counts like '3S-B-A-13U-H' (13 units); '1OU' is a known O/0 typo
        nums = [int(x.replace("O", "0")) for x in re.findall(r"(?:^|[-/ B])(\d[\dO]*)U(?![A-Z])", d)]
        if nums:
            n = sum(nums)
            return n, n, f"MOD-IV building description '{desc}'"
        if use_code == "4C":
            # NJ property class 4C is 'apartment' (commercial residential, 5 or more units) in MOD-IV
            return 5, None, "NJ MOD-IV property class 4C (apartment, 5+ units)"
    return None


def building_facts(row: dict) -> dict:
    year = _int(row.get("year_built"))
    units = _int(row.get("units"))
    desc = row.get("use_description") or ""
    rng = None if units else units_range_from_use(row.get("source_dataset", ""), row.get("use_code", ""), desc)
    derived, notes = [], []
    if rng:
        derived.append("units")
        notes.append(f"units {rng[0] or '?'}-{rng[1] or '+'} derived from {rng[2]}")
    subsidized = True if "SUBSD" in desc.upper() or "AFFORDABL" in desc.upper() else None
    if subsidized:
        derived.append("subsidized")
        notes.append(f"subsidized housing per use description '{desc}'")
    missing = [f for f, v in (("year_built", year), ("units", units or rng)) if not v] + ALWAYS_MISSING
    if not subsidized:
        missing.append("subsidized")
    return {
        "year_built": year,
        "units": units,
        "units_min": rng[0] if rng else units,
        "units_max": rng[1] if rng else units,
        "use_code": row.get("use_code") or None,
        "use_description": desc or None,
        "subsidized": subsidized,
        "missing": missing,
        "derived": derived,
        "notes": notes,
    }
