"""A1 Extractor (LLM) + A2 verification with one repair round. Results land in the `candidates` table."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import delete, select

from navigator import config, corpus, db, prompts, verify
from navigator.llm import structured
from navigator.models import ExtractionOut, RepairOut

STATE_CODES = {"CA", "NJ", "MA"}


def allowed_jurisdictions(src_jurisdictions: list[str]) -> list[str]:
    """A city document may restate its state's law, so the state code is allowed too."""
    allowed = list(src_jurisdictions)
    for j in src_jurisdictions:
        st = j.split(",")[-1].strip()
        if st in STATE_CODES and st not in allowed:
            allowed.append(st)
    return allowed


def _value_for(cand: dict, path: str) -> str:
    return {
        "quoted_span": cand.get("requirement"),
        "effective_date_span": f"effective date {cand.get('effective_date')}",
        "key_value_span": cand.get("key_value"),
        "coverage.coverage_span": (cand.get("coverage") or {}).get("applies_to"),
    }.get(path) or ""


def _repair(cand: dict, failed: list[str], body: str, ref: str) -> tuple[dict, list[str], list[dict]]:
    """One repair round per failed field: the model may only pick among real source passages."""
    still_failed, log = [], []
    for path in failed:
        bad = (cand.get("coverage") or {}).get("coverage_span") if path.startswith("coverage.") else cand.get(path)
        options = verify.candidate_windows(body, bad or _value_for(cand, path))
        out, _ = structured(
            "repair",
            prompts.REPAIR_SYSTEM,
            prompts.repair_user(path, _value_for(cand, path), bad or "", options),
            RepairOut,
            ref=ref,
            max_tokens=4000,
        )
        m = verify.find_span(body, out.quote) if out.quote else None
        if m is None:
            still_failed.append(path)
            log.append({"field": path, "result": "repair_fail"})
            continue
        if path.startswith("coverage."):
            cand["coverage"] = {**cand["coverage"], "coverage_span": m.text}
        else:
            cand[path] = m.text
        cand.setdefault("_offsets", {})[path] = [m.start, m.end]
        cand["confidence"] = max(0.0, (cand.get("confidence") or 0.8) - 0.1)
        log.append({"field": path, "result": "repair_" + m.method})
    return cand, still_failed, log


def extract_doc(doc_id: str) -> dict:
    src = corpus.get_source(doc_id)
    if src is None or not src.has_text:
        return {"doc_id": doc_id, "skipped": True}
    allowed = allowed_jurisdictions(src.jurisdictions)
    if src.source_type != "official":
        # roundup articles (law-firm alerts, news) often cover several in-scope cities; still capped as secondary
        with db.session() as s:
            every = sorted(
                {j for (js,) in s.execute(select(db.Source.jurisdictions).where(db.Source.in_corpus)) for j in js}
            )
        allowed = allowed + [j for j in every if j not in allowed]
    chunks = corpus.chunk_body(src.body)
    rows, stats = [], {"doc_id": doc_id, "chunks": len(chunks), "raw": 0, "verified": 0, "dropped": 0}
    for ch in chunks:
        ref = f"{doc_id}#{ch.index}"
        user = prompts.extract_user(
            doc_id, src.url, src.retrieved_at, src.source_type, allowed, ch.text, ch.index, len(chunks)
        )
        out, h = structured("extract", prompts.EXTRACT_SYSTEM, user, ExtractionOut, ref=ref, max_tokens=64000)
        for r in out.rules:
            stats["raw"] += 1
            cand = r.model_dump(mode="json")
            cand["source_doc_id"] = doc_id
            cand["discussed_without_rule"] = out.categories_discussed_without_rule
            log: list[dict] = []
            if cand["jurisdiction"] not in allowed:
                log.append({"field": "jurisdiction", "result": "fail", "value": cand["jurisdiction"]})
                final = None
            else:
                cand, vlog, failed = verify.verify_fields(cand, src.body)
                log += vlog
                if failed:
                    cand, failed, rlog = _repair(cand, failed, src.body, ref)
                    log += rlog
                final, notes = verify.apply_failures(cand, failed)
                log += [{"note": n} for n in notes]
            if final is not None and (src.source_type != "official" or not src.in_corpus):
                final["confidence"] = min(final.get("confidence") or 0.6, 0.6)
                final["secondary_source"] = True
            ok = final is not None
            stats["verified" if ok else "dropped"] += 1
            rows.append(
                db.Candidate(
                    doc_id=doc_id,
                    chunk=ch.index,
                    call_hash=h,
                    jurisdiction=cand["jurisdiction"],
                    category=cand["category"],
                    data=final if ok else cand,
                    verified=ok,
                    verify_log=log,
                )
            )
            db.audit("verify", "verified" if ok else "dropped", f"{doc_id}:{cand['category']}", log=log)
    with db.session() as s:
        s.execute(delete(db.Candidate).where(db.Candidate.doc_id == doc_id))
        s.add_all(rows)
    return stats


def extract_all(doc_ids: list[str] | None = None, progress=print) -> list[dict]:
    if doc_ids is None:
        with db.session() as s:
            doc_ids = list(s.scalars(select(db.Source.doc_id).where(db.Source.has_text).order_by(db.Source.doc_id)))
    results = []
    with ThreadPoolExecutor(max_workers=config.max_parallel()) as pool:
        futs = {pool.submit(extract_doc, d): d for d in doc_ids}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # one bad doc must not stop the run; it is logged and reported
                r = {"doc_id": futs[f], "error": f"{type(e).__name__}: {e}"[:500]}
                db.audit("extract", "error", futs[f], error=r["error"])
            results.append(r)
            progress(r)
    return results


def verified_candidates(jurisdiction: str | None = None) -> list[db.Candidate]:
    with db.session() as s:
        q = select(db.Candidate).where(db.Candidate.verified)
        if jurisdiction:
            q = q.where(db.Candidate.jurisdiction == jurisdiction)
        return list(s.scalars(q.order_by(db.Candidate.id)))
