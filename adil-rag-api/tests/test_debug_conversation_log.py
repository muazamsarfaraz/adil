"""Tests for the gated raw conversation debug log."""

from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture
def reset_module(monkeypatch):
    """Reload conversation_log fresh so DEBUG_LOG_RAW picks up the env state."""

    def _reload(flag: str | None):
        if flag is None:
            monkeypatch.delenv("DEBUG_LOG_RAW", raising=False)
        else:
            monkeypatch.setenv("DEBUG_LOG_RAW", flag)
        import conversation_log

        return importlib.reload(conversation_log)

    return _reload


def test_default_off_skips_db(reset_module):
    """With no DEBUG_LOG_RAW env var, the function returns without touching the pool."""
    mod = reset_module(None)
    assert mod.DEBUG_LOG_RAW is False

    called = {"pool": 0}

    async def fake_pool():
        called["pool"] += 1
        return object()

    mod._get_pool = fake_pool  # type: ignore[attr-defined]
    asyncio.run(
        mod.log_conversation_raw(
            endpoint="query",
            conversation_id="00000000-0000-0000-0000-000000000000",
            query="test",
            response="hi",
        )
    )
    assert called["pool"] == 0, "DEBUG_LOG_RAW=0 must not even acquire the pool"


def test_explicit_zero_off(reset_module):
    mod = reset_module("0")
    assert mod.DEBUG_LOG_RAW is False


def test_flag_on_attempts_pool(reset_module):
    """With DEBUG_LOG_RAW=1, the function attempts to acquire the pool."""
    mod = reset_module("1")
    assert mod.DEBUG_LOG_RAW is True

    pool_calls = {"n": 0}

    async def fake_pool():
        pool_calls["n"] += 1
        return None  # simulate no DATABASE_URL — function should bail gracefully

    mod._get_pool = fake_pool  # type: ignore[attr-defined]
    asyncio.run(
        mod.log_conversation_raw(
            endpoint="query",
            query="test",
            response="hi",
        )
    )
    assert pool_calls["n"] == 1
