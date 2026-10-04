"""Live A1+A2: real LLM extraction on real corpus documents, verified quotes checked against the real text.

The expectations come from the challenge brief (test data only; nothing here feeds the pipeline).
"""

import os

import pytest

from navigator import corpus, extract

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY") and os.getenv("LLM_PROVIDER", "anthropic") == "anthropic",
        reason="no LLM key",
    ),
]


@pytest.fixture(scope="module", autouse=True)
def _ingest():
    corpus.ingest()


def _assert_quotes_verbatim(doc_id, cands):
    body = corpus.get_source(doc_id).body
    for c in cands:
        s, e = c.data["_offsets"]["quoted_span"]
        assert body[s:e] == c.data["quoted_span"], "stored quote must be the raw source substring"
        assert len(c.data["quoted_span"]) >= 20


def test_extract_nj_screening_fee_law():
    stats = extract.extract_doc("D066")  # P.L.2025, c.405
    assert stats["verified"] >= 1
    cands = [c for c in extract.verified_candidates("NJ") if c.doc_id == "D066"]
    _assert_quotes_verbatim("D066", cands)
    fees = [c for c in cands if c.category == "application_screening_fees"]
    assert fees, f"expected a fee rule, got {[c.category for c in cands]}"
    assert any("50" in (c.data.get("key_value") or "") for c in fees)


def test_extract_nj_fair_act_dates():
    stats = extract.extract_doc("D069")  # FAIR Act, P.L.2026, c.43
    assert stats["verified"] >= 1
    cands = [c for c in extract.verified_candidates("NJ") if c.doc_id == "D069"]
    _assert_quotes_verbatim("D069", cands)
    alg = [c for c in cands if c.category == "algorithmic_rent_setting"]
    assert alg and all(c.data["enacted"] for c in alg)
    dates = {c.data.get("effective_date") for c in alg}
    assert any(d and d.startswith("2027-07") for d in dates), f"brief says effective 7/1/2027; got {dates}"
