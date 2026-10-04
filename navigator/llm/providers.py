"""Provider adapters behind one interface: complete_json(system, user, schema) -> dict.

Switch provider/model with LLM_PROVIDER / LLM_MODEL in .env. Each adapter uses the vendor's
official SDK and its native structured-output mode, then the caller validates with Pydantic.
"""

from __future__ import annotations

import copy
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel

from navigator import config


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


class LLMTruncated(LLMError):
    pass


@dataclass
class LLMResponse:
    data: dict
    model: str
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)


def strict_json_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema -> strict JSON schema (all properties required, no extra keys).

    Used for OpenAI-compatible json_schema mode and Gemini.
    """
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            node.pop("default", None)
            node.pop("title", None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


class Provider(ABC):
    name: str

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: type[BaseModel], max_tokens: int) -> LLMResponse: ...


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str):
        super().__init__(model)
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()

    def complete_json(self, system, user, schema, max_tokens):
        # Streaming avoids HTTP timeouts on long documents; output_format constrains the JSON.
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": config.llm_effort()},
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise LLMRefusal(f"refusal: {getattr(msg, 'stop_details', None)}")
        if msg.stop_reason == "max_tokens":
            raise LLMTruncated("hit max_tokens")
        parsed = getattr(msg, "parsed_output", None)
        if parsed is not None:
            data = parsed.model_dump(mode="json") if isinstance(parsed, BaseModel) else parsed
        else:
            text = next(b.text for b in msg.content if b.type == "text")
            data = json.loads(text)
        u = msg.usage
        usage = {
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        }
        return LLMResponse(data=data, model=msg.model, stop_reason=msg.stop_reason, usage=usage)


class OpenAICompatProvider(Provider):
    """OpenAI, Groq (open-weight models) and Ollama (local Llama) via the OpenAI SDK."""

    def __init__(self, model: str, name: str):
        super().__init__(model)
        import openai

        self.name = name
        if name == "groq":
            self.client = openai.OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")
        elif name == "ollama":
            self.client = openai.OpenAI(
                api_key="ollama", base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            )
        else:
            self.client = openai.OpenAI()

    def complete_json(self, system, user, schema, max_tokens):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if self.name == "openai":
            resp = self.client.chat.completions.parse(
                model=self.model, messages=messages, response_format=schema, max_completion_tokens=max_tokens
            )
            choice = resp.choices[0]
            if choice.message.refusal:
                raise LLMRefusal(choice.message.refusal)
            if choice.finish_reason == "length":
                raise LLMTruncated("hit max tokens")
            data = choice.message.parsed.model_dump(mode="json")
        else:
            # Groq / Ollama: JSON mode with the schema spelled out, validated by the caller.
            schema_text = json.dumps(strict_json_schema(schema))
            messages[0]["content"] = (
                f"{system}\n\nReturn ONLY a JSON object that validates against this JSON Schema:\n{schema_text}"
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            if choice.finish_reason == "length":
                raise LLMTruncated("hit max tokens")
            data = json.loads(choice.message.content)
        u = resp.usage
        usage = {"input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens} if u else {}
        return LLMResponse(data=data, model=resp.model, stop_reason=choice.finish_reason, usage=usage)


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, model: str):
        super().__init__(model)
        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    def complete_json(self, system, user, schema, max_tokens):
        import time

        from google.genai import errors

        cfg = self.types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=strict_json_schema(schema),
            max_output_tokens=max_tokens,
            automatic_function_calling=self.types.AutomaticFunctionCallingConfig(disable=True),
        )
        for attempt in range(5):  # the Gemini SDK does not retry 503s itself
            try:
                resp = self.client.models.generate_content(model=self.model, contents=user, config=cfg)
                break
            except errors.ServerError:
                if attempt == 4:
                    raise
                time.sleep(2**attempt * 2)
        cand = resp.candidates[0] if resp.candidates else None
        finish = str(cand.finish_reason) if cand and cand.finish_reason else None
        if finish and "MAX_TOKENS" in finish:
            raise LLMTruncated("hit max tokens")
        if finish and "SAFETY" in finish:
            raise LLMRefusal(finish)
        if not resp.text:
            raise LLMError(f"empty response, finish_reason={finish}")
        um = resp.usage_metadata
        usage = {"input_tokens": um.prompt_token_count, "output_tokens": um.candidates_token_count} if um else {}
        return LLMResponse(data=json.loads(resp.text), model=self.model, stop_reason=finish, usage=usage)


def get_provider(name: str | None = None, model: str | None = None) -> Provider:
    name = name or config.llm_provider()
    model = model or (config.llm_model() if name == config.llm_provider() else config.DEFAULT_MODELS[name])
    if name == "anthropic":
        return AnthropicProvider(model)
    if name == "gemini":
        return GeminiProvider(model)
    if name in ("openai", "groq", "ollama"):
        return OpenAICompatProvider(model, name)
    raise ValueError(f"unknown LLM_PROVIDER {name!r}; use anthropic | openai | gemini | groq | ollama")
