"""Paths and settings. Settings are read from the environment on each call so tests can override them."""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)

STARTER = ROOT / "starter"
CORPUS_DIR = STARTER / "corpus"
MANIFEST = CORPUS_DIR / "corpus_manifest.csv"
ADDRESSES_CSV = STARTER / "data" / "sample_addresses.csv"
RULE_SCHEMA = STARTER / "schema" / "rule_record.schema.json"
CHANGE_TESTS = STARTER / "dev" / "change_tests.json"
OUTPUT_DIR = ROOT / "output"
SUPPLEMENTARY_DIR = ROOT / "supplementary"

AS_OF_DEFAULT = date(2026, 10, 1)
PROMPT_VERSION = "v1"

CATEGORIES = [
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-5",
    "gemini": "gemini-flash-latest",
    "groq": "openai/gpt-oss-120b",
    "ollama": "llama3.3",
}


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or "sqlite:///data/navigator.db"
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        # relative sqlite paths resolve against the project root
        url = "sqlite:///" + str(ROOT / url.removeprefix("sqlite:///"))
    return url


def llm_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()


def llm_model() -> str:
    return (os.getenv("LLM_MODEL") or "").strip() or DEFAULT_MODELS[llm_provider()]


def llm_effort() -> str:
    return (os.getenv("LLM_EFFORT") or "high").strip()


def max_parallel() -> int:
    return int(os.getenv("LLM_MAX_PARALLEL") or 4)


def offline() -> bool:
    return os.getenv("NAVIGATOR_OFFLINE", "0") == "1"
