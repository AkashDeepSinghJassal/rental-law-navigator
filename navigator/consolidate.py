"""A3 Consolidator + A4 Auditor -> a new knowledge-base version.

The consolidator may only GROUP verified candidates, LINK rules and report no-rule findings. Code rebuilds every
final rule from verified candidate data, so citations, dates, numbers and quotes can never be changed here.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from navigator import config, corpus, db, verify
from navigator.extract import STATE_CODES, verified_candidates
from navigator.llm import structured
from navigator.models import Category, CoverageOut

SOURCE_RANK = {"official": 0, "code_publisher": 1, "secondary": 2}
INSTRUMENT_RANK = {"statute": 0, "ordinance": 0, "regulation": 1, "ballot_measure": 1, "bill": 1, "agency_guidance": 2}


class GroupOut(BaseModel):
    member_idxs: list[int] = Field(description="candidate indexes describing the SAME legal rule")
    title: str
    requirement: str = Field(description="1-2 plain-language sentences combining the members")


class LinkOut(BaseModel):
    from_idx: int
    to_idx: int
    kind: Literal["supersedes", "narrow_exception", "may_conflict_with"]
    reason: str


class CoverageAuditOut(BaseModel):
    found_coverage: bool = Field(description="true only if the documents state which buildings the rule covers")
    coverage: CoverageOut


class NoRuleOut(BaseModel):
    category: Category
    finding: str
    doc_id: str | None
    quoted_span: str | None


class ConsolidationOut(BaseModel):
    groups: list[GroupOut]
    links: list[LinkOut]
    no_rule_findings: list[NoRuleOut]


class FieldCheck(BaseModel):
    field: Literal["requirement", "key_value", "effective_date", "coverage", "status"]
    verdict: Literal["supported", "contradicted", "not_stated"]
    note: str


class AuditOut(BaseModel):
    checks: list[FieldCheck]


CONSOLIDATE_SYSTEM = """You consolidate verified rental-housing rule candidates for ONE jurisdiction. You never \
invent law: you only group, link and report gaps, using the candidates given.

1. groups: put every EDITABLE candidate index in exactly one group. A group is one legal rule = one law \
(statute, ordinance, bill or ballot measure) in one category. Merge ALL candidates that come from the same law and \
category into ONE group, even when they describe different subsections, causes, exceptions, notices, penalties or \
figures, and even when they come from several documents (an agency page restating a statute belongs with that \
statute). Aim for one group per (law, category). Keep apart only genuinely different instruments: an enacted law vs \
a pending bill vs a failed ballot question, a state law vs a city ordinance, or two unrelated laws. Give each group \
a short title and a 1-2 sentence plain-language requirement a renter can act on (headline rule first, key number \
included), using only what the members say.
2. links: relations between rules, by candidate index (editable or context). "supersedes" means the from-rule \
governs the SAME subject instead of the to-rule wherever both cover a building (e.g. a local rent ordinance and a \
state rent cap that exempts units under local rent control). Use it only when the from-rule replaces the to-rule \
entirely for that subject. If the from-rule only carves out one narrow situation from a broader rule (e.g. a state \
section that sets relocation pay for stays under 20 days inside a broader local just-cause ordinance), use \
"narrow_exception" instead; it is shown as a note and does not override the broader rule. "may_conflict_with" means \
possible preemption or inconsistency that a human should review. Only link when a member's text supports it.
3. no_rule_findings: for each of the six categories with NO rule in this jurisdiction at this level, say so \
briefly. If a document states why (e.g. a state law bars local rent control), give its doc_id and a verbatim \
quote; else null.

Categories: rent_increase_limits, just_cause_eviction, security_deposits, application_screening_fees, \
screening_restrictions, algorithmic_rent_setting."""

AUDIT_SYSTEM = """You audit one extracted housing-law rule against excerpts of its source document (the document \
header, the passage around the quote, and the effective-date clause). For each field (requirement, key_value, \
effective_date, coverage, status) answer: supported (the excerpts say it), contradicted (the excerpts state \
something DIFFERENT, e.g. another number, date, or scope) or not_stated (the excerpts are silent or do not cover it). \
Absence of information is never "contradicted". A computed effective date is supported if the stated clause and \
approval date yield it. Be literal; quote the excerpt in the note."""


def _summary(c: dict) -> dict:
    keep = (
        "jurisdiction",
        "level",
        "category",
        "instrument",
        "enacted",
        "failed",
        "title",
        "requirement",
        "key_value",
        "effective_date",
        "citation",
        "interaction",
        "preemption_note",
        "source_doc_id",
    )
    out = {k: c.get(k) for k in keep}
    out["coverage"] = (c.get("coverage") or {}).get("applies_to")
    out["quote"] = (c.get("quoted_span") or "")[:400]
    return out


def _source_rank(c: dict) -> tuple:
    src = corpus.get_source(c["source_doc_id"])
    return (
        SOURCE_RANK.get(src.source_type, 3),
        INSTRUMENT_RANK.get(c.get("instrument"), 3),
        -len(c.get("quoted_span") or ""),
    )


def consolidate_jurisdiction(
    jur: str, context: list[dict], doc_ids: list[str] | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (final rules, links as (from_key,to_key,kind,reason), no-rule findings)."""
    cands = [c.data | {"_cid": c.id} for c in verified_candidates(jur) if doc_ids is None or c.doc_id in doc_ids]
    if not cands:
        return [], [], []
    payload = {
        "jurisdiction": jur,
        "editable_candidates": [{"idx": i, **_summary(c)} for i, c in enumerate(cands)],
        "context_rules_read_only": [{"idx": len(cands) + i, **_summary(r)} for i, r in enumerate(context)],
    }
    out, h = structured(
        "consolidate", CONSOLIDATE_SYSTEM, json.dumps(payload, indent=1), ConsolidationOut, ref=jur, max_tokens=32000
    )

    # groups: every candidate exactly once; strays become singleton groups
    seen, groups = set(), []
    for g in out.groups:
        members = [i for i in g.member_idxs if 0 <= i < len(cands) and i not in seen]
        if members:
            seen.update(members)
            groups.append((members, g.title, g.requirement))
    for i in range(len(cands)):
        if i not in seen:
            groups.append(([i], cands[i]["title"], cands[i]["requirement"]))

    idx_to_key, rules = {}, []
    for members, title, requirement in groups:
        # a group must not mix categories or enacted/pending; split if the model did
        by_kind: dict[tuple, list[int]] = {}
        for i in members:
            by_kind.setdefault((cands[i]["category"], cands[i]["enacted"], cands[i]["failed"]), []).append(i)
        for part in by_kind.values():
            primary = min(part, key=lambda i: _source_rank(cands[i]))
            rule = {k: v for k, v in cands[primary].items() if not k.startswith("_")}
            rule["quote_offsets"] = cands[primary]["_offsets"]
            if len(by_kind) == 1:
                rule["title"], rule["requirement"] = title, requirement
            rule["member_candidate_ids"] = [cands[i]["_cid"] for i in part]
            rule["member_docs"] = sorted({cands[i]["source_doc_id"] for i in part})
            # dates: prefer a verified date from any official member if the primary lacks one
            if not rule.get("effective_date"):
                dated = [
                    cands[i] for i in part if cands[i].get("effective_date") and cands[i].get("effective_date_span")
                ]
                if dated:
                    best = min(dated, key=_source_rank)
                    for f in ("effective_date", "effective_date_span", "effective_date_basis"):
                        rule[f] = best.get(f)
            for f in ("preemption_note", "interaction"):  # carry text notes from any member, best source first
                if not rule.get(f):
                    rule[f] = next(
                        (cands[i][f] for i in sorted(part, key=lambda i: _source_rank(cands[i])) if cands[i].get(f)),
                        None,
                    )
            dates = {cands[i].get("effective_date") for i in part if cands[i].get("effective_date")}
            if len(dates) > 1:
                rule["conflict_flag"] = True
                rule["conflict_note"] = f"Sources give different effective dates: {sorted(dates)}"
            key = f"{jur}|{rule['category']}|{rule['citation']}|{rule.get('effective_date')}|{primary}"
            rule["_key"] = key
            for i in part:
                idx_to_key[i] = key
            rules.append(rule)

    for i, r in enumerate(context):
        idx_to_key[len(cands) + i] = r["_key"]
    links = []
    for ln in out.links:
        a, b = idx_to_key.get(ln.from_idx), idx_to_key.get(ln.to_idx)
        if a and b and a != b:
            links.append({"from": a, "to": b, "kind": ln.kind, "reason": ln.reason})

    findings = []
    have = {r["category"] for r in rules}
    for f in out.no_rule_findings:
        if f.category in have:
            continue
        rec = {
            "jurisdiction": jur,
            "category": f.category,
            "finding": f.finding,
            "doc_id": None,
            "quoted_span": None,
            "evidence": "none",
        }
        if f.doc_id and f.quoted_span:
            src = corpus.get_source(f.doc_id)
            m = verify.find_span(src.body, f.quoted_span) if src and src.body else None
            if m:
                rec.update(doc_id=f.doc_id, quoted_span=m.text, evidence="quoted", source_url=src.url)
        findings.append(rec)
    db.audit("consolidate", "done", jur, groups=len(rules), links=len(links), no_rule=len(findings), call_hash=h)
    return rules, links, findings


def audit_rule(rule: dict) -> dict:
    src = corpus.get_source(rule["source_doc_id"])
    s, e = rule["quote_offsets"]["quoted_span"]
    passage = src.body[max(0, s - 1500) : e + 1500]
    extra = rule.get("effective_date_span") or ""
    payload = {
        k: rule.get(k)
        for k in (
            "title",
            "requirement",
            "key_value",
            "effective_date",
            "effective_date_basis",
            "instrument",
            "enacted",
            "failed",
            "citation",
        )
    }
    payload["coverage"] = rule.get("coverage")
    header = src.body[:1200] if s > 1200 else ""
    user = (
        f"<rule>{json.dumps(payload)}</rule>\n<document_header>{header}</document_header>\n"
        f"<passage>{passage}</passage>\n<date_clause>{extra}</date_clause>"
    )
    out, _ = structured("audit", AUDIT_SYSTEM, user, AuditOut, ref=rule["_key"], max_tokens=8000)
    bad = [c for c in out.checks if c.verdict == "contradicted"]
    rule["audit"] = [c.model_dump() for c in out.checks]
    if bad:
        rule["conflict_flag"] = True
        note = "; ".join(f"auditor: {c.field} contradicted ({c.note[:200]})" for c in bad)
        rule["conflict_note"] = f"{rule.get('conflict_note') or ''} {note}".strip()
        rule["confidence"] = max(0.0, (rule.get("confidence") or 0.8) - 0.3)
    return rule


COVERAGE_SYSTEM = """You read the full text of source documents about ONE housing rule and report which buildings the \
rule covers or exempts. Use only the documents given.
Return found_coverage=true only if the documents state coverage conditions for THIS rule's law (for example: only \
buildings first built or issued a certificate of occupancy before or after a date, a minimum or maximum number of \
units, a rolling age such as the last 15 years, owner-occupancy or owner-type exemptions). Fill min_units / max_units / \
built_before / built_after / cutoff_basis and the exemptions list only with what the text states: built_before means \
the rule covers buildings built or certified BEFORE (or on or before) that date. Copy coverage_span VERBATIM from the \
documents (one or two contiguous sentences, at least 20 characters). If nothing is stated, found_coverage=false and \
leave the fields empty or null. Never use outside knowledge."""

WORD_CAP_DOC, WORD_CAP_TOTAL = 12000, 40000


def _docs_for(rule: dict) -> list[tuple[str, str]]:
    """Member documents first, then other text sources for the same jurisdiction, within size caps."""
    from navigator import corpus as corp

    with db.session() as s:
        srcs = list(s.scalars(select(db.Source).where(db.Source.has_text)))
    members = rule.get("member_docs") or [rule["source_doc_id"]]
    pool = [x for x in srcs if x.doc_id in members] + [
        x for x in srcs if x.doc_id not in members and rule["jurisdiction"] in x.jurisdictions
    ]
    out, total = [], 0
    for x in pool:
        words = x.body.split()
        if len(words) > WORD_CAP_DOC:
            if x.doc_id not in members:
                continue
            q = (rule.get("quote_offsets") or {}).get("quoted_span")
            c = next(
                (c for c in corp.chunk_body(x.body) if q and c.start <= q[0] < c.start + len(c.text)),
                corp.chunk_body(x.body)[0],
            )
            text = c.text
        else:
            text = x.body
        w = len(text.split())
        if total + w > WORD_CAP_TOTAL:
            continue
        total += w
        out.append((x.doc_id, text))
    return out


def coverage_audit(rule: dict) -> dict:
    """Fill coverage conditions the first extraction left unstructured, from VERIFIED quotes only. Never removes."""
    docs = _docs_for(rule)
    payload = {k: rule.get(k) for k in ("title", "requirement", "citation", "jurisdiction", "category")}
    user = json.dumps(payload) + "\n" + "\n".join(f'<document doc_id="{d}">\n{t}\n</document>' for d, t in docs)
    try:
        out, _ = structured("coverage", COVERAGE_SYSTEM, user, CoverageAuditOut, ref=rule["_key"], max_tokens=16000)
    except Exception as e:  # one failed audit must not lose a long build; the rule keeps its original coverage
        db.audit("coverage", "error", rule["_key"], error=f"{type(e).__name__}: {e}"[:300])
        return rule
    new = out.coverage.model_dump(mode="json")
    span = new.get("coverage_span")
    hit = None
    if out.found_coverage and span:
        for d, _ in docs:
            body = corpus.get_source(d).body
            m = verify.find_span(body, span)
            if m:
                hit = (d, m)
                break
    if not hit:
        db.audit("coverage", "no_verified_coverage", rule["_key"])
        return rule
    cov = dict(rule.get("coverage") or {})
    added = []
    for k in ("min_units", "max_units", "built_before", "built_after"):
        if cov.get(k) is None and new.get(k) is not None:
            cov[k] = new[k]
            added.append(k)
    if (
        added
        and cov.get("cutoff_basis") in (None, "not_stated")
        and new.get("cutoff_basis") not in (None, "not_stated")
    ):
        cov["cutoff_basis"] = new["cutoff_basis"]
    have = " ".join(e["description"].lower() for e in cov.get("exemptions") or [])
    for e in new.get("exemptions") or []:
        key = e["description"].lower()[:40]
        if key and key not in have:
            cov.setdefault("exemptions", []).append(e)
            added.append("exemption")
    for f in new.get("requires_facts_not_in_data") or []:
        if f not in (cov.get("requires_facts_not_in_data") or []):
            cov.setdefault("requires_facts_not_in_data", []).append(f)
    if added:
        cov["coverage_span"] = hit[1].text
        cov["coverage_span_doc"] = hit[0]
        rule["coverage"] = cov
        rule["coverage_audited"] = {"added": added, "doc_id": hit[0]}
        db.audit("coverage", "added", rule["_key"], added=added, doc=hit[0])
    return rule


def _state_of(jur: str) -> str:
    return jur if jur in STATE_CODES else jur.split(",")[-1].strip()


def build_kb(audit: bool = True, note: str = "full build") -> dict:
    with db.session() as s:
        jurs = sorted({j for (j,) in s.execute(select(db.Candidate.jurisdiction).where(db.Candidate.verified))})
    states = [j for j in jurs if j in STATE_CODES]
    cities = [j for j in jurs if j not in STATE_CODES]

    all_rules, all_links, all_findings = [], [], []
    by_state: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=config.max_parallel()) as pool:
        for jur, (rules, links, findings) in zip(states, pool.map(lambda j: consolidate_jurisdiction(j, []), states)):
            by_state[jur] = rules
            all_rules += rules
            all_links += links
            all_findings += findings
        res = pool.map(lambda j: consolidate_jurisdiction(j, by_state.get(_state_of(j), [])), cities)
        for rules, links, findings in res:
            all_rules += rules
            all_links += links
            all_findings += findings
        all_rules = list(pool.map(coverage_audit, all_rules))
        if audit:
            all_rules = list(pool.map(audit_rule, all_rules))
    all_links += preemption_links(all_rules, all_links)
    return write_version(all_rules, all_links, all_findings, note=note)


PREEMPT_WORDS = ("preempt", "pre-empt", "supersede", "ordinance", "municipal", "local law")


def preemption_links(rules: list[dict], existing: list[dict]) -> list[dict]:
    """Generic, text-driven: a state rule whose extracted preemption note talks about local law may conflict with
    every local rule of the same category in that state. Flagged for human review, never resolved automatically."""
    have = {(ln["from"], ln["to"]) for ln in existing} | {(ln["to"], ln["from"]) for ln in existing}
    out = []
    for s in rules:
        note = (s.get("preemption_note") or "").lower()
        if s["level"] != "state" or not any(w in note for w in PREEMPT_WORDS):
            continue
        for c in rules:
            if (
                c["level"] == "city"
                and c["category"] == s["category"]
                and _state_of(c["jurisdiction"]) == s["jurisdiction"]
                and (s["_key"], c["_key"]) not in have
                and s.get("enacted")
                and c.get("enacted")
            ):
                out.append(
                    {
                        "from": s["_key"],
                        "to": c["_key"],
                        "kind": "may_conflict_with",
                        "reason": f"state rule notes: {s['preemption_note'][:160]}",
                    }
                )
    return out


def assign_ids(rules: list[dict]) -> None:
    """Stable ids: a deterministic sort for a fresh build; rules that already have an id keep it."""

    def sort_key(r):
        return (
            _state_of(r["jurisdiction"]),
            r["level"] != "state",
            r["jurisdiction"],
            r["category"],
            r["citation"],
            r.get("effective_date") or "",
            r["_key"],
        )

    taken = [int(r["team_rule_id"][2:]) for r in rules if r.get("team_rule_id")]
    nxt = max(taken, default=0) + 1
    for r in sorted((r for r in rules if not r.get("team_rule_id")), key=sort_key):
        r["team_rule_id"] = f"r-{nxt:04d}"
        nxt += 1


def write_version(
    rules: list[dict], links: list[dict], findings: list[dict], note: str, parent: int | None = None
) -> dict:
    assign_ids(rules)
    key_to_id = {r["_key"]: r["team_rule_id"] for r in rules}
    for r in rules:
        r.setdefault("supersedes", [])
        r.setdefault("superseded_by", [])
        r.setdefault("may_conflict_with", [])
    by_id = {r["team_rule_id"]: r for r in rules}
    for ln in links:
        a, b = key_to_id.get(ln["from"]), key_to_id.get(ln["to"])
        if not a or not b:
            continue
        if ln["kind"] == "narrow_exception":
            by_id[b]["interaction"] = (
                f"{by_id[b].get('interaction') or ''} Narrow exception: {by_id[a]['title']} "
                f"({a}) governs {ln['reason'][:160]}"
            ).strip()
        elif ln["kind"] == "supersedes":
            by_id[a]["supersedes"].append(b)
            by_id[b]["superseded_by"].append(a)
            by_id[b]["interaction"] = by_id[b].get("interaction") or f"Yields to {by_id[a]['title']} where it applies."
        else:
            for x, y in ((a, b), (b, a)):
                if y not in by_id[x]["may_conflict_with"]:
                    by_id[x]["may_conflict_with"].append(y)
                by_id[x]["conflict_flag"] = True
                by_id[x]["conflict_note"] = (
                    f"{by_id[x].get('conflict_note') or ''} Possible conflict with {y}: {ln['reason'][:200]}".strip()
                )
    for r in rules:
        r["links"] = (r.get("links") or []) + [ln for ln in links if ln["from"] == r["_key"] or ln["to"] == r["_key"]]
    with db.session() as s:
        prev = s.scalar(select(db.KBVersion.version).order_by(db.KBVersion.version.desc()).limit(1)) or 0
        version = prev + 1
        s.add(
            db.KBVersion(
                version=version,
                parent=parent if parent is not None else (prev or None),
                note=note,
                provider=config.llm_provider(),
                model=config.llm_model(),
                prompt_version=config.PROMPT_VERSION,
            )
        )
        for r in rules:
            s.add(
                db.Rule(
                    kb_version=version,
                    team_rule_id=r["team_rule_id"],
                    jurisdiction=r["jurisdiction"],
                    category=r["category"],
                    data=r,
                )
            )
        for f in findings:
            s.add(db.NoRuleFinding(kb_version=version, jurisdiction=f["jurisdiction"], category=f["category"], data=f))
    db.audit("kb", "version_written", str(version), rules=len(rules), links=len(links), no_rule=len(findings))
    return {"kb_version": version, "rules": len(rules), "links": len(links), "no_rule_findings": len(findings)}


def load_rules(version: int | None = None) -> list[dict]:
    version = version or db.latest_kb_version()
    with db.session() as s:
        return [
            r.data
            for r in s.scalars(select(db.Rule).where(db.Rule.kb_version == version).order_by(db.Rule.team_rule_id))
        ]


def load_findings(version: int | None = None) -> list[dict]:
    version = version or db.latest_kb_version()
    with db.session() as s:
        return [f.data for f in s.scalars(select(db.NoRuleFinding).where(db.NoRuleFinding.kb_version == version))]
