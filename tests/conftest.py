"""Tests run against real services: a real SQLite database file, real LLM APIs, the real Census Geocoder.

No mocks. LLM and HTTP responses are cached in the test database, so reruns are cheap and replayable.
Tests needing a key are skipped when that key is absent.
"""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///data/test_navigator.db")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls a real external API (LLM or Census)")


def need_env(*names):
    missing = [n for n in names if not os.getenv(n)]
    return pytest.mark.skipif(bool(missing), reason=f"missing env: {', '.join(missing)}")
