"""A0 ingest against the real starter-pack corpus and the real database."""

from sqlalchemy import func, select

from navigator import corpus, db


def test_ingest_real_corpus():
    stats = corpus.ingest()
    assert stats["total"] == 87
    assert stats["with_text"] == 54
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(db.Source)) >= 87
        d024 = s.get(db.Source, "D024")
        assert d024.has_text and d024.source_type == "official"
        assert not d024.body.startswith("SOURCE:")
        assert "1947.12" in d024.body
        assert d024.jurisdictions == ["CA"]
        d032 = s.get(db.Source, "D032")  # Hoboken ecode360, link-only
        assert not d032.has_text and d032.body is None and d032.source_type == "code_publisher"
        berkeley = s.get(db.Source, "D001")
        assert berkeley.jurisdictions == ["Berkeley, CA"]


def test_chunking_offsets_map_back_to_body():
    corpus.ingest()
    d067 = corpus.get_source("D067")  # ~26k words: must chunk
    chunks = corpus.chunk_body(d067.body)
    assert len(chunks) >= 4
    for c in chunks:
        assert d067.body[c.start : c.start + len(c.text)] == c.text
        assert len(c.text.split()) <= 8000
    # chunks cover the whole body
    assert chunks[0].start == 0
    assert chunks[-1].start + len(chunks[-1].text) == len(d067.body)
    # small docs are one chunk
    assert len(corpus.chunk_body(corpus.get_source("D080").body)) == 1
