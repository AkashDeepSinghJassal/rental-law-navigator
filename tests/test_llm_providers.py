"""Live tests of the provider-neutral LLM layer against each configured vendor."""

import os
from typing import Literal

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select

from navigator import db
from navigator.llm import CacheMiss, structured

SYSTEM = "You extract facts from a short legal sentence. Copy quotes verbatim."
USER = (
    'Text: "A landlord shall not demand or receive security for a rental agreement in an amount '
    "or value in excess of an amount equal to one month's rent.\" Extract the cap."
)


class Cap(BaseModel):
    category: Literal["security_deposits", "rent_increase_limits", "other"]
    key_value: str
    quoted_span: str
    months: float | None


def _check(obj: Cap):
    assert obj.category == "security_deposits"
    assert obj.months == 1
    assert "one month" in obj.quoted_span


@pytest.mark.live
@pytest.mark.parametrize(
    "provider,env",
    [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("groq", "GROQ_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
    ],
)
def test_provider_structured_output_and_cache(provider, env):
    if not os.getenv(env):
        pytest.skip(f"{env} not set")
    obj, h = structured("test", SYSTEM, USER, Cap, ref=f"test-{provider}", max_tokens=8000, provider=provider)
    _check(obj)
    with db.session() as s:
        n_before = s.scalar(select(func.count()).select_from(db.LLMCall))
    obj2, h2 = structured("test", SYSTEM, USER, Cap, ref=f"test-{provider}", max_tokens=8000, provider=provider)
    with db.session() as s:
        n_after = s.scalar(select(func.count()).select_from(db.LLMCall))
    assert h == h2 and obj2 == obj and n_before == n_after  # second call served from the DB cache


def test_offline_mode_raises_on_cache_miss(monkeypatch):
    monkeypatch.setenv("NAVIGATOR_OFFLINE", "1")
    with pytest.raises(CacheMiss):
        structured("test", SYSTEM, USER + " (uncached variant)", Cap, provider="anthropic")
