"""A2 Verifier: every quote must be found in its source text, by code. Stored quotes are always the raw source text."""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz, process

CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "\u200b": "",
}  # fmt: skip

SNAP_THRESHOLD = 92
MIN_QUOTE_LEN = 20


def normalize_with_map(text: str, lower: bool = False) -> tuple[str, list[int]]:
    """Normalize quotes/dashes/whitespace/unicode; return (normalized, index map normalized->raw)."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True  # drops leading whitespace
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", CHAR_MAP.get(ch, ch)):
            c = CHAR_MAP.get(c, c)
            if not c:
                continue
            if c.isspace():
                if prev_space:
                    continue
                c, prev_space = " ", True
            else:
                prev_space = False
            out.append(c.lower() if lower else c)
            idx.append(i)
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize(text: str, lower: bool = False) -> str:
    return normalize_with_map(text, lower)[0]


@dataclass
class SpanMatch:
    start: int  # raw offsets into the body
    end: int
    method: str  # exact | case | snap
    score: float
    text: str  # the raw source substring (what we store)


def _raw(body: str, idx: list[int], s: int, e: int) -> tuple[int, int]:
    return idx[s], idx[e - 1] + 1


def find_span(body: str, quote: str) -> SpanMatch | None:
    if not quote or len(normalize(quote)) < MIN_QUOTE_LEN:
        return None
    for lower, method in ((False, "exact"), (True, "case")):
        nb, idx = normalize_with_map(body, lower)
        nq = normalize(quote, lower)
        pos = nb.find(nq)
        if pos >= 0:
            s, e = _raw(body, idx, pos, pos + len(nq))
            return SpanMatch(s, e, method, 100.0, body[s:e])
    nb, idx = normalize_with_map(body, True)
    nq = normalize(quote, True)
    al = fuzz.partial_ratio_alignment(nq, nb)
    if al and al.score >= SNAP_THRESHOLD:
        ds, de = al.dest_start, al.dest_end
        # widen to word boundaries so a snap never cuts a word
        while ds > 0 and nb[ds - 1] not in " ":
            ds -= 1
        while de < len(nb) and nb[de] not in " ":
            de += 1
        s, e = _raw(body, idx, ds, de)
        return SpanMatch(s, e, "snap", al.score, body[s:e])
    return None


_SENT_RE = re.compile(r"[^.;:\n]+(?:[.;:](?=\s)|\n|$)")


def candidate_windows(body: str, quote: str, k: int = 3) -> list[str]:
    """Top-k source sentences most similar to a failed quote, for the one repair round."""
    sentences = [m.group(0).strip() for m in _SENT_RE.finditer(body)]
    sentences = [s for s in sentences if len(s) >= MIN_QUOTE_LEN]
    # also consider pairs of adjacent sentences (quotes often span two)
    pairs = [f"{a} {b}" for a, b in itertools.pairwise(sentences)]
    hits = process.extract(quote, sentences + pairs, scorer=fuzz.token_set_ratio, limit=k)
    return [h[0] for h in hits]


QUOTE_FIELDS = ("quoted_span", "effective_date_span", "key_value_span")


def verify_fields(cand: dict, body: str) -> tuple[dict, list[dict], list[str]]:
    """Verify every quote field of a candidate rule against the body.

    Returns (updated candidate, log entries, list of failed field paths).
    Passing quotes are replaced by the raw source text and get offsets in cand["_offsets"].
    """
    cand = dict(cand)
    cov = dict(cand.get("coverage") or {})
    offsets: dict[str, list[int]] = dict(cand.get("_offsets") or {})
    log, failed = [], []
    fields = [(f, cand.get(f)) for f in QUOTE_FIELDS] + [("coverage.coverage_span", cov.get("coverage_span"))]
    for path, quote in fields:
        if not quote:
            continue
        m = find_span(body, quote)
        if m is None:
            failed.append(path)
            log.append({"field": path, "result": "fail", "quote": quote[:300]})
            continue
        if path == "coverage.coverage_span":
            cov["coverage_span"] = m.text
        else:
            cand[path] = m.text
        offsets[path] = [m.start, m.end]
        log.append({"field": path, "result": m.method, "score": round(m.score, 1)})
    if cov:
        cand["coverage"] = cov
    cand["_offsets"] = offsets
    return cand, log, failed


def apply_failures(cand: dict, failed: list[str]) -> tuple[dict | None, list[str]]:
    """After the repair round: drop the rule if its main quote failed; null optional fields that failed."""
    if "quoted_span" in failed:
        return None, ["dropped: quoted_span not found in source"]
    notes = []
    cand = dict(cand)
    for path in failed:
        if path == "effective_date_span":
            cand["effective_date_span"] = None
            cand["effective_date"] = None
            cand["confidence"] = max(0.0, (cand.get("confidence") or 0.8) - 0.2)
            notes.append("effective_date removed: no verifiable quote")
        elif path == "key_value_span":
            cand["key_value_span"] = None
            notes.append("key_value quote unverified")
        elif path == "coverage.coverage_span":
            cov = dict(cand.get("coverage") or {})
            cov["coverage_span"] = None
            cand["coverage"] = cov
            cand["confidence"] = max(0.0, (cand.get("confidence") or 0.8) - 0.1)
            notes.append("coverage quote unverified")
    return cand, notes
