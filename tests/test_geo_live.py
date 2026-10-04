"""B1+B2 against the real Census Geocoder and the real 500 sample addresses."""

import pytest

from navigator import corpus, facts, geo

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def stats():
    corpus.ingest()  # the in-scope city list comes from the source library
    return geo.resolve_all()


def test_all_addresses_resolved(stats):
    assert stats["total"] == 500
    assert stats["batch"] + stats["oneline"] >= 480, stats  # Census matched almost everything
    assert stats["no_city"] <= 10, stats


def test_postal_neighborhoods_resolve_to_legal_city(stats):
    rows = {a.address_id: a for a in geo.all_addresses()}
    dorchester = [a for a in rows.values() if a.raw["postal_city"] == "Dorchester"]
    assert dorchester and all(a.stack["city"] == "Boston, MA" for a in dorchester)
    ysidro = [a for a in rows.values() if a.raw["postal_city"] == "San Ysidro"]
    assert ysidro and ysidro[0].stack["city"] == "San Diego, CA"
    hob = [a for a in rows.values() if a.raw["postal_city"] == "Hoboken"]
    assert sum(a.stack["city"] == "Hoboken, NJ" for a in hob) >= len(hob) - 1
    assert all(a.stack["city"] != "Santa Ana, CA" for a in rows.values())


def test_offline_replay_uses_cache(stats, monkeypatch):
    monkeypatch.setenv("NAVIGATOR_OFFLINE", "1")
    again = geo.resolve_all()
    assert again == stats


def test_unit_ranges_from_real_use_codes():
    f = facts.building_facts
    base = {"year_built": "", "units": "", "use_code": ""}
    assert (
        f({**base, "source_dataset": "Boston Property Assessment FY2026", "use_description": "APT 7-30 UNITS"})[
            "units_min"
        ]
        == 7
    )
    r = f(
        {
            **base,
            "source_dataset": "NJOGIS Parcels & MOD-IV Composite",
            "use_code": "4C",
            "use_description": "3S-B-A-13U-H",
        }
    )
    assert (r["units_min"], r["units_max"]) == (13, 13) and "units" in r["derived"]
    r = f({**base, "source_dataset": "NJOGIS Parcels & MOD-IV Composite", "use_code": "4C", "use_description": "3SB"})
    assert (r["units_min"], r["units_max"]) == (5, None)
    r = f({**base, "source_dataset": "DataSF", "units": "20", "year_built": "1962", "use_description": "x"})
    assert r["units"] == 20 and r["year_built"] == 1962 and "units" not in r["missing"]
    r = f({**base, "source_dataset": "Boston Property Assessment FY2026", "use_description": "SUBSD HOUSING S- 8"})
    assert r["subsidized"] is True and "units" in r["missing"]
