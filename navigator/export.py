"""Write the three submission files, validated against the starter-pack schema."""

from __future__ import annotations

import json

import jsonschema

from navigator import changes, config, consolidate, corpus, evaluate, geo

STATUS = {
    "in_force": "in_force",
    "ambiguous": "in_force",
    "not_yet_effective": "not_yet_effective",
    "pending": "pending",
    "failed": "failed",
    "expired": "failed",
}


def to_record(r: dict) -> dict:
    src = corpus.get_source(r["source_doc_id"])
    cov = dict(r.get("coverage") or {})
    exemptions = "; ".join(e["description"] for e in cov.get("exemptions") or []) or None
    rec = {
        "team_rule_id": r["team_rule_id"],
        "jurisdiction": r["jurisdiction"],
        "level": r["level"],
        "category": r["category"],
        "status": STATUS[evaluate.time_status(r, config.AS_OF_DEFAULT)],
        "title": r["title"],
        "requirement": r["requirement"],
        "key_value": r.get("key_value"),
        "coverage_conditions": cov or None,
        "exemptions": exemptions,
        "overrides": sorted(set((r.get("supersedes") or []) + (r.get("superseded_by") or []))),
        "interaction": r.get("interaction"),
        "effective_date": r.get("effective_date"),
        "citation": r["citation"],
        "source_doc_id": r["source_doc_id"],
        "source_url": src.url if src else None,
        "quoted_span": r["quoted_span"],
        "confidence": r.get("confidence"),
        "conflict_flag": bool(r.get("conflict_flag")),
        "conflict_note": r.get("conflict_note"),
        # extra provenance (allowed by the schema)
        "retrieved_at": src.retrieved_at if src else None,
        "effective_date_span": r.get("effective_date_span"),
        "effective_date_basis": r.get("effective_date_basis"),
        "secondary_source": bool(r.get("secondary_source")),
        "instrument": r.get("instrument"),
        "member_docs": r.get("member_docs"),
    }
    return rec


def export_all(version: int | None = None) -> dict:
    rules = consolidate.load_rules(version)
    schema = json.loads(config.RULE_SCHEMA.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    records, invalid = [], []
    for r in rules:
        rec = to_record(r)
        errs = list(validator.iter_errors(rec))
        if errs:
            invalid.append({"team_rule_id": r["team_rule_id"], "errors": [e.message for e in errs][:5]})
            continue
        records.append(rec)
    config.OUTPUT_DIR.mkdir(exist_ok=True)

    def dump(name, obj):
        (config.OUTPUT_DIR / name).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    dump("rules.json", {"rules": records, "no_rule_findings": consolidate.load_findings(version)})
    results = evaluate.evaluate_all(rules, config.AS_OF_DEFAULT)
    lookups = {
        aid: [{k: x[k] for k in ("team_rule_id", "result", "explanation", "conflict_flag")} for x in lst]
        for aid, lst in sorted(results.items())
    }
    dump("lookups.json", {"as_of": config.AS_OF_DEFAULT.isoformat(), "lookups": lookups})
    ch = changes.run_all(rules)
    dump(
        "changes.json",
        {
            k: {kk: v[kk] for kk in ("affected_address_ids", "conflict_flag_address_ids", "notes")}
            for k, v in ch.items()
        },
    )
    dump("changes_detail.json", ch)
    return {
        "rules": len(records),
        "invalid": invalid,
        "addresses": len(lookups),
        "tests": sorted(ch),
        "geo_addresses": len(geo.all_addresses()),
    }
