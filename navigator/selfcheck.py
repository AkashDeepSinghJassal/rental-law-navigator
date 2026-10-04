"""Self-check report (stand-in for the organizers' score.py, which is not in the starter pack)."""

from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import func, select

from navigator import DISCLAIMER, config, consolidate, corpus, db, geo, verify


def run() -> str:
    lines = [f"Rental Housing Law Navigator self-check. {DISCLAIMER}", ""]
    version = db.latest_kb_version()
    rules = consolidate.load_rules(version)
    findings = consolidate.load_findings(version)
    out = config.OUTPUT_DIR
    rj = json.loads((out / "rules.json").read_text())
    lk = json.loads((out / "lookups.json").read_text())
    ch = json.loads((out / "changes_detail.json").read_text())
    by_id = {r["team_rule_id"]: r for r in rules}

    lines.append(
        f"KB version {version}: {len(rules)} rules, {len(findings)} no-rule findings; "
        f"{len(rj['rules'])} exported (schema-valid)"
    )

    # 2. quote verification of every 'applies' answer
    applies = [(aid, x) for aid, lst in lk["lookups"].items() for x in lst if x["result"] == "applies"]
    ok = sec = 0
    for _, x in applies:
        r = by_id[x["team_rule_id"]]
        src = corpus.get_source(r["source_doc_id"])
        if src and src.body and verify.find_span(src.body, r["quoted_span"]) and src.in_corpus:
            ok += 1
        if r.get("secondary_source"):
            sec += 1
    pct = 100 * ok / max(1, len(applies))
    lines.append(
        f"Quotes: {ok}/{len(applies)} 'applies' answers ({pct:.1f}%) backed by a quote found verbatim in a "
        f"corpus file; {sec} rely on secondary sources"
    )

    # 3. coverage matrix
    lines += ["", "Coverage matrix (rule ids | 'none' = no-rule finding | '--' = gap):"]
    jurs = sorted(
        {r["jurisdiction"] for r in rules} | {f["jurisdiction"] for f in findings},
        key=lambda j: (j.split(",")[-1].strip(), "," in j, j),
    )
    for j in jurs:
        cells = []
        for c in config.CATEGORIES:
            ids = [r["team_rule_id"] for r in rules if r["jurisdiction"] == j and r["category"] == c]
            nr = any(f["jurisdiction"] == j and f["category"] == c for f in findings)
            cells.append(",".join(ids) if ids else ("none" if nr else "--"))
        lines.append(f"  {j:<18} " + " | ".join(f"{c[:4]}:{v}" for c, v in zip(config.CATEGORIES, cells)))

    # 4-5. result distribution per city and missing facts
    lines += ["", "Results per city at 2026-10-01:"]
    addrs = {a.address_id: a for a in geo.all_addresses()}
    per_city: dict[str, Counter] = {}
    missing = Counter()
    for aid, lst in lk["lookups"].items():
        city = (addrs[aid].stack or {}).get("city") or "(state only)"
        cnt = per_city.setdefault(city, Counter())
        for x in lst:
            cnt[x["result"]] += 1
    for city, cnt in sorted(per_city.items()):
        total = sum(cnt.values())
        flag = "  <-- review: >60% unknown" if cnt["unknown"] > 0.6 * total else ""
        lines.append(f"  {city:<18} {dict(cnt)}{flag}")
    detail = json.loads((out / "changes_detail.json").read_text())  # noqa: F841 (kept for symmetry)
    from navigator import evaluate

    for a in addrs.values():
        for x in evaluate.evaluate_address(a.stack or {}, a.facts, rules, config.AS_OF_DEFAULT):
            missing.update(x["missing_facts"])
    lines.append(f"Missing facts behind unknowns: {dict(missing)}")

    # 6. change tests
    lines += ["", "Change tests:"]
    ma = {aid for aid, a in addrs.items() if a.raw["state"] == "MA"}
    nj = {aid for aid, a in addrs.items() if a.raw["state"] == "NJ"}
    ca = {aid for aid, a in addrs.items() if a.raw["state"] == "CA"}
    city_of = {aid: (a.stack or {}).get("city") for aid, a in addrs.items()}
    checks = {
        "T1": lambda t: set(t["affected_address_ids"]) == ca,
        "T2": lambda t: (
            all(city_of[a] in ("Hoboken, NJ", "Jersey City, NJ") for a in t["affected_address_ids"])
            and any(city_of[a] == "Hoboken, NJ" for a in t["affected_address_ids"])
            and any(city_of[a] == "Jersey City, NJ" for a in t["affected_address_ids"])
        ),
        "T3": lambda t: (
            set(t["affected_address_ids"]) == nj
            and set(t["conflict_flag_address_ids"])
            == {a for a in nj if city_of[a] in ("Hoboken, NJ", "Jersey City, NJ")}
        ),
        "T4": lambda t: set(t["affected_address_ids"]) == ma,
        "T5": lambda t: t["affected_address_ids"] == [],
    }
    for tid, t in sorted(ch.items()):
        verdict = checks[tid](t) if tid in checks else None
        lines.append(
            f"  {tid}: {'PASS' if verdict else 'CHECK' if verdict is None else 'FAIL'} "
            f"affected={len(t['affected_address_ids'])} conflicts={len(t['conflict_flag_address_ids'])} "
            f"map={t.get('rule_map')}"
        )
    ma_caps = [
        x
        for aid in ma
        for x in lk["lookups"][aid]
        if by_id[x["team_rule_id"]]["category"] == "rent_increase_limits"
        and x["result"] == "applies"
        and by_id[x["team_rule_id"]]["level"] == "city"
    ]
    lines.append(f"  MA local rent caps reported as applies: {len(ma_caps)} (must be 0)")

    # 7. geocoding
    meth = Counter(a.stack.get("method") for a in addrs.values())
    differs = sum(
        1
        for a in addrs.values()
        if a.stack.get("city") and a.stack["city"].split(",")[0].lower() != a.raw["postal_city"].lower()
    )
    low = [a.address_id for a in addrs.values() if a.stack.get("confidence", 0) < 0.9]
    lines += ["", f"Geocoding: {dict(meth)}; postal city != legal city: {differs}; low confidence: {low}"]

    # 8. open questions
    lines += ["", "Known open questions (README section 9):"]
    for label, jur, cat in (
        ("Berkeley algorithmic ban dates", "Berkeley, CA", "algorithmic_rent_setting"),
        ("NJ FAIR Act vs local bans", "NJ", "algorithmic_rent_setting"),
        ("LA RSO formula dates", "Los Angeles, CA", "rent_increase_limits"),
        ("CA screening-fee cap figure", "CA", "application_screening_fees"),
    ):
        rs = [r for r in rules if r["jurisdiction"] == jur and r["category"] == cat]
        lines.append(
            f"  {label}: "
            + "; ".join(
                f"{r['team_rule_id']} eff={r.get('effective_date')} key={r.get('key_value')} conflict={bool(r.get('conflict_flag'))}"
                f"{' note=' + r['conflict_note'][:120] if r.get('conflict_note') else ''}"
                for r in rs
            )
            or "  (none)"
        )

    # 9. audit counts
    with db.session() as s:
        stages = dict(s.execute(select(db.LLMCall.stage, func.count()).group_by(db.LLMCall.stage)).all())
        usage = [u for (u,) in s.execute(select(db.LLMCall.usage))]
        decisions = dict(
            s.execute(
                select(db.AuditEvent.decision, func.count())
                .where(db.AuditEvent.stage == "verify")
                .group_by(db.AuditEvent.decision)
            ).all()
        )
        cands = s.scalar(select(func.count()).select_from(db.Candidate))
    tin = sum(u.get("input_tokens", 0) for u in usage)
    tout = sum(u.get("output_tokens", 0) for u in usage)
    lines += [
        "",
        f"LLM calls by stage: {stages}; tokens in/out: {tin}/{tout}",
        f"Candidates: {cands}; verification decisions: {decisions}",
        f"Provider/model of this KB: {config.llm_provider()} / {config.llm_model()}",
    ]
    text = "\n".join(lines) + "\n"
    text = text.replace(f"Provider/model of this KB: {config.llm_provider()} / {config.llm_model()}\n", "")
    with db.session() as s:
        built = [f"v{v.version}: {v.provider}/{v.model}" for v in s.scalars(select(db.KBVersion))]
    text += f"Knowledge base builds (provider/model): {'; '.join(built)}\n"
    (out / "selfcheck.txt").write_text(text)
    return text
