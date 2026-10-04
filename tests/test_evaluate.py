"""B3 evaluator logic. Rules here are synthetic (fictional jurisdiction 'Testville, CA'); facts come from the real
building-facts normalizer applied to real-shaped assessor rows. Pure functions, no network."""

from datetime import date

from navigator import evaluate as ev
from navigator.facts import building_facts

AS_OF = date(2026, 10, 1)
STACK = {"state": "CA", "city": "Testville, CA"}


def bld(year="", units="", desc="x", dataset="DataSF"):
    return building_facts(
        {
            "year_built": str(year),
            "units": str(units),
            "use_code": "",
            "use_description": desc,
            "source_dataset": dataset,
        }
    )


def rule(rid="r-0001", jur="Testville, CA", cat="rent_increase_limits", **kw):
    base = {
        "team_rule_id": rid,
        "jurisdiction": jur,
        "level": "city",
        "category": cat,
        "title": f"Rule {rid}",
        "citation": "Testville Code 1",
        "enacted": True,
        "failed": False,
        "effective_date": None,
        "coverage": {"exemptions": []},
    }
    base.update(kw)
    return base


def one(r, f, as_of=AS_OF, extra=()):
    res = ev.evaluate_address(STACK, f, [r, *extra], as_of)
    return {x["team_rule_id"]: x for x in res}


def test_time_branches():
    f = bld(1960, 20)
    assert one(rule(effective_date="2027-07-01"), f)["r-0001"]["result"] == "not_yet_effective"
    assert one(rule(effective_date="2027-07-01"), f, date(2027, 7, 2))["r-0001"]["result"] == "applies"
    assert one(rule(enacted=False), f)["r-0001"]["result"] == "pending"
    assert one(rule(failed=True), f) == {}
    assert one(rule(effective_date="2026-10"), f)["r-0001"]["result"] == "unknown"  # month-only date
    assert one(rule(sunset_date="2025-12-31"), f) == {}


def test_other_jurisdictions_are_ignored():
    assert one(rule(jur="Elsewhere, CA"), bld(1960, 20)) == {}
    assert one(rule(jur="CA", level="state"), bld(1960, 20))["r-0001"]["result"] == "applies"


def test_unit_thresholds_with_exact_derived_and_missing_units():
    r = rule(coverage={"min_units": 5, "exemptions": []})
    assert one(r, bld(units=20))["r-0001"]["result"] == "applies"
    assert one(r, bld(units=3)) == {}
    derived = bld(desc="Five or more apartments", dataset="LA County eGIS parcels")  # units derived 5+
    assert one(r, derived)["r-0001"]["result"] == "applies"
    unknown = one(r, bld())["r-0001"]
    assert unknown["result"] == "unknown" and unknown["missing_facts"] == ["units"]


def test_certificate_of_occupancy_cutoff_year_is_unknown():
    r = rule(coverage={"built_before": "1979-06-13", "cutoff_basis": "certificate_of_occupancy", "exemptions": []})
    assert one(r, bld(1962, 20))["r-0001"]["result"] == "applies"
    assert one(r, bld(1985, 20)) == {}
    same = one(r, bld(1979, 20))["r-0001"]
    assert same["result"] == "unknown" and "certificate_of_occupancy" in same["missing_facts"]
    assert one(r, bld("", 20))["r-0001"]["result"] == "unknown"


def test_exemptions_ruled_out_or_unknown():
    small_owner = {"description": "small landlord", "max_units": 4, "depends_on": ["owner_type"]}
    r = rule(cat="security_deposits", coverage={"exemptions": [small_owner]})
    assert one(r, bld(1990, 20))["r-0001"]["result"] == "applies"  # 20 units: exemption impossible
    u = one(r, bld(1990, ""))["r-0001"]
    assert u["result"] == "unknown" and "owner_type" in u["missing_facts"]
    new = {"description": "new construction", "newer_than_years": 15, "depends_on": []}
    r2 = rule(coverage={"exemptions": [new]})
    assert one(r2, bld(2020, 20)) == {}  # exempt: built within 15 years
    assert one(r2, bld(1990, 20))["r-0001"]["result"] == "applies"
    free_text = {"description": "hotels and dormitories", "depends_on": []}
    assert one(rule(coverage={"exemptions": [free_text]}), bld(1990, 20))["r-0001"]["result"] == "applies"


def test_precedence_local_supersedes_state():
    state = rule("r-0001", jur="CA", level="state", superseded_by=["r-0002"])
    local = rule(
        "r-0002",
        coverage={"built_before": "1979-06-13", "cutoff_basis": "certificate_of_occupancy", "exemptions": []},
        supersedes=["r-0001"],
    )
    res = one(state, bld(1962, 20), extra=[local])
    assert res["r-0002"]["result"] == "applies" and res["r-0001"]["result"] == "superseded"
    res = one(state, bld(1979, 20), extra=[local])  # local coverage unknown -> state unknown, not omitted
    assert res["r-0002"]["result"] == "unknown" and res["r-0001"]["result"] == "unknown"
    res = one(state, bld(1990, 20), extra=[local])  # local does not cover -> state applies
    assert res["r-0001"]["result"] == "applies" and "r-0002" not in res


def test_conflict_flag_only_when_partner_present():
    state = rule(
        "r-0001",
        jur="CA",
        level="state",
        cat="algorithmic_rent_setting",
        effective_date="2027-07-01",
        may_conflict_with=["r-0002"],
        conflict_flag=True,
    )
    local = rule("r-0002", cat="algorithmic_rent_setting", may_conflict_with=["r-0001"], conflict_flag=True)
    res = one(state, bld(1990, 20), extra=[local])
    assert res["r-0001"]["conflict_flag"] and res["r-0002"]["conflict_flag"]
    assert res["r-0001"]["result"] == "not_yet_effective"
    alone = ev.evaluate_address({"state": "CA", "city": None}, bld(1990, 20), [state, local], AS_OF)
    assert alone[0]["team_rule_id"] == "r-0001" and alone[0]["conflict_flag"] is False


def test_inferred_subsidy_never_silently_removes_a_rule():
    govt = {"description": "government-regulated rents", "depends_on": ["subsidized"]}
    r = rule(coverage={"exemptions": [govt]})
    inferred = bld(desc="3S-6U-AFFORDABL", dataset="NJOGIS Parcels & MOD-IV Composite")  # subsidized inferred only
    assert inferred["subsidized"] is True
    res = one(r, inferred)["r-0001"]
    assert res["result"] == "unknown" and "subsidized" in res["missing_facts"]
    # the person asking can resolve it
    said_no = {**inferred, "subsidized": False, "user_supplied": ["subsidized"]}
    assert one(r, said_no)["r-0001"]["result"] == "applies"
    said_yes = {**inferred, "subsidized": True, "user_supplied": ["subsidized"]}
    assert one(r, said_yes) == {}


def test_year_decides_cutoff_without_exact_certificate_date():
    r = rule(
        coverage={
            "built_before": "1979-06-13",
            "cutoff_basis": "certificate_of_occupancy",
            "requires_facts_not_in_data": ["certificate_of_occupancy"],
            "exemptions": [],
        }
    )
    assert one(r, bld(1926, 21))["r-0001"]["result"] == "applies"
    assert one(r, bld(1979, 21))["r-0001"]["result"] == "unknown"  # same year: the exact date really is needed


def test_local_rule_that_applies_supersedes_a_state_rule_with_unknown_coverage():
    state = rule(
        "r-0001",
        jur="CA",
        level="state",
        superseded_by=["r-0002"],
        coverage={"exemptions": [{"description": "owner lives there", "depends_on": ["owner_occupied"]}]},
    )
    local = rule("r-0002", supersedes=["r-0001"])
    res = one(state, bld(1990, 20), extra=[local])
    assert res["r-0002"]["result"] == "applies" and res["r-0001"]["result"] == "superseded"
