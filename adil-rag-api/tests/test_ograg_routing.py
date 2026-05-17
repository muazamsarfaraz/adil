"""Routing test: RAG_BACKEND env flag selects between FST and OG-RAG paths.

Verifies that:
- Unset / 'fst' → existing Gemini File Search Tool path is used.
- 'ograg'       → ograg.backend.answer is called, FST helpers are NOT touched.

Both code paths are mocked so the test runs offline.
"""

import sys

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("RAG_BACKEND", raising=False)
    yield


async def _instantiate_service():
    # Lazy import to ensure module-level state is fresh.
    if "rag_service" in sys.modules:
        del sys.modules["rag_service"]
    from rag_service import RAGService

    return RAGService(gemini_api_key="test-key", file_search_store_id="test-store")


async def test_unset_backend_uses_fst_path(monkeypatch):
    service = await _instantiate_service()

    called = {"fst": False}

    async def _fake_generate(*args, **kwargs):
        called["fst"] = True

        class _Resp:
            text = "FST answer about discrimination."
            usage_metadata = type("U", (), {"prompt_token_count": 5, "candidates_token_count": 7})()

        return _Resp()

    # Patch the asyncio.to_thread wrapper used by query() so we intercept
    # the FST call without needing real Gemini.
    import asyncio as _asyncio

    import rag_service as _rs

    orig_to_thread = _asyncio.to_thread

    async def _patched_to_thread(fn, *args, **kwargs):
        return await _fake_generate(fn, *args, **kwargs)

    monkeypatch.setattr(_rs.asyncio, "to_thread", _patched_to_thread)

    # Should NOT route to ograg
    async def _explode(*a, **kw):
        raise AssertionError("ograg.backend.answer must not be called when RAG_BACKEND is unset")

    monkeypatch.setitem(sys.modules, "ograg.backend", type(sys)("ograg.backend"))
    sys.modules["ograg.backend"].answer = _explode

    result = await service.query(query_text="What is direct discrimination?", max_sources=3)

    assert called["fst"] is True
    assert isinstance(result, tuple) and len(result) == 6
    assert "FST answer" in result[0]

    # restore (safety; monkeypatch will undo too)
    _asyncio.to_thread = orig_to_thread


async def test_ograg_backend_routes_to_ograg(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND", "ograg")
    service = await _instantiate_service()

    from models import QueryMetadata, TokenUsage

    sentinel = (
        "OG-RAG answer mentioning section 13.",
        [],
        TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3, estimated_cost_usd=0.0),
        QueryMetadata(original_language="en", processing_time_ms=12, model_used="gemini-2.5-flash"),
        None,
        [],
    )

    called = {"ograg": False, "fst": False}

    async def _fake_ograg_answer(question, **kwargs):
        called["ograg"] = True
        assert kwargs.get("max_sources") == 4
        assert kwargs.get("include_viability") is False
        return sentinel

    # Inject a fake ograg.backend module BEFORE query() imports it.
    fake_mod = type(sys)("ograg.backend")
    fake_mod.answer = _fake_ograg_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_mod)

    # Sentinel for the FST path: it must NOT be reached.
    import rag_service as _rs

    async def _patched_to_thread(fn, *args, **kwargs):
        called["fst"] = True
        raise AssertionError("FST path must not run when RAG_BACKEND=ograg")

    monkeypatch.setattr(_rs.asyncio, "to_thread", _patched_to_thread)

    result = await service.query(query_text="What is direct discrimination?", max_sources=4)

    assert called["ograg"] is True
    assert called["fst"] is False
    assert result == sentinel
