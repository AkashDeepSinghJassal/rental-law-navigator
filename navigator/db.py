"""Knowledge base and caches, stored in a real SQL database (SQLite by default, any SQLAlchemy URL)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from navigator import config


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Source(Base):
    """Source library: one row per corpus (or supplementary) document."""

    __tablename__ = "sources"
    doc_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    jurisdictions: Mapped[list] = mapped_column(JSON)
    url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str | None] = mapped_column(String(64))
    has_text: Mapped[bool] = mapped_column(Boolean)
    in_corpus: Mapped[bool] = mapped_column(Boolean, default=True)
    body: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)


class LLMCall(Base):
    """Every model call: cache (by hash) and audit record."""

    __tablename__ = "llm_calls"
    call_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(16))
    ref: Mapped[str | None] = mapped_column(String(128))
    response_json: Mapped[str] = mapped_column(Text)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Candidate(Base):
    """Rule candidates from the extractor, with their verification outcome."""

    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(32), index=True)
    chunk: Mapped[int] = mapped_column(Integer, default=0)
    call_hash: Mapped[str] = mapped_column(String(64))
    jurisdiction: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_log: Mapped[list] = mapped_column(JSON, default=list)


class KBVersion(Base):
    __tablename__ = "kb_versions"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Rule(Base):
    """Final rules, snapshotted per knowledge-base version."""

    __tablename__ = "rules"
    kb_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_rule_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    jurisdiction: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class NoRuleFinding(Base):
    __tablename__ = "no_rule_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_version: Mapped[int] = mapped_column(Integer, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class Address(Base):
    __tablename__ = "addresses"
    address_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    raw: Mapped[dict] = mapped_column(JSON)
    facts: Mapped[dict] = mapped_column(JSON)
    stack: Mapped[dict | None] = mapped_column(JSON)


class HttpCache(Base):
    """Cached external HTTP responses (Census Geocoder)."""

    __tablename__ = "http_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stage: Mapped[str] = mapped_column(String(32), index=True)
    ref: Mapped[str | None] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


@lru_cache(maxsize=8)
def _engine(url: str):
    if url.startswith("sqlite:///"):
        from pathlib import Path

        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    Base.metadata.create_all(engine)
    return engine


def engine():
    return _engine(config.database_url())


@contextmanager
def session() -> Iterator[Session]:
    s = sessionmaker(bind=engine(), expire_on_commit=False)()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def audit(stage: str, decision: str, ref: str | None = None, **detail: Any) -> None:
    with session() as s:
        s.add(AuditEvent(stage=stage, decision=decision, ref=ref, detail=json.loads(json.dumps(detail, default=str))))


def latest_kb_version() -> int | None:
    with session() as s:
        return s.scalar(select(KBVersion.version).order_by(KBVersion.version.desc()).limit(1))
