"""C1 Change tracker: T1-T5 from the starter pack, plus ingest-new for laws released mid-event (T6)."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from sqlalchemy import select

from navigator import config, consolidate, corpus, db, evaluate, extract, geo

PREFIX_JUR = {"CA": "CA", "NJ": "NJ", "MA": "MA", "HOB": "Hoboken, NJ", "JC": "Jersey City, NJ"}
CODE_CAT = {
    "ALG": "algorithmic_rent_setting",
    "RENT": "rent_increase_limits",
    "DEP": "security_deposits",
    "EVIC": "just_cause_eviction",
    "FEE": "application_screening_fees",
    "SCR": "screening_restrictions",
}


def load_tests() -> list[dict]:
    return json.loads(config.CHANGE_TESTS.read_text())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\d{3,}", text or ""))


def map_test_rule(test_rule_id: str, test: dict, rules: list[dict]) -> tuple[str | None, str]:
    """Map an answer-key rule id (e.g. 'CA-ALG-01', 'MA-ALG-P2') to one of our rules. Returns (id, reason)."""
    parts = test_rule_id.split("-")
    jur, cat = PREFIX_JUR.get(parts[0]), CODE_CAT.get(parts[1])
    proposed = parts[-1].startswith("P")
    pool = [
        r
        for r in rules
        if r["jurisdiction"] == jur
        and r["category"] == cat
        and (not r.get("enacted", True) or r.get("failed")) == proposed
    ]
    if not pool:
        return None, f"no {'proposed' if proposed else 'enacted'} {cat} rule for {jur} in the knowledge base"
    title_nums = sorted(_tokens(test["title"]), key=test["title"].find)
    if (
        proposed and len(title_nums) > 1 and parts[-1][1:].isdigit()
    ):  # P1 -> first bill number in the title, P2 -> second
        k = int(parts[-1][1:]) - 1
        title_nums = title_nums[k : k + 1] if k < len(title_nums) else title_nums
    want_failed = "struck" in test["title"].lower() or test.get("type") == "negative"

    def score(r):
        hay = f"{r['citation']} {r['title']}"
        return (len(_tokens(hay) & set(title_nums)), r.get("failed", False) == want_failed, -int(r["team_rule_id"][2:]))

    best = max(pool, key=score)
    return best["team_rule_id"], f"matched {jur} / {cat} / '{best['citation']}'"


def _results(rules, as_of):
    return evaluate.evaluate_all(rules, as_of)


def _by_rule(results: dict, rid: str) -> dict[str, dict]:
    return {aid: x for aid, lst in results.items() for x in lst if x["team_rule_id"] == rid}


def run_test(test: dict, rules: list[dict]) -> dict:
    mapping = {tr: map_test_rule(tr, test, rules) for tr in test["rule_ids"]}
    out = {"affected_address_ids": [], "conflict_flag_address_ids": [], "notes": "", "rule_map": {}}
    out["rule_map"] = {k: v[0] for k, v in mapping.items()}
    notes = [f"{k} -> {v[0]} ({v[1]})" for k, v in mapping.items()]
    ttype = test["type"]
    affected, conflicts, per_address = set(), set(), {}
    if ttype == "as_of":
        before = _results(rules, date.fromisoformat(test["as_of_before"]))
        after = _results(rules, date.fromisoformat(test["as_of_after"]))
        for rid in filter(None, out["rule_map"].values()):
            b, a = _by_rule(before, rid), _by_rule(after, rid)
            for aid in set(b) | set(a):
                rb, ra = b.get(aid, {}).get("result"), a.get(aid, {}).get("result")
                if rb != ra and ra in ("applies", "unknown", "superseded"):
                    affected.add(aid)
                    per_address[aid] = {"before": rb, "after": ra}
                if a.get(aid, {}).get("conflict_flag"):
                    conflicts.add(aid)
    else:
        res = _results(rules, date.fromisoformat(test.get("as_of", str(config.AS_OF_DEFAULT))))
        for rid in filter(None, out["rule_map"].values()):
            for aid, x in _by_rule(res, rid).items():
                if (
                    ttype == "boundary"
                    and x["result"] in ("applies", "unknown", "superseded")
                    or ttype == "pending"
                    and x["result"] == "pending"
                ):
                    affected.add(aid)
                elif ttype == "negative":
                    affected.add(aid)  # a failed measure must never show up: expected empty
                per_address[aid] = {"result": x["result"]}
                if x["conflict_flag"]:
                    conflicts.add(aid)
        if ttype == "boundary":
            cities = {}
            for a in geo.all_addresses():
                if a.address_id in affected:
                    cities[a.stack.get("city")] = cities.get(a.stack.get("city"), 0) + 1
            notes.append(f"affected by city: {cities}")
    out["affected_address_ids"] = sorted(affected)
    out["conflict_flag_address_ids"] = sorted(conflicts)
    out["per_address"] = per_address
    out["notes"] = f"{test['title']}. " + " | ".join(notes)
    return out


def run_all(rules: list[dict] | None = None) -> dict:
    rules = rules if rules is not None else consolidate.load_rules()
    results = {t["test_id"]: run_test(t, rules) for t in load_tests()}
    extra = config.OUTPUT_DIR / "new_law_tests.json"
    if extra.exists():
        results.update(json.loads(extra.read_text()))
    return results


def ingest_new(path: str, jurisdiction: str, url: str, retrieved: str | None = None, test_id: str = "T6") -> dict:
    """Extract a newly released law with the same agents, add it as a new KB version, report what changes."""
    text = Path(path).read_text(encoding="utf-8")
    body, header_ret = corpus.split_header(text)
    with db.session() as s:
        n = len(list(s.scalars(select(db.Source.doc_id).where(db.Source.doc_id.like("N%")))))
        doc_id = f"N{n + 1:03d}"
        s.merge(
            db.Source(
                doc_id=doc_id,
                jurisdictions=[jurisdiction],
                url=url,
                source_type="official",
                retrieved_at=retrieved or header_ret,
                sha256=None,
                has_text=True,
                in_corpus=False,
                body=body,
                word_count=len(body.split()),
            )
        )
    stats = extract.extract_doc(doc_id)
    old_version = db.latest_kb_version()
    old_rules = consolidate.load_rules(old_version)
    state = jurisdiction.split(",")[-1].strip()
    context = [r for r in old_rules if r["jurisdiction"] in (jurisdiction, state)]
    new_rules, links, findings = consolidate.consolidate_jurisdiction(jurisdiction, context, doc_ids=[doc_id])
    new_rules = [consolidate.audit_rule(consolidate.coverage_audit(r)) for r in new_rules]
    info = consolidate.write_version(
        old_rules + new_rules,
        links,
        consolidate.load_findings(old_version) + findings,
        note=f"ingest-new {doc_id} ({jurisdiction})",
        parent=old_version,
    )
    rules = consolidate.load_rules(info["kb_version"])
    new_ids = sorted(r["team_rule_id"] for r in rules if doc_id in (r.get("member_docs") or []))
    dates = sorted(
        {config.AS_OF_DEFAULT}
        | {
            evaluate.parse_partial(r["effective_date"])[0]
            for r in rules
            if r["team_rule_id"] in new_ids and r.get("effective_date")
        }
        | {
            d
            for r in rules
            if r["team_rule_id"] in new_ids and r.get("effective_date")
            for d in [evaluate.parse_partial(r["effective_date"])[1]]
        }
    )
    affected, per = set(), {}
    for d in dates:
        before, after = _results(old_rules, d), _results(rules, d)
        for aid in after:
            b = {x["team_rule_id"]: x["result"] for x in before[aid]}
            a = {x["team_rule_id"]: x["result"] for x in after[aid]}
            if a != b:
                affected.add(aid)
                per.setdefault(aid, {})[d.isoformat()] = {
                    "new_rules": {k: v for k, v in a.items() if k in new_ids},
                    "changed": {k: [b.get(k), a.get(k)] for k in set(a) | set(b) if a.get(k) != b.get(k)},
                }
    result = {
        test_id: {
            "affected_address_ids": sorted(affected),
            "conflict_flag_address_ids": sorted(
                aid
                for aid in affected
                for x in evaluate.evaluate_address(
                    geo.get_address(aid).stack, geo.get_address(aid).facts, rules, max(dates)
                )
                if x["conflict_flag"] and x["team_rule_id"] in new_ids
            ),
            "notes": f"New law {doc_id} ({jurisdiction}, {url}) -> rules {new_ids}; extracted {stats}; "
            f"checked dates {[d.isoformat() for d in dates]}; KB v{old_version} -> v{info['kb_version']}",
            "per_address": per,
        }
    }
    extra = config.OUTPUT_DIR / "new_law_tests.json"
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    existing = json.loads(extra.read_text()) if extra.exists() else {}
    existing.update(result)
    extra.write_text(json.dumps(existing, indent=2, sort_keys=True))
    return result
