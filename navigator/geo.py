"""B2 Resolver: address -> legal jurisdiction stack via the US Census Geocoder (cached in the database)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy import select

from navigator import config, db, facts

BASE = "https://geocoding.geo.census.gov/geocoder"
PARAMS = {"benchmark": "Public_AR_Current", "vintage": "Current_Current"}
LAYERS = "Incorporated Places,Counties,County Subdivisions"
STATE_FIPS = {"06": "CA", "34": "NJ", "25": "MA"}

# last-resort fallback only: well-known neighborhoods that are inside the legal city (confidence 0.5, flagged)
NEIGHBORHOODS = {
    ("MA", "ALLSTON"): "Boston", ("MA", "BRIGHTON"): "Boston", ("MA", "DORCHESTER"): "Boston",
    ("MA", "EAST BOSTON"): "Boston", ("MA", "HYDE PARK"): "Boston", ("MA", "JAMAICA PLAIN"): "Boston",
    ("MA", "MATTAPAN"): "Boston", ("MA", "ROXBURY"): "Boston", ("MA", "SOUTH BOSTON"): "Boston",
    ("CA", "SAN YSIDRO"): "San Diego",
}  # fmt: skip


class GeoOffline(RuntimeError):
    pass


def _cached(method: str, url: str, params: dict, files: dict | None = None) -> str:
    key = hashlib.sha256(json.dumps([method, url, params, files], sort_keys=True).encode()).hexdigest()
    with db.session() as s:
        hit = s.get(db.HttpCache, key)
        if hit:
            return hit.response
    if config.offline():
        raise GeoOffline(f"offline cache miss: {url}")
    for attempt in range(4):
        try:
            if method == "POST":
                r = httpx.post(url, data=params, files={k: ("a.csv", v) for k, v in (files or {}).items()}, timeout=300)
            else:
                r = httpx.get(url, params=params, timeout=60)
            r.raise_for_status()
            break
        except httpx.HTTPError as e:
            if attempt == 3:
                raise
            db.audit("geocode", "retry", url, error=str(e)[:300])
    with db.session() as s:
        s.merge(db.HttpCache(key=key, url=url, response=r.text))
    return r.text


def in_scope_cities() -> dict[str, str]:
    """'San Francisco' -> 'San Francisco, CA' for every city jurisdiction in the source library."""
    with db.session() as s:
        jurs = {j for (js,) in s.execute(select(db.Source.jurisdictions)) for j in js}
    return {j.split(",")[0].strip().lower(): j for j in jurs if "," in j}


def _house_numbers(street: str) -> tuple[int, int] | None:
    m = re.match(r"\s*(\d+)(?:\s*-\s*(\d+))?", street)
    if not m:
        return None
    a = int(m[1])
    return a, int(m[2]) if m[2] else a


def batch_geocode(rows: list[dict]) -> dict[str, dict]:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow([r["address_id"], r["street_address"], r["postal_city"], r["state"], r["zip"]])
    text = _cached("POST", f"{BASE}/geographies/addressbatch", PARAMS, {"addressFile": buf.getvalue()})
    out = {}
    for rec in csv.reader(io.StringIO(text)):
        if len(rec) >= 6 and rec[2] == "Match":
            lon, lat = rec[5].split(",")
            out[rec[0]] = {"matched": rec[4], "lon": float(lon), "lat": float(lat), "state_fips": rec[8]}
    return out


def place_for_point(lon: float, lat: float) -> dict:
    text = _cached(
        "GET",
        f"{BASE}/geographies/coordinates",
        {**PARAMS, "x": f"{lon:.6f}", "y": f"{lat:.6f}", "layers": LAYERS, "format": "json"},
    )
    g = json.loads(text)["result"]["geographies"]
    return {k: [x.get("NAME") for x in v] for k, v in g.items()}


def oneline(row: dict) -> dict | None:
    addr = f"{row['street_address']}, {row['postal_city']}, {row['state']} {row['zip']}".strip()
    text = _cached(
        "GET", f"{BASE}/geographies/onelineaddress", {**PARAMS, "address": addr, "layers": LAYERS, "format": "json"}
    )
    matches = json.loads(text)["result"].get("addressMatches") or []
    if not matches:
        return None
    m = matches[0]
    g = m.get("geographies") or {}
    return {
        "matched": m["matchedAddress"],
        "lon": m["coordinates"]["x"],
        "lat": m["coordinates"]["y"],
        "places": {k: [x.get("NAME") for x in v] for k, v in g.items()},
    }


def _city_from_places(places: dict, state: str, scope: dict[str, str]) -> tuple[str | None, str | None]:
    names = (places.get("Incorporated Places") or []) + (places.get("County Subdivisions") or [])
    county = (places.get("Counties") or [None])[0]
    for n in names:
        base = re.sub(r"\s+(city|town|township|CDP)$", "", n or "", flags=re.IGNORECASE).strip().lower()
        j = scope.get(base)
        if j and j.endswith(state):
            return j, county
    return None, county


def resolve_row(row: dict, batch_hit: dict | None, scope: dict[str, str]) -> dict:
    st = row["state"]
    stack = {
        "state": st,
        "county": None,
        "city": None,
        "census_place": None,
        "method": None,
        "confidence": 0.0,
        "matched": None,
        "note": None,
    }
    hit, method = batch_hit, "batch"
    want = _house_numbers(row["street_address"])
    if hit:
        got = _house_numbers(hit["matched"])
        if want and got and not (want[0] <= got[0] <= want[1] or got[0] in want):
            hit, method = None, None  # matched a different house number: try a single-line geocode
            stack["note"] = f"batch match '{batch_hit['matched']}' had a different house number"
    places = None
    if hit:
        places = place_for_point(hit["lon"], hit["lat"])
    else:
        one = oneline(row)
        if one:
            got = _house_numbers(one["matched"])
            if not (want and got and not (want[0] <= got[0] <= want[1])):
                hit, method, places = one, "oneline", one["places"]
    if hit and places is not None:
        city, county = _city_from_places(places, st, scope)
        stack.update(
            city=city,
            county=county,
            method=method,
            matched=hit["matched"],
            lon=hit["lon"],
            lat=hit["lat"],
            confidence=0.95,
            census_place=(places.get("Incorporated Places") or [None])[0],
        )
        if city is None:
            stack["note"] = f"outside the cities in scope ({stack['census_place']}); state rules only"
        return stack
    # last resort: postal city or known neighborhood
    pc = row["postal_city"].strip()
    city_name = NEIGHBORHOODS.get((st, pc.upper()), pc)
    j = scope.get(city_name.lower())
    stack.update(
        city=j if j and j.endswith(st) else None,
        method="postal_fallback",
        confidence=0.5,
        note=f"Census could not match this address; legal city taken from postal city '{pc}'",
    )
    return stack


def resolve_all(csv_path=config.ADDRESSES_CSV) -> dict:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    scope = in_scope_cities()
    hits = batch_geocode(rows)
    with ThreadPoolExecutor(max_workers=8) as pool:
        stacks = list(pool.map(lambda r: resolve_row(r, hits.get(r["address_id"]), scope), rows))
    stats = {"total": len(rows), "batch": 0, "oneline": 0, "postal_fallback": 0, "postal_differs": 0, "no_city": 0}
    with db.session() as s:
        for r, st in zip(rows, stacks):
            stats[st["method"]] += 1
            if st["city"] is None:
                stats["no_city"] += 1
            elif st["city"].split(",")[0].lower() != r["postal_city"].lower():
                stats["postal_differs"] += 1
            s.merge(db.Address(address_id=r["address_id"], raw=r, facts=facts.building_facts(r), stack=st))
    db.audit("geocode", "done", None, **stats)
    return stats


def get_address(address_id: str) -> db.Address | None:
    with db.session() as s:
        return s.get(db.Address, address_id)


def all_addresses() -> list[db.Address]:
    with db.session() as s:
        return list(s.scalars(select(db.Address).order_by(db.Address.address_id)))
