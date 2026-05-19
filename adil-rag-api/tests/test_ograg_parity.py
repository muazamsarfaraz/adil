"""P7 parity tests: OG-RAG path returns the same answer/viability/checklist
shape as the FST path, and is correctly routed for streaming + vision.

These tests are pure-offline: the Gemini client and retriever are stubbed.
They lock in the contract — same 6-tuple from ``answer``, same SSE events
from ``answer_stream`` — so a future refactor can't silently regress
either path.
"""

from __future__ import annotations

import sys
import types as _types

import pytest

pytestmark = pytest.mark.asyncio


# ---------- helpers ----------------------------------------------------


class _FakeUsageMeta:
    prompt_token_count = 11
    candidates_token_count = 23
    total_token_count = 34


class _FakeResp:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = _FakeUsageMeta()


def _viability_block() -> str:
    return (
        "Some lead-in legal analysis referencing s.13.\n"
        "---EVIDENCE_CHECKLIST---\n"
        "- payslips\n"
        "- grievance letters\n"
        "- HR investigation report\n"
        "---END_CHECKLIST---\n"
        "---VIABILITY_ASSESSMENT---\n"
        "SCORE: 75\n"
        "VENTO_BAND: middle\n"
        "VENTO_RANGE: £11,200 - £33,700\n"
        "REASONING: Strong statutory footing under s.13 with documented detriment.\n"
        "STATUTORY_FOOTING: true\n"
        "CASE_LAW_PRECEDENT: true\n"
        "QUANTUM_POTENTIAL: true\n"
        "---END_VIABILITY---\n"
    )


_FAKE_CHUNKS = [
    {
        "text": "Section 13 of the Equality Act 2010 defines direct discrimination.",
        "source": {
            "id": "ea2010-s13",
            "kind": "statute",
            "title": "Equality Act 2010",
            "section": "13",
            "url": "https://www.legislation.gov.uk/ukpga/2010/15/section/13",
        },
    },
    {
        "text": "Harassment under s.26 covers unwanted conduct related to a protected characteristic.",
        "source": {
            "id": "ea2010-s26",
            "kind": "statute",
            "title": "Equality Act 2010",
            "section": "26",
        },
    },
]


async def _fake_retrieve(question, k=5):  # noqa: ARG001
    return _FAKE_CHUNKS[:k]


@pytest.fixture(autouse=True)
def _reset_modules():
    # Each test gets a fresh ograg.backend so monkeypatched retrieve sticks.
    for name in ("ograg.backend", "rag_service"):
        sys.modules.pop(name, None)
    yield


@pytest.fixture
def _stub_gemini_unary(monkeypatch):
    """Stub the unary Gemini call with a deterministic response."""
    import ograg.backend as backend  # noqa: WPS433 — late import for fresh module

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)

    def _fake_call_factory(text: str):
        def _call():
            return _FakeResp(text)

        return _call

    return backend, _fake_call_factory


# ---------- non-streaming answer parity --------------------------------


async def test_answer_returns_six_tuple_with_viability(monkeypatch):
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)

    # Patch the synchronous Gemini call inside answer() — the `_call` closure
    # is resolved by asyncio.to_thread, so we replace asyncio.to_thread for
    # that one path.
    async def _fake_to_thread(fn, *args, **kwargs):
        return _FakeResp(_viability_block())

    monkeypatch.setattr(backend.asyncio, "to_thread", _fake_to_thread)

    result = await backend.answer(
        "What is direct discrimination under the Equality Act 2010?",
        include_viability=True,
    )

    assert isinstance(result, tuple) and len(result) == 6
    ans, sources, usage, metadata, viability, evidence = result

    # Viability + evidence parsed from the block
    assert viability is not None
    assert viability.score == 75
    assert viability.statutory_footing is True
    assert evidence == ["payslips", "grievance letters", "HR investigation report"]

    # Block is stripped from the user-visible answer text
    assert "VIABILITY_ASSESSMENT" not in ans
    assert "EVIDENCE_CHECKLIST" not in ans
    assert "s.13" in ans or "section 13" in ans.lower() or len(ans) > 10

    # Sources come from retrieved chunks
    assert len(sources) == 2
    assert sources[0].title == "Equality Act 2010"
    assert sources[0].section == "13"

    # Usage / metadata populated
    assert usage.total_tokens == 11 + 23
    assert metadata.model_used == "gemini-2.5-flash"


async def test_answer_without_viability_returns_none_and_empty(monkeypatch):
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)

    async def _fake_to_thread(fn, *args, **kwargs):
        return _FakeResp("Plain answer with no viability block.")

    monkeypatch.setattr(backend.asyncio, "to_thread", _fake_to_thread)

    ans, sources, usage, metadata, viability, evidence = await backend.answer(
        "What is direct discrimination?",
        include_viability=False,
    )

    assert viability is None
    assert evidence == []
    assert "Plain answer" in ans
    assert sources  # retrieved chunks become sources regardless
    assert usage.total_tokens > 0
    assert metadata.processing_time_ms >= 0


# ---------- streaming parity -------------------------------------------


async def test_answer_stream_emits_expected_events(monkeypatch):
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)

    # Build a fake streaming iterator yielding token chunks then a final
    # chunk that carries usage_metadata.
    text_pieces = [
        "Direct discrimination ",
        "under s.13 ",
        "occurs when ...\n",
        _viability_block(),
    ]

    class _Chunk:
        def __init__(self, text=None, usage=None):
            self.text = text
            self.usage_metadata = usage

    chunks_to_yield = [_Chunk(text=p) for p in text_pieces]
    chunks_to_yield.append(_Chunk(usage=_FakeUsageMeta()))

    class _FakeStream:
        def __init__(self, items):
            self._iter = iter(items)

        def __iter__(self):
            return self._iter

    async def _fake_to_thread(fn, *args, **kwargs):
        # First call: kick off the stream. Subsequent calls: next chunk.
        # The backend uses to_thread for both `_start_stream` and `_next_chunk`.
        return fn(*args, **kwargs)

    monkeypatch.setattr(backend.asyncio, "to_thread", _fake_to_thread)

    # Patch _client().models.generate_content_stream to return our fake.
    class _FakeModels:
        def generate_content_stream(self, *, model, contents, config):  # noqa: ARG002
            return _FakeStream(chunks_to_yield)

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(backend, "_client", lambda: _FakeClient())

    events = []
    async for ev in backend.answer_stream(
        "What is direct discrimination?",
        include_viability=True,
    ):
        events.append(ev)

    event_types = [e["event"] for e in events]
    # Tokens stream first, then sources, then viability, then done
    assert event_types.count("token") == len(text_pieces)
    assert event_types[-1] == "done"
    assert "source" in event_types
    assert "viability" in event_types

    # Viability event payload includes the merged evidence_checklist
    viability_event = next(e for e in events if e["event"] == "viability")
    assert viability_event["data"]["score"] == 75
    assert viability_event["data"]["evidence_checklist"] == [
        "payslips",
        "grievance letters",
        "HR investigation report",
    ]

    # Source events are typed dicts (model_dump output)
    source_events = [e for e in events if e["event"] == "source"]
    assert len(source_events) == 2
    assert source_events[0]["data"]["title"] == "Equality Act 2010"

    done = events[-1]["data"]
    assert done["sources_count"] == 2
    assert done["tokens_used"] == 34


# ---------- RAG_BACKEND routing for stream + vision --------------------


async def test_stream_query_routes_to_ograg_when_flag_set(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND", "ograg")

    # Stub ograg.backend.answer_stream BEFORE rag_service is imported by the
    # routing branch.
    fake_mod = _types.ModuleType("ograg.backend")
    yielded = [
        {"event": "token", "data": "hello"},
        {"event": "done", "data": {"sources_count": 0, "tokens_used": 5}},
    ]

    async def _fake_stream(question, **kwargs):  # noqa: ARG001
        for ev in yielded:
            yield ev

    fake_mod.answer_stream = _fake_stream

    # Also stub answer so stream_query's caller won't pull the real module.
    async def _unused_answer(*a, **kw):  # noqa: ARG001
        raise AssertionError("answer must not be called on a stream route")

    fake_mod.answer = _unused_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_mod)

    from rag_service import RAGService

    service = RAGService(gemini_api_key="test-key", file_search_store_id="test-store")

    # If FST path runs we'll explode here (no real client).
    out = []
    async for ev in service.stream_query("any question", include_viability_score=True):
        out.append(ev)

    assert out == yielded


async def test_query_with_images_routes_to_ograg_when_flag_set(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND", "ograg")

    from models import QueryMetadata, TokenUsage

    sentinel = (
        "OG-RAG vision answer.",
        [],
        TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3, estimated_cost_usd=0.0),
        QueryMetadata(original_language="en", processing_time_ms=12, model_used="gemini-2.5-flash"),
        None,
        [],
    )

    called = {"ok": False}

    fake_mod = _types.ModuleType("ograg.backend")

    async def _fake_answer(question, **kwargs):
        called["ok"] = True
        # images must be forwarded
        assert kwargs.get("images") == [{"mime_type": "image/png", "data": "AAA"}]
        return sentinel

    fake_mod.answer = _fake_answer
    monkeypatch.setitem(sys.modules, "ograg.backend", fake_mod)

    from rag_service import RAGService

    service = RAGService(gemini_api_key="test-key", file_search_store_id="test-store")

    result = await service.query_with_images(
        images=[{"mime_type": "image/png", "data": "AAA"}],
        query_text="What does this show?",
        include_viability=False,
    )

    assert called["ok"] is True
    assert result == sentinel
