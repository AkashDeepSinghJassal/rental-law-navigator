"""Web app tests against the real application database (the built knowledge base) via FastAPI's real ASGI stack."""

import pytest
from fastapi.testclient import TestClient

from navigator import config, db


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", "sqlite:///data/navigator.db")  # the real KB, not the scratch test DB
    from web.app import app

    if db.latest_kb_version() is None:
        pytest.skip("knowledge base not built yet: run `python -m navigator consolidate`")
    with TestClient(app) as c:
        yield c
    mp.undo()


def test_health_and_not_legal_advice_header(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["kb_version"] >= 1 and r.json()["addresses"] == 500
    assert r.headers["X-Not-Legal-Advice"] == "true"
    page = client.get("/")
    assert page.status_code == 200 and "Not legal advice" in page.text


def test_address_search_and_lookup(client):
    hits = client.get("/api/addresses", params={"q": "clinton st"}).json()
    assert hits and all("clinton st" in h["label"].lower() for h in hits)
    sf = next(
        h
        for h in client.get("/api/addresses", params={"q": "", "limit": 500}).json()
        if h["legal_city"] == "San Francisco, CA"
    )
    d = client.get(f"/api/lookup/{sf['address_id']}").json()
    assert d["as_of"] == "2026-10-01" and d["stack"]["city"] == "San Francisco, CA"
    assert d["results"] and "Not legal advice" in d["disclaimer"]
    for x in d["results"]:
        assert x["result"] in {"applies", "unknown", "superseded", "not_yet_effective", "pending"}
        assert x["rule"]["citation"] and x["rule"]["quoted_span"]
    assert client.get("/api/lookup/NOPE").status_code == 404
    assert client.get(f"/api/lookup/{sf['address_id']}", params={"as_of": "bad"}).status_code == 400


def test_as_of_dates_change_results(client):
    nj = next(
        h
        for h in client.get("/api/addresses", params={"q": "", "limit": 500}).json()
        if h["legal_city"] == "Newark, NJ"
    )
    now = {x["team_rule_id"]: x["result"] for x in client.get(f"/api/lookup/{nj['address_id']}").json()["results"]}
    later = {
        x["team_rule_id"]: x["result"]
        for x in client.get(f"/api/lookup/{nj['address_id']}", params={"as_of": "2027-07-02"}).json()["results"]
    }
    assert "not_yet_effective" in now.values()  # NJ FAIR Act, effective 2027-07-01
    flipped = [r for r in now if now[r] == "not_yet_effective" and later.get(r) in ("applies", "unknown")]
    assert flipped, (now, later)


def test_quote_in_source_panel_matches_rule_quote(client):
    sf = next(h for h in client.get("/api/addresses", params={"q": "", "limit": 500}).json() if h["legal_city"])
    d = client.get(f"/api/lookup/{sf['address_id']}").json()
    x = next(x for x in d["results"] if x["rule"]["quote_offsets"])
    s, e = x["rule"]["quote_offsets"]["quoted_span"]
    src = client.get(f"/api/source/{x['rule']['source_doc_id']}", params={"start": s, "end": e}).json()
    assert src["quote"] == x["rule"]["quoted_span"] and src["url"].startswith("http")


def test_confirm_facts_reruns_evaluator(client):
    unknowns = [(h["address_id"]) for h in client.get("/api/addresses", params={"q": "", "limit": 500}).json()]
    for aid in unknowns:
        d = client.get(f"/api/lookup/{aid}").json()
        if "year_built" in d["facts"]["missing"] and any(x["result"] == "unknown" for x in d["results"]):
            before = sum(x["result"] == "unknown" for x in d["results"])
            after = client.post(f"/api/lookup/{aid}", json={"year_built": 2015, "units": 30}).json()
            assert "year_built" not in after["facts"]["missing"] and after["facts"]["year_built"] == 2015
            assert sum(x["result"] == "unknown" for x in after["results"]) <= before
            return
    pytest.skip("no address with unknown year_built found")


@pytest.mark.live
def test_custom_address_live_geocode(client):
    r = client.post(
        "/api/lookup-custom",
        json={
            "street": "1 Dr Carlton B Goodlett Pl",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94102",
            "year_built": 1915,
            "units": 40,
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stack"]["city"] == "San Francisco, CA" and d["facts"]["units"] == 40
    assert (
        client.post("/api/lookup-custom", json={"street": "1 Main", "city": "Austin", "state": "TX"}).status_code == 400
    )


def test_rules_changes_and_method_endpoints(client):
    rules = client.get("/api/rules").json()
    assert len(rules) > 50 and all(r["citation"] and r["quoted_span"] for r in rules)
    assert client.get("/api/rules", params={"jurisdiction": "NJ"}).json()
    ch = client.get("/api/changes").json()
    assert {t["test_id"] for t in ch} >= {"T1", "T2", "T3", "T4", "T5"}
    assert client.get("/api/audit").json()["llm_calls"]
    assert config.OUTPUT_DIR.exists()


def test_official_resources_come_from_the_source_library(client):
    res = client.get("/api/resources", params={"state": "CA", "city": "San Francisco, CA"}).json()
    assert res and all(r["url"].startswith("http") and r["jurisdiction"] in ("CA", "San Francisco, CA") for r in res)
    assert res[0]["jurisdiction"] == "San Francisco, CA"  # city pages first


def test_coordinates_present_for_the_map(client):
    d = client.get("/api/lookup/A0016").json()
    assert isinstance(d["stack"]["lat"], float) and isinstance(d["stack"]["lon"], float)


def test_confirmed_facts_change_the_answer(client):
    before = {x["team_rule_id"]: x["result"] for x in client.get("/api/lookup/A0016").json()["results"]}
    after = {
        x["team_rule_id"]: x["result"]
        for x in client.post("/api/lookup/A0016", json={"subsidized": False, "owner_occupied": False}).json()["results"]
    }
    changed = [k for k in before if before[k] == "unknown" and after.get(k) in ("applies", "superseded")]
    assert changed, (before, after)
