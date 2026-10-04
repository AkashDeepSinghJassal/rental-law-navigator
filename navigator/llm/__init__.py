"""Cached, audited structured calls. Every model call goes through `structured()`."""

from __future__ import annotations

import hashlib
import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from navigator import config, db
from navigator.llm.providers import LLMError, LLMRefusal, LLMTruncated, get_provider

T = TypeVar("T", bound=BaseModel)

__all__ = ["CacheMiss", "LLMError", "LLMRefusal", "LLMTruncated", "call_hash", "structured"]


class CacheMiss(LLMError):
    pass


def call_hash(provider: str, model: str, stage: str, system: str, user: str, schema: type[BaseModel]) -> str:
    payload = json.dumps(
        [provider, model, config.PROMPT_VERSION, stage, system, user, schema.model_json_schema()],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def structured(
    stage: str,
    system: str,
    user: str,
    schema: type[T],
    *,
    ref: str | None = None,
    max_tokens: int = 32000,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[T, str]:
    """Return (validated object, call_hash). Cached in the database by a hash of all inputs."""
    provider = provider or config.llm_provider()
    model = model or (config.llm_model() if provider == config.llm_provider() else config.DEFAULT_MODELS[provider])
    h = call_hash(provider, model, stage, system, user, schema)

    with db.session() as s:
        hit = s.get(db.LLMCall, h)
        if hit is not None:
            return schema.model_validate_json(hit.response_json), h
    if config.offline():
        raise CacheMiss(f"offline and no cached response for {stage} {ref}")

    client = get_provider(provider, model)
    resp = client.complete_json(system, user, schema, max_tokens)
    try:
        obj = schema.model_validate(resp.data)
    except ValidationError as e:
        # one repair round: show the model its validation errors
        db.audit(stage, "schema_retry", ref, errors=str(e)[:2000])
        resp = client.complete_json(
            system,
            f"{user}\n\nYour previous JSON failed validation:\n{str(e)[:2000]}\nReturn corrected JSON only.",
            schema,
            max_tokens,
        )
        obj = schema.model_validate(resp.data)

    with db.session() as s:
        s.merge(
            db.LLMCall(
                call_hash=h,
                stage=stage,
                provider=provider,
                model=resp.model or model,
                prompt_version=config.PROMPT_VERSION,
                ref=ref,
                response_json=obj.model_dump_json(),
                usage=resp.usage,
                stop_reason=resp.stop_reason,
            )
        )
    db.audit(stage, "llm_call", ref, provider=provider, model=resp.model or model, usage=resp.usage, call_hash=h)
    return obj, h
