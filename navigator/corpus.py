"""A0 Ingest: load the corpus manifest and texts into the Source library table."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from navigator import config, db

HEADER_RE = re.compile(r"\ASOURCE:\s*(?P<url>\S+)\s*\nRETRIEVED:\s*(?P<ret>[^\n]*)\n\n?", re.MULTILINE)
SECTION_BREAK_RE = re.compile(r"\n(?=(?:Section|SECTION|§|Sec\.|\d+[.:]\s|[A-Z][A-Z ,'-]{6,}\n))")


def load_manifest(path: Path = config.MANIFEST) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split_header(raw: str) -> tuple[str, str | None]:
    """Return (body, retrieved) with the two-line SOURCE/RETRIEVED header removed. Body is never rewritten."""
    m = HEADER_RE.match(raw)
    if not m:
        return raw, None
    return raw[m.end() :], m.group("ret").strip()


def source_type(raw: str) -> str:
    raw = raw.lower()
    if raw.startswith("official"):
        return "official"
    if "code publisher" in raw:
        return "code_publisher"
    return "secondary"


def ingest(manifest_path: Path = config.MANIFEST, corpus_dir: Path = config.CORPUS_DIR) -> dict:
    rows = load_manifest(manifest_path)
    stats = {"total": 0, "with_text": 0, "sha_mismatch": 0}
    with db.session() as s:
        for r in rows:
            stats["total"] += 1
            has_text = r["status"] == "ok" and bool(r["text_file"])
            body, retrieved = None, r["retrieved_at"] or None
            if has_text:
                raw_bytes = (corpus_dir / r["text_file"]).read_bytes()
                if r["sha256"] and hashlib.sha256(raw_bytes).hexdigest() != r["sha256"]:
                    stats["sha_mismatch"] += 1  # manifest hash may be of the original capture, not the .txt
                body, header_ret = split_header(raw_bytes.decode("utf-8"))
                retrieved = retrieved or header_ret
                stats["with_text"] += 1
            s.merge(
                db.Source(
                    doc_id=r["doc_id"],
                    jurisdictions=[j.strip() for j in r["jurisdictions"].split(";") if j.strip()],
                    url=r["url"],
                    source_type=source_type(r["source_type"]),
                    retrieved_at=retrieved,
                    sha256=r["sha256"] or None,
                    has_text=has_text,
                    in_corpus=True,
                    body=body,
                    word_count=len(body.split()) if body else 0,
                )
            )
    db.audit("ingest", "done", None, **stats)
    return stats


@dataclass
class Chunk:
    index: int
    start: int  # char offset into the source body
    text: str


def chunk_body(body: str, max_words: int = 8000, overlap_words: int = 300) -> list[Chunk]:
    """Split long bodies at section-like boundaries into <= max_words chunks (with overlap). Offsets map to body."""
    if len(body.split()) <= max_words:
        return [Chunk(0, 0, body)]
    # candidate cut points: section breaks, else paragraph breaks
    cuts = sorted(
        {m.start() for m in SECTION_BREAK_RE.finditer(body)} | {m.start() for m in re.finditer(r"\n\n", body)}
    )
    word_starts = [m.start() for m in re.finditer(r"\S+", body)]
    chunks, start_word = [], 0
    while start_word < len(word_starts):
        end_word = min(start_word + max_words, len(word_starts))
        start_char = word_starts[start_word]
        if end_word >= len(word_starts):
            end_char = len(body)
        else:
            hard = word_starts[end_word]
            soft = [c for c in cuts if word_starts[start_word + max_words // 2] < c <= hard]
            end_char = soft[-1] if soft else hard
        chunks.append(Chunk(len(chunks), start_char, body[start_char:end_char]))
        if end_char >= len(body):
            break
        # next chunk starts overlap_words before the cut, on a word boundary
        next_word = next(i for i, w in enumerate(word_starts) if w >= end_char)
        start_word = max(next_word - overlap_words, start_word + 1)
    return chunks


def get_source(doc_id: str) -> db.Source | None:
    with db.session() as s:
        return s.get(db.Source, doc_id)
