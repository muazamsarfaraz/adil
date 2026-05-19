"""P9 shadow tests.

Verifies the critical guarantees:
1. RAG_SHADOW unset / "0" → shadow does NOT fire.
2. RAG_SHADOW=1 + FST live path → shadow fires fire-and-forget.
3. RAG_BACKEND=ograg → shadow does NOT fire (user already gets OG-RAG).
4. Shadow OG-RAG raising must NOT affect the user FST response.
5. Shadow DB insert failure must NOT affect the user FST response.
6. Timeout in shadow is swallowed.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("RAG_BACKEND", raising=False)
    monkeypatch.delenv("RAG_SHADOW", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield


def _purge_modules():
    for name in ("rag_service", "ograg.shadow", "ograg.backend"):
        sys.modules.pop(name, None)


async def _instantiate_service():
    _purge_modules()
    from rag_service import RAGService

    return RAGService(gemini_api_key="test-key", file_search_store_id="test-store")


def _patch_fst_to_return(monkeypatch, text="FST answer about discrimination."):
    """Replace asyncio.to_thread used inside rag_service.query for the Gemini call."""
    import rag_service as _rs

    class _Resp:
        text = "INIT"
        usage_metadata = type("U", (), {"prompt_token_count": 5, "candidates_token_count": 7})()

    _Resp.text = text

    async def _patched_to_thread(fn, *args, **kwargs):
        return _Resp()

    monkeypatch.setattr(_rs.asyncio, "to_thread", _patched_to_thread)


# ----------------------------------------------------------------------------
# shadow_enabled flag
# ----------------------------------------------------------------------------


async def test_shadow_disabled_by_default(monkeypatch):
    _purge_modules()
    from ograg.shadow import shadow_enabled

    assert shadow_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
async def test_shadow_enabled_truthy(monkeypatch, value):
    monkeypatch.setenv("RAG_SHADOW", value)
    _purge_modules()
    from ograg.shadow import shadow_enabled

    assert shadow_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
async def test_shadow_disabled_falsy(monkeypatch, value):
    monkeypatch.setenv("RAG_SHADOW", value)
    _purge_modules()
    from ograg.shadow import shadow_enabled

    assert shadow_enabled() is False


# ----------------------------------------------------------------------------
# Live query() integration
# ----------------------------------------------------------------------------


async def test_shadow_does_not_fire_when_disabled(monkeypatch):
    """RAG_SHADOW unset → fire_and_forget_shadow returns without scheduling."""
    service = await _instantiate_service()
    _patch_fst_to_return(monkeypatch, "FST answer.")

    # Inject fake ograg.backend that explodes if called.
    fake_backend = type(sys)("ograg.backend")

    async def _explode_answer(*a, **kw):
        raise AssertionError("ograg.backend.answer must NOT be called when RAG_SHADOW unset")

    fake_backend.answer = _explode_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_backend)

    answer, *_ = await service.query(query_text="What is direct discrimination?", max_sources=3)
    assert "FST answer" in answer


async def test_shadow_fires_when_enabled(monkeypatch):
    """RAG_SHADOW=1 → ograg.backend.answer is invoked in background."""
    monkeypatch.setenv("RAG_SHADOW", "1")
    service = await _instantiate_service()
    _patch_fst_to_return(monkeypatch, "FST answer.")

    fire_event = asyncio.Event()
    captured = {}

    async def _record_answer(question, **kwargs):
        captured["question"] = question
        captured["kwargs"] = kwargs
        fire_event.set()
        from models import QueryMetadata, TokenUsage

        return (
            "shadow OG-RAG answer",
            [],
            TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3, estimated_cost_usd=0.0),
            QueryMetadata(original_language="en", processing_time_ms=5, model_used="gemini-2.5-flash"),
            None,
            [],
        )

    fake_backend = type(sys)("ograg.backend")
    fake_backend.answer = _record_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_backend)

    # Stub out DB insert so we don't need a real Postgres.
    from ograg import shadow as _shadow

    async def _noop_insert(**kw):
        return None

    monkeypatch.setattr(_shadow, "_insert_row", _noop_insert)

    answer, *_ = await service.query(query_text="What is direct discrimination?", max_sources=3)
    assert "FST answer" in answer

    # Yield once to let the fire-and-forget task run.
    await asyncio.wait_for(fire_event.wait(), timeout=2.0)
    assert captured["question"] == "What is direct discrimination?"
    assert captured["kwargs"].get("max_sources") == 3


async def test_shadow_does_not_fire_when_backend_is_ograg(monkeypatch):
    """If RAG_BACKEND=ograg the user already gets OG-RAG; no shadow needed."""
    monkeypatch.setenv("RAG_BACKEND", "ograg")
    monkeypatch.setenv("RAG_SHADOW", "1")
    service = await _instantiate_service()

    calls = {"count": 0}

    async def _record_answer(question, **kwargs):
        calls["count"] += 1
        from models import QueryMetadata, TokenUsage

        return (
            "ograg live answer",
            [],
            TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3, estimated_cost_usd=0.0),
            QueryMetadata(original_language="en", processing_time_ms=5, model_used="gemini-2.5-flash"),
            None,
            [],
        )

    fake_backend = type(sys)("ograg.backend")
    fake_backend.answer = _record_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_backend)

    await service.query(query_text="q", max_sources=3)
    # Let any (incorrectly) scheduled shadow task drain.
    await asyncio.sleep(0.05)

    # Exactly one call — the live OG-RAG; no second shadow call.
    assert calls["count"] == 1


# ----------------------------------------------------------------------------
# Failure isolation
# ----------------------------------------------------------------------------


async def test_shadow_raise_does_not_break_user_response(monkeypatch, caplog):
    """If ograg.backend.answer raises, the FST user response must still succeed."""
    import logging as _logging

    monkeypatch.setenv("RAG_SHADOW", "1")
    service = await _instantiate_service()
    _patch_fst_to_return(monkeypatch, "FST resilient answer.")

    async def _explode(*a, **kw):
        raise RuntimeError("simulated OG-RAG failure")

    fake_backend = type(sys)("ograg.backend")
    fake_backend.answer = _explode
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_backend)

    # Capture warnings emitted by the shadow path.
    caplog.set_level(_logging.WARNING, logger="ograg.shadow")

    # Should NOT raise.
    answer, *_ = await service.query(query_text="hello", max_sources=2)
    assert "FST resilient answer" in answer

    # Give the shadow task time to run through its except path.
    deadline_msgs = "ograg shadow failed"
    for _ in range(30):
        if any(deadline_msgs in r.getMessage() for r in caplog.records):
            break
        await asyncio.sleep(0.02)

    matched = [r for r in caplog.records if "ograg shadow failed" in r.getMessage()]
    assert matched, "expected shadow to log the OG-RAG failure as a warning"
    assert "simulated OG-RAG failure" in matched[0].getMessage()


async def test_shadow_db_insert_failure_is_swallowed(monkeypatch):
    """If eval_run insert fails, the FST user response must still succeed."""
    monkeypatch.setenv("RAG_SHADOW", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid:invalid@127.0.0.1:1/nope")
    service = await _instantiate_service()
    _patch_fst_to_return(monkeypatch, "FST still ok.")

    async def _ok_answer(question, **kwargs):
        from models import QueryMetadata, TokenUsage

        return (
            "shadow answer",
            [],
            TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3, estimated_cost_usd=0.0),
            QueryMetadata(original_language="en", processing_time_ms=5, model_used="gemini-2.5-flash"),
            None,
            [],
        )

    fake_backend = type(sys)("ograg.backend")
    fake_backend.answer = _ok_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_backend)

    # User response must not be affected even though the DB connection will fail.
    answer, *_ = await service.query(query_text="hello", max_sources=2)
    assert "FST still ok" in answer
    # Drain background task — should also not raise.
    await asyncio.sleep(0.1)


async def test_shadow_timeout_is_swallowed(monkeypatch):
    """A hung OG-RAG call must not pile up; timeout caps it."""
    monkeypatch.setenv("RAG_SHADOW", "1")
    _purge_modules()
    from ograg import shadow as _shadow

    monkeypatch.setattr(_shadow, "SHADOW_TIMEOUT_SECONDS", 0.05)

    async def _hang(*a, **kw):
        await asyncio.sleep(10)  # would block forever within the test

    fake_backend = type(sys)("ograg.backend")
    fake_backend.answer = _hang
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_backend)

    inserted = {"args": None}

    async def _capture_insert(**kw):
        inserted["args"] = kw

    monkeypatch.setattr(_shadow, "_insert_row", _capture_insert)

    _shadow.fire_and_forget_shadow("q", max_sources=1)

    for _ in range(30):
        if inserted["args"] is not None:
            break
        await asyncio.sleep(0.02)

    assert inserted["args"] is not None
    assert "timeout" in (inserted["args"]["error"] or "")
