"""A2 verifier on real corpus text (no synthetic documents)."""

import pytest

from navigator import corpus, verify


@pytest.fixture(scope="module")
def d024():
    corpus.ingest()
    return corpus.get_source("D024").body  # Cal. Civ. Code 1947.12


def _real_sentence(body: str, needle: str, length: int = 160) -> str:
    i = body.index(needle)
    return body[i : i + length]


def test_exact_match_returns_raw_offsets(d024):
    q = _real_sentence(d024, "an owner of residential real property shall not")
    m = verify.find_span(d024, q)
    assert m and m.method == "exact"
    assert d024[m.start : m.end] == m.text
    assert verify.normalize(m.text) == verify.normalize(q)


def test_whitespace_quotes_and_case_differences_still_match(d024):
    q = _real_sentence(d024, "an owner of residential real property shall not")
    mangled = q.replace(" ", "  \n").replace("'", "’").upper()
    m = verify.find_span(d024, mangled)
    assert m and m.method in ("exact", "case")
    assert verify.normalize(m.text, True) == verify.normalize(q, True)


def test_small_typo_snaps_to_real_source_text(d024):
    q = _real_sentence(d024, "an owner of residential real property shall not", 200)
    typo = q.replace("residential", "residental", 1).replace("shall not", "shal not", 1)
    m = verify.find_span(d024, typo)
    assert m and m.method == "snap"
    assert m.text in d024  # stored text is real source text, not the model's typo


def test_fabricated_quote_is_rejected(d024):
    fake = "A landlord may increase rent by any amount without notice to the tenant whatsoever."
    assert verify.find_span(d024, fake) is None
    assert verify.find_span(d024, "too short") is None


def test_candidate_windows_suggest_the_right_passage(d024):
    paraphrase = "owners of residential property cannot raise the gross rental rate by more than 5 percent plus CPI"
    windows = verify.candidate_windows(d024, paraphrase)
    assert len(windows) == 3
    assert any("percent" in w for w in windows)


def test_verify_fields_and_failure_policy(d024):
    q = _real_sentence(d024, "an owner of residential real property shall not")
    cand = {
        "quoted_span": q,
        "effective_date": "2020-01-01",
        "effective_date_span": "This section shall become effective on the first day of the year 2099 forever.",
        "key_value_span": None,
        "coverage": {"coverage_span": None},
        "confidence": 0.9,
    }
    out, _log, failed = verify.verify_fields(cand, d024)
    assert failed == ["effective_date_span"]
    assert out["_offsets"]["quoted_span"][1] > out["_offsets"]["quoted_span"][0]
    final, _notes = verify.apply_failures(out, failed)
    assert final["effective_date"] is None and final["confidence"] == pytest.approx(0.7)
    dropped, _ = verify.apply_failures(out, ["quoted_span"])
    assert dropped is None
