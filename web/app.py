"""Web app: address lookup, change tracking, rules explorer, sources and method. Not legal advice."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from navigator import DISCLAIMER, changes, config, consolidate, corpus, db, evaluate, facts, geo

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Rental Housing Law Navigator", description=DISCLAIMER)


@app.middleware("http")
async def not_legal_advice(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Not-Legal-Advice"] = "true"
    return resp


def parse_date(s: str | None) -> date:
    try:
        return date.fromisoformat(s) if s else config.AS_OF_DEFAULT
    except ValueError:
        raise HTTPException(400, "as_of must be YYYY-MM-DD")


@app.get("/api/health")
def health():
    with db.session() as s:
        n_src = s.scalar(select(func.count()).select_from(db.Source))
        n_addr = s.scalar(select(func.count()).select_from(db.Address))
    return {
        "ok": True,
        "kb_version": db.latest_kb_version(),
        "sources": n_src,
        "addresses": n_addr,
        "provider": config.llm_provider(),
        "model": config.llm_model(),
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/addresses")
def addresses(q: str = "", limit: int = Query(12, le=600)):
    q = q.strip().lower()
    out = []
    for a in geo.all_addresses():
        r = a.raw
        label = f"{r['street_address']}, {r['postal_city']}, {r['state']} {r['zip']}".strip()
        if not q or q in label.lower() or q == a.address_id.lower():
            city = (a.stack or {}).get("city")
            out.append({"address_id": a.address_id, "label": label, "legal_city": city})
            if len(out) >= limit:
                break
    return out


@app.get("/api/lookup/{address_id}")
def lookup(address_id: str, as_of: str | None = None):
    try:
        return evaluate.lookup_address(address_id, parse_date(as_of))
    except KeyError:
        raise HTTPException(404, "unknown address id")


class FactsIn(BaseModel):
    year_built: int | None = None
    units: int | None = None
    subsidized: bool | None = None  # is the rent set or limited by a government program?
    owner_occupied: bool | None = None  # does the owner live in the building?


@app.post("/api/lookup/{address_id}")
def lookup_with_facts(address_id: str, body: FactsIn, as_of: str | None = None):
    """The 'confirm facts' flow: re-run the same deterministic evaluator with facts the user supplies."""
    try:
        return evaluate.lookup_address(address_id, parse_date(as_of), facts_override=body.model_dump())
    except KeyError:
        raise HTTPException(404, "unknown address id")


class CustomAddress(BaseModel):
    street: str
    city: str
    state: str
    zip: str = ""
    year_built: int | None = None
    units: int | None = None
    subsidized: bool | None = None
    owner_occupied: bool | None = None


@app.post("/api/lookup-custom")
def lookup_custom(body: CustomAddress, as_of: str | None = None):
    """Any address in the three states: geocoded live (cached); building facts come only from the user."""
    if body.state.upper() not in ("CA", "NJ", "MA"):
        raise HTTPException(400, "state must be CA, NJ or MA (the states in scope)")
    row = {
        "address_id": None,
        "street_address": body.street,
        "postal_city": body.city,
        "state": body.state.upper(),
        "zip": body.zip,
    }
    try:
        stack = geo.resolve_row(row, None, geo.in_scope_cities())
    except geo.GeoOffline:
        raise HTTPException(503, "geocoder unavailable in offline mode")
    f = facts.building_facts(
        {
            **row,
            "year_built": body.year_built or "",
            "units": body.units or "",
            "use_code": "",
            "use_description": "",
            "source_dataset": "user",
        }
    )
    f["notes"] = f["notes"] + ["building facts supplied by the user"]
    confirmed = {k: v for k, v in body.model_dump().items() if k in ("subsidized", "owner_occupied") and v is not None}
    for k in ("year_built", "units"):
        if getattr(body, k) is not None:
            f.setdefault("user_supplied", []).append(k)
    return evaluate.describe(stack, f, row, None, parse_date(as_of), facts_override=confirmed or None)


@app.get("/api/rules")
def rules(jurisdiction: str | None = None, category: str | None = None):
    out = []
    for r in consolidate.load_rules():
        if jurisdiction and r["jurisdiction"] != jurisdiction:
            continue
        if category and r["category"] != category:
            continue
        out.append(
            {
                k: r.get(k)
                for k in (
                    "team_rule_id",
                    "jurisdiction",
                    "level",
                    "category",
                    "title",
                    "requirement",
                    "key_value",
                    "citation",
                    "effective_date",
                    "enacted",
                    "failed",
                    "instrument",
                    "confidence",
                    "conflict_flag",
                    "conflict_note",
                    "source_doc_id",
                    "quoted_span",
                    "quote_offsets",
                    "secondary_source",
                    "supersedes",
                    "superseded_by",
                    "may_conflict_with",
                )
            }
            | {"status": evaluate.time_status(r, config.AS_OF_DEFAULT)}
        )
    return out


@app.get("/api/source/{doc_id}")
def source(doc_id: str, start: int = 0, end: int = 0, ctx: int = Query(900, le=3000)):
    src = corpus.get_source(doc_id)
    if src is None:
        raise HTTPException(404, "unknown source")
    out = {
        "doc_id": doc_id,
        "url": src.url,
        "retrieved_at": src.retrieved_at,
        "source_type": src.source_type,
        "in_corpus": src.in_corpus,
        "jurisdictions": src.jurisdictions,
        "has_text": src.has_text,
    }
    if src.body and end > start:
        a, b = max(0, start - ctx), min(len(src.body), end + ctx)
        out.update(
            before=("… " if a else "") + src.body[a:start],
            quote=src.body[start:end],
            after=src.body[end:b] + (" …" if b < len(src.body) else ""),
        )
    return out


@app.get("/api/changes")
def get_changes():
    path = config.OUTPUT_DIR / "changes_detail.json"
    data = json.loads(path.read_text()) if path.exists() else changes.run_all()
    tests = {t["test_id"]: t for t in changes.load_tests()}
    addr_city = {a.address_id: (a.stack or {}).get("city") for a in geo.all_addresses()}
    out = []
    for tid, res in sorted(data.items()):
        t = tests.get(tid, {"title": res.get("notes", "")[:80], "expected_behavior": ""})
        cities: dict = {}
        for aid in res["affected_address_ids"]:
            cities[addr_city.get(aid) or "(state only)"] = cities.get(addr_city.get(aid) or "(state only)", 0) + 1
        out.append(
            {
                "test_id": tid,
                "title": t["title"],
                "type": t.get("type"),
                "expected_behavior": t.get("expected_behavior"),
                "affected": len(res["affected_address_ids"]),
                "conflicts": len(res["conflict_flag_address_ids"]),
                "sample_ids": res["affected_address_ids"][:12],
                "by_city": cities,
                "notes": res.get("notes"),
                "rule_map": res.get("rule_map"),
            }
        )
    return out


@app.get("/api/selfcheck")
def selfcheck():
    p = config.OUTPUT_DIR / "selfcheck.txt"
    return {"text": p.read_text() if p.exists() else "Run: python -m navigator selfcheck"}


@app.get("/api/audit")
def audit_summary():
    with db.session() as s:
        calls = dict(s.execute(select(db.LLMCall.stage, func.count()).group_by(db.LLMCall.stage)).all())
        events = dict(s.execute(select(db.AuditEvent.stage, func.count()).group_by(db.AuditEvent.stage)).all())
        versions = [
            {
                "version": v.version,
                "note": v.note,
                "provider": v.provider,
                "model": v.model,
                "created_at": v.created_at.isoformat(),
            }
            for v in s.scalars(select(db.KBVersion))
        ]
    return {"llm_calls": calls, "audit_events": events, "kb_versions": versions}


@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)


def _title(body: str | None, url: str) -> str:
    for line in (body or "").splitlines():
        line = line.strip()
        if 12 <= len(line) <= 110 and not line.lower().startswith(("skip", "menu", "search", "http")):
            return line
    return url.split("//")[-1].split("/")[0]


@app.get("/api/resources")
def resources(state: str, city: str | None = None):
    """Official pages in the source library for this address's state and city (no invented links)."""
    wanted = [j for j in (city, state) if j]
    out = []
    with db.session() as s:
        for src in s.scalars(select(db.Source).where(db.Source.source_type == "official")):
            hit = next((j for j in wanted if j in src.jurisdictions), None)
            if hit and src.in_corpus:
                out.append({"doc_id": src.doc_id, "url": src.url, "jurisdiction": hit,
                            "title": _title(src.body, src.url), "host": src.url.split("//")[-1].split("/")[0]})
    out.sort(key=lambda r: (wanted.index(r["jurisdiction"]), r["title"]))
    return out


DIST = Path(__file__).parent / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    if not (DIST / "index.html").exists():
        raise HTTPException(503, "Front end not built: run `cd frontend && npm install && npm run build`")
    return FileResponse(DIST / "index.html")
