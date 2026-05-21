"""P7 parity tests: OG-RAG path returns the same answer/viability/checklist
shape as the FST path, and is correctly routed for streaming + vision.

These tests are pure-offline: the Anthropic client and retriever are stubbed.
They lock in the contract — same 6-tuple from ``answer``, same SSE events
from ``answer_stream`` — so a future refactor can't silently regress
either path.

Vendor pivot (Phase 2, 2026-05-21): generation now uses Anthropic Claude
Sonnet via ``client.messages.create`` (unary) and ``client.messages.stream``
(SSE). Mocks reflect that shape.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.asyncio


# ---------- helpers ----------------------------------------------------


class _FakeAnthropicUsage:
    """Mirror anthropic.types.Usage shape."""

    input_tokens = 11
    output_tokens = 23


class _FakeTextBlock:
    """Mirror anthropic.types.TextBlock shape."""

    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeAnthropicResponse:
    """Mirror anthropic.types.Message (non-streaming)."""

    def __init__(self, text: str):
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeAnthropicUsage()


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


class _FakeAsyncAnthropicUnary:
    """Mocks ``AsyncAnthropic`` for the non-streaming path.

    Implements ``messages.create(...)`` as a coroutine returning a fake
    response. Captures the call kwargs for assertion.
    """

    def __init__(self, text: str):
        self._text = text
        self.captured: dict = {}

        async def _create(**kwargs):
            self.captured.update(kwargs)
            return _FakeAnthropicResponse(self._text)

        # nested namespace to mirror the real shape: client.messages.create(...)
        messages_ns = type("_Messages", (), {"create": staticmethod(_create)})()
        self.messages = messages_ns


# ---------- non-streaming answer parity --------------------------------


async def test_answer_returns_six_tuple_with_viability(monkeypatch):
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)
    fake_client = _FakeAsyncAnthropicUnary(_viability_block())
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

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

    # Usage / metadata populated from Anthropic usage shape
    assert usage.prompt_tokens == 11
    assert usage.completion_tokens == 23
    assert usage.total_tokens == 34
    assert metadata.model_used == "claude-sonnet-4-6"

    # The mocked client was called with the expected kwargs.
    assert fake_client.captured["model"] == "claude-sonnet-4-6"
    assert "system" in fake_client.captured
    assert isinstance(fake_client.captured["messages"], list)


async def test_answer_without_viability_returns_none_and_empty(monkeypatch):
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)
    fake_client = _FakeAsyncAnthropicUnary("Plain answer with no viability block.")
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

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


class _FakeAsyncAnthropicStream:
    """Mocks ``AsyncAnthropic`` for the streaming path.

    ``messages.stream(...)`` returns an async context manager exposing
    ``text_stream`` (async iterator of text deltas) and
    ``get_final_message()`` (coroutine returning a message with usage).
    """

    def __init__(self, text_pieces: list[str]):
        self._pieces = text_pieces
        self.captured: dict = {}

        outer = self

        class _Manager:
            async def __aenter__(self_mgr):
                async def _text_iter():
                    for p in outer._pieces:
                        yield p

                self_mgr.text_stream = _text_iter()

                async def _final():
                    # Mimic anthropic.types.Message with usage attached
                    msg = type("_Msg", (), {})()
                    msg.usage = _FakeAnthropicUsage()
                    return msg

                self_mgr.get_final_message = _final
                return self_mgr

            async def __aexit__(self_mgr, exc_type, exc, tb):
                return False

        def _stream_fn(**kwargs):
            outer.captured.update(kwargs)
            return _Manager()

        messages_ns = type("_Messages", (), {"stream": staticmethod(_stream_fn)})()
        self.messages = messages_ns


async def test_answer_stream_emits_expected_events(monkeypatch):
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)

    text_pieces = [
        "Direct discrimination ",
        "under s.13 ",
        "occurs when ...\n",
        _viability_block(),
    ]
    fake_client = _FakeAsyncAnthropicStream(text_pieces)
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    events: list[dict] = []
    async for ev in backend.answer_stream(
        "What is direct discrimination?",
        include_viability=True,
    ):
        events.append(ev)

    # 4 token events (one per piece) + 2 sources + 1 viability + 1 done.
    token_events = [e for e in events if e["event"] == "token"]
    source_events = [e for e in events if e["event"] == "source"]
    viability_events = [e for e in events if e["event"] == "viability"]
    done_events = [e for e in events if e["event"] == "done"]

    assert len(token_events) == 4
    assert len(source_events) == 2
    assert len(viability_events) == 1
    assert len(done_events) == 1

    # Tokens preserve order.
    assert [e["data"] for e in token_events] == text_pieces

    # Viability parsed from the streamed block.
    v = viability_events[0]["data"]
    assert v["score"] == 75
    assert v["statutory_footing"] is True
    assert v["evidence_checklist"] == ["payslips", "grievance letters", "HR investigation report"]

    # Done summary references both sources and the running token count.
    done = done_events[0]["data"]
    assert done["sources_count"] == 2
    assert done["tokens_used"] == 34

    # The mocked client received the expected kwargs.
    assert fake_client.captured["model"] == "claude-sonnet-4-6"
    assert isinstance(fake_client.captured["messages"], list)
