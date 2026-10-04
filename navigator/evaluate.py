"""B3 Evaluator: deterministic, three-valued (True / False / None=unknown). No LLM at query time.

Order: time -> coverage -> precedence -> conflicts. A rule whose coverage is unknown is reported as `unknown`
with the missing facts named; it is never silently dropped.
"""

from __future__ import annotations

import calendar
from datetime import date

from navigator import DISCLAIMER, config, db

UNKNOWABLE = {"owner_type", "certificate_of_occupancy", "owner_occupied", "new_construction_filing"}
IGNORED_FACTS = {"tenant_status", "other"}  # lookups are per building, not per tenant
FACT_LABEL = {
    "year_built": "year built", "units": "number of units", "owner_type": "owner type",
    "certificate_of_occupancy": "certificate-of-occupancy date", "owner_occupied": "whether the owner lives there",
    "new_construction_filing": "new-construction exemption filing", "subsidized": "whether the unit is subsidized",
}  # fmt: skip


def parse_partial(d: str | None) -> tuple[date, date] | None:
    if not d:
        return None
    parts = [int(p) for p in d.split("-")]
    if len(parts) == 1:
        return date(parts[0], 1, 1), date(parts[0], 12, 31)
    if len(parts) == 2:
        return date(parts[0], parts[1], 1), date(parts[0], parts[1], calendar.monthrange(parts[0], parts[1])[1])
    return date(*parts), date(*parts)


def time_status(rule: dict, as_of: date) -> str:
    """failed | pending | not_yet_effective | ambiguous | expired | in_force"""
    if rule.get("failed"):
        return "failed"
    if not rule.get("enacted", True):
        return "pending"
    win = parse_partial(rule.get("effective_date"))
    if win:
        if as_of < win[0]:
            return "not_yet_effective"
        if win[0] != win[1] and as_of <= win[1]:
            return "ambiguous"
    sun = parse_partial(rule.get("sunset_date"))
    if sun and as_of > sun[1]:
        return "expired"
    return "in_force"


def _year_cmp(year: int | None, cutoff: str, basis: str | None) -> bool | None:
    """True if built before cutoff, False if not, None if unknowable."""
    cut = parse_partial(cutoff)
    if cut is None or year is None:
        return None
    c = cut[0]
    if year < c.year:
        return True
    if year > c.year:
        return False
    if c.month == 1 and c.day == 1 and basis == "year_built":
        return False  # built during the cutoff year is not before Jan 1 of it
    return None  # same year: certificate-of-occupancy date unknown


def _units(f: dict, min_u: int | None, max_u: int | None) -> bool | None:
    lo, hi = f.get("units_min"), f.get("units_max")
    res = True
    if min_u is not None:
        if lo is not None and lo >= min_u:
            pass
        elif hi is not None and hi < min_u:
            return False
        else:
            res = None
    if max_u is not None:
        if hi is not None and hi <= max_u:
            pass
        elif lo is not None and lo > max_u:
            return False
        else:
            res = None
    return res


def _and(vals):
    if any(v is False for v in vals):
        return False
    return None if any(v is None for v in vals) else True


def exemption_applies(ex: dict, f: dict, as_of: date) -> tuple[bool | None, list[str]]:
    """True = exempt, False = ruled out, None = can't tell (with missing facts)."""
    conds, missing = [], []
    if ex.get("max_units") is not None or ex.get("min_units") is not None:
        v = _units(f, ex.get("min_units"), ex.get("max_units"))
        conds.append(v)
        if v is None:
            missing.append("units")
    if ex.get("built_after"):
        b = _year_cmp(f.get("year_built"), ex["built_after"], "certificate_of_occupancy")
        v = None if b is None else (not b)
        conds.append(v)
        if v is None:
            missing.append("year_built" if f.get("year_built") is None else "certificate_of_occupancy")
    if ex.get("newer_than_years"):
        y = f.get("year_built")
        if y is None:
            conds.append(None)
            missing.append("year_built")
        else:
            age = as_of.year - y
            n = ex["newer_than_years"]
            conds.append(True if age < n else False if age > n else None)
            if age == n:
                missing.append("certificate_of_occupancy")
    for fact in ex.get("depends_on") or []:
        if fact in IGNORED_FACTS:
            continue
        if fact in ("year_built", "units"):
            continue  # handled by the structured bounds above
        val = f.get(fact)
        if val is False:
            conds.append(False)  # known not to be the case: this exemption is ruled out
        elif val is True and fact in (f.get("user_supplied") or []):
            conds.append(True)  # stated by the person asking
        else:
            # unknown, or only inferred from a land-use code: an inference must not silently remove a rule
            conds.append(None)
            missing.append(fact)
    if not conds:
        return False, []  # free-text exemption with no checkable condition: noted, not evaluated
    return _and(conds), missing


def coverage(rule: dict, f: dict, as_of: date) -> tuple[bool | None, list[str], list[str]]:
    """(covered, missing facts, reasons)"""
    cov = rule.get("coverage") or {}
    vals, missing, reasons = [], [], []
    if cov.get("min_units") is not None or cov.get("max_units") is not None:
        v = _units(f, cov.get("min_units"), cov.get("max_units"))
        vals.append(v)
        if v is None:
            missing.append("units")
        else:
            reasons.append(f"unit-count condition {'met' if v else 'not met'}")
    for key, before in (("built_before", True), ("built_after", False)):
        if cov.get(key):
            b = _year_cmp(f.get("year_built"), cov[key], cov.get("cutoff_basis"))
            v = None if b is None else (b if before else not b)
            vals.append(v)
            if v is None:
                missing.append("year_built" if f.get("year_built") is None else "certificate_of_occupancy")
            else:
                reasons.append(f"built {'before' if before else 'after'} {cov[key]}: {'yes' if v else 'no'}")
    cutoff_decided = any(
        _year_cmp(f.get("year_built"), cov[k], cov.get("cutoff_basis")) is not None
        for k in ("built_before", "built_after")
        if cov.get(k)
    )
    for fact in cov.get("requires_facts_not_in_data") or []:
        if fact in IGNORED_FACTS or fact in ("year_built", "units"):
            continue
        if fact == "certificate_of_occupancy" and cutoff_decided:
            continue  # the year already decides the cutoff; the exact certificate date is not needed
        if isinstance(f.get(fact), bool) and fact in (f.get("user_supplied") or []):
            continue
        vals.append(None)
        missing.append(fact)
    covered = _and(vals) if vals else True
    if covered is not False:
        ex_unknown = []
        for ex in cov.get("exemptions") or []:
            e, m = exemption_applies(ex, f, as_of)
            if e is True:
                return False, [], [f"exempt: {ex.get('description')}"]
            if e is None:
                ex_unknown.append(ex.get("description"))
                missing += m
        if ex_unknown and covered:
            covered = None
            reasons.append("exemption may apply: " + "; ".join(x for x in ex_unknown if x))
    return covered, sorted(set(missing)), reasons


def _facts_phrase(missing: list[str]) -> str:
    return ", ".join(FACT_LABEL.get(m, m) for m in missing) or "a fact not in the data"


def evaluate_address(stack: dict, f: dict, rules: list[dict], as_of: date) -> list[dict]:
    jurs = {stack.get("state"), stack.get("city")} - {None}
    prelim: dict[str, dict] = {}
    for r in rules:
        if r["jurisdiction"] not in jurs:
            continue
        t = time_status(r, as_of)
        if t in ("failed", "expired"):
            continue
        cov, missing, reasons = coverage(r, f, as_of)
        if cov is False:
            continue
        where = r["jurisdiction"]
        if t == "pending":
            res, why = (
                "pending",
                f"Proposed, not law: {r['title']} ({r['citation']}) would cover this {where} address if enacted.",
            )
        elif t == "not_yet_effective":
            res, why = (
                "not_yet_effective",
                f"Enacted but takes effect {r['effective_date']}, after {as_of.isoformat()}.",
            )
        elif t == "ambiguous":
            res, why = (
                "unknown",
                f"Effective date known only as {r['effective_date']}; it may or may not be in force on {as_of.isoformat()}.",
            )
        elif cov is None:
            res, why = "unknown", f"Coverage depends on {_facts_phrase(missing)}, which the data does not include."
        else:
            res = "applies"
            why = f"In force for this {where} address" + (f" ({'; '.join(reasons)})" if reasons else "") + "."
        prelim[r["team_rule_id"]] = {"rule": r, "result": res, "explanation": why, "missing_facts": missing}

    # precedence: a covered rule yields to a superseding rule that applies (or might apply) here
    for rid, p in prelim.items():
        if p["result"] not in ("applies", "unknown"):
            continue
        for sup in p["rule"].get("superseded_by") or []:
            q = prelim.get(sup)
            if not q:
                continue
            if q["result"] == "applies":
                was_unknown = p["result"] == "unknown"
                p["result"] = "superseded"
                p["explanation"] = f"{q['rule']['title']} ({sup}) governs here instead" + (
                    ", whether or not this rule would otherwise cover the building." if was_unknown else "."
                )
                break
            if q["result"] == "unknown" and p["result"] == "applies":
                p["result"] = "unknown"
                p["explanation"] = f"Superseded if {q['rule']['title']} ({sup}) covers this building; that is unknown."
                p["missing_facts"] = sorted(set(p["missing_facts"]) | set(q["missing_facts"]))

    out = []
    for rid in sorted(prelim):
        p = prelim[rid]
        r = p["rule"]
        partners = [x for x in r.get("may_conflict_with") or [] if x in prelim]
        conflict = bool(partners) or bool(r.get("conflict_flag") and not r.get("may_conflict_with"))
        expl = p["explanation"]
        if partners:
            expl += f" Possible conflict with {', '.join(partners)}: flagged for human review."
        out.append(
            {
                "team_rule_id": rid,
                "result": p["result"],
                "explanation": expl,
                "conflict_flag": conflict,
                "missing_facts": p["missing_facts"],
            }
        )
    return out


def evaluate_all(rules: list[dict], as_of: date, addresses=None) -> dict[str, list[dict]]:
    from navigator import geo

    addresses = addresses if addresses is not None else geo.all_addresses()
    return {a.address_id: evaluate_address(a.stack or {}, a.facts, rules, as_of) for a in addresses}


def lookup_address(
    address_id: str,
    as_of: date = config.AS_OF_DEFAULT,
    kb_version: int | None = None,
    facts_override: dict | None = None,
) -> dict:
    from navigator import geo

    a = geo.get_address(address_id)
    if a is None:
        raise KeyError(address_id)
    return describe(a.stack or {}, dict(a.facts), a.raw, address_id, as_of, kb_version, facts_override)


def describe(
    stack: dict,
    f: dict,
    raw: dict,
    address_id: str | None,
    as_of: date,
    kb_version: int | None = None,
    facts_override: dict | None = None,
) -> dict:
    from navigator import consolidate

    if facts_override:
        for k, v in facts_override.items():
            if v in (None, ""):
                continue
            f[k] = v
            if k == "units":
                f["units_min"] = f["units_max"] = int(v)
            f["missing"] = [m for m in f.get("missing", []) if m != k]
            f.setdefault("user_supplied", []).append(k)
    rules = consolidate.load_rules(kb_version)
    by_id = {r["team_rule_id"]: r for r in rules}
    results = evaluate_address(stack, f, rules, as_of)
    for res in results:
        r = by_id[res["team_rule_id"]]
        res["rule"] = {
            k: r.get(k)
            for k in (
                "title",
                "jurisdiction",
                "level",
                "category",
                "requirement",
                "key_value",
                "citation",
                "quoted_span",
                "quote_offsets",
                "source_doc_id",
                "member_docs",
                "effective_date",
                "effective_date_span",
                "confidence",
                "conflict_note",
                "secondary_source",
                "instrument",
                "enacted",
                "interaction",
            )
        }
    return {
        "address_id": address_id,
        "as_of": as_of.isoformat(),
        "address": raw,
        "stack": stack,
        "facts": f,
        "results": results,
        "kb_version": kb_version or db.latest_kb_version(),
        "disclaimer": DISCLAIMER,
    }
