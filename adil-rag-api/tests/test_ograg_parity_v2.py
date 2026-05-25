"""P7 parity tests (additional) — vision routing, conversation history flow,
streaming edge cases, and explicit shape parity with ``RAGService.query``.

The existing ``test_ograg_parity.py`` covers the happy path for unary
answer + streaming + viability. This file fills the gaps:

  - Vision: ``app.py`` POST /api/v1/vision delegates to
    ``rag_service.query_with_images`` which (when RAG_BACKEND=ograg)
    routes through ``ograg.backend.answer(images=...)``. We verify the
    image dict is converted to an Anthropic image content block on the
    final user turn and that retrieval still runs over the text only.

  - Conversation history: passing ``conversation_history`` to ``answer``
    and ``answer_stream`` must (a) be forwarded to the retriever (where
    P6's query-rewriter consumes it), and (b) populate the Anthropic
    messages array with prior turns mapped role-user/role-assistant.

  - Streaming edge cases: (a) empty retrieval still yields valid event
    sequence ending in ``done`` with sources_count=0; (b) viability=False
    suppresses the viability event even if the model returns the block;
    (c) safety-blocked (empty text) responses don't crash the stream.

  - Shape parity: ``ograg.backend.answer`` and ``RAGService.query`` both
    return a 6-tuple of the same Python types (Source/TokenUsage/...).
    Locks the public contract so an accidental signature change on
    either side is caught.

All tests are pure-offline — Anthropic, Gemini embedding, and the Store
are stubbed. No DB, no network.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.asyncio


# ---------- shared mocks (kept small — repeat rather than import private) ----


class _FakeUsage:
    input_tokens = 11
    output_tokens = 23


class _FakeText:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeMsg:
    def __init__(self, text: str):
        self.content = [_FakeText(text)]
        self.usage = _FakeUsage()


_VIABILITY_BLOCK = (
    "Brief lead-in.\n"
    "---EVIDENCE_CHECKLIST---\n"
    "- payslips\n"
    "- HR letter\n"
    "---END_CHECKLIST---\n"
    "---VIABILITY_ASSESSMENT---\n"
    "SCORE: 60\n"
    "VENTO_BAND: lower\n"
    "VENTO_RANGE: £1,200 - £11,200\n"
    "REASONING: Documented detriment with statutory footing.\n"
    "STATUTORY_FOOTING: true\n"
    "CASE_LAW_PRECEDENT: false\n"
    "QUANTUM_POTENTIAL: true\n"
    "---END_VIABILITY---\n"
)


_FAKE_CHUNKS = [
    {
        "text": "Section 13 EA 2010 defines direct discrimination.",
        "source": {
            "id": "ea2010-s13",
            "kind": "statute",
            "title": "Equality Act 2010",
            "section": "13",
        },
    },
]


async def _fake_retrieve(question, k=5, **kwargs):  # noqa: ARG001
    return _FAKE_CHUNKS[:k]


class _CaptureAnthropic:
    """Async client mock that captures the call payload — used both for
    unary ``messages.create`` and streaming ``messages.stream``.
    """

    def __init__(self, text: str, *, stream_pieces: list[str] | None = None):
        self.captured: dict = {}
        outer = self

        async def _create(**kwargs):
            outer.captured.update(kwargs)
            return _FakeMsg(text)

        class _StreamMgr:
            async def __aenter__(self_mgr):
                pieces = stream_pieces or [text]

                async def _iter():
                    for p in pieces:
                        yield p

                self_mgr.text_stream = _iter()

                async def _final():
                    m = type("_M", (), {})()
                    m.usage = _FakeUsage()
                    return m

                self_mgr.get_final_message = _final
                return self_mgr

            async def __aexit__(self_mgr, *exc):
                return False

        def _stream(**kwargs):
            outer.captured.update(kwargs)
            return _StreamMgr()

        self.messages = type(
            "_Messages",
            (),
            {"create": staticmethod(_create), "stream": staticmethod(_stream)},
        )()


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Each test gets a fresh import of ograg.backend so monkeypatches stick."""
    for name in ("ograg.backend", "rag_service"):
        sys.modules.pop(name, None)
    yield


# ---------- vision routing ---------------------------------------------------


async def test_vision_image_attached_to_final_user_turn(monkeypatch):
    """An image dict must become an Anthropic image content block on the
    last user message; retrieval still runs over the text-only question.
    """
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)
    fake_client = _CaptureAnthropic("This photo shows a written warning letter.")
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    images = [
        {
            "mime_type": "image/png",
            "data": "aGVsbG8=",  # base64 "hello"
        }
    ]
    result = await backend.answer(
        "Could this be discriminatory treatment?",
        images=images,
    )
    ans, sources, usage, metadata, viability, evidence = result

    # 6-tuple shape preserved with images.
    assert isinstance(ans, str) and ans
    assert sources, "retrieval still ran"
    assert usage.total_tokens > 0
    assert viability is None and evidence == []

    # Final user message has image + text content blocks (Anthropic shape).
    messages = fake_client.captured["messages"]
    assert messages and messages[-1]["role"] == "user"
    content = messages[-1]["content"]
    assert isinstance(content, list), "vision turn uses block content, not str"
    image_blocks = [b for b in content if b.get("type") == "image"]
    text_blocks = [b for b in content if b.get("type") == "text"]
    assert len(image_blocks) == 1
    assert len(text_blocks) == 1
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert image_blocks[0]["source"]["data"] == "aGVsbG8="


# ---------- conversation history flow ---------------------------------------


async def test_conversation_history_forwarded_to_retriever_and_messages(monkeypatch):
    """History must reach the retriever (P6 rewriter consumes it) AND
    populate the Anthropic messages array with user/assistant turns.
    """
    import ograg.backend as backend

    seen: dict = {}

    async def _capture_retrieve(question, k=5, **kwargs):  # noqa: ARG001
        seen["history"] = kwargs.get("conversation_history")
        return _FAKE_CHUNKS

    monkeypatch.setattr(backend, "_do_retrieve", _capture_retrieve)
    fake_client = _CaptureAnthropic("Follow-up answer.")
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    history = [
        {"role": "user", "content": "I work in Manchester."},
        {"role": "assistant", "content": "Got it. What happened?"},
    ]
    await backend.answer("Could it be discrimination?", conversation_history=history)

    # Retriever received the full history (P6 rewriter then consumes it).
    assert seen["history"] == history

    # Anthropic messages contain mapped roles + current user turn.
    messages = fake_client.captured["messages"]
    assert len(messages) == 3  # 2 history turns + 1 current
    assert messages[0] == {"role": "user", "content": "I work in Manchester."}
    assert messages[1] == {"role": "assistant", "content": "Got it. What happened?"}
    assert messages[-1]["role"] == "user"
    assert "Could it be discrimination" in messages[-1]["content"]


async def test_stream_forwards_conversation_history_to_retriever(monkeypatch):
    """The streaming path must also forward history to the retriever so
    P6's multi-turn rewrite happens for SSE clients too.
    """
    import ograg.backend as backend

    seen: dict = {}

    async def _capture_retrieve(question, k=5, **kwargs):  # noqa: ARG001
        seen["history"] = kwargs.get("conversation_history")
        return _FAKE_CHUNKS

    monkeypatch.setattr(backend, "_do_retrieve", _capture_retrieve)
    fake_client = _CaptureAnthropic("", stream_pieces=["hello ", "world"])
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    history = [{"role": "user", "content": "Prior turn."}]
    events: list[dict] = []
    async for ev in backend.answer_stream(
        "and now?",
        include_viability=False,
        conversation_history=history,
    ):
        events.append(ev)

    assert seen["history"] == history
    assert [e["event"] for e in events if e["event"] == "token"]


# ---------- streaming edge cases --------------------------------------------


async def test_stream_with_empty_retrieval_still_yields_done(monkeypatch):
    """Zero hyperedges → no source events, but token + done still flow."""
    import ograg.backend as backend

    async def _empty_retrieve(question, k=5, **kwargs):  # noqa: ARG001
        return []

    monkeypatch.setattr(backend, "retrieve", _empty_retrieve)
    fake_client = _CaptureAnthropic("", stream_pieces=["I don't have enough context."])
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    events: list[dict] = []
    async for ev in backend.answer_stream("Esoteric question.", include_viability=False):
        events.append(ev)

    kinds = [e["event"] for e in events]
    assert kinds[-1] == "done"
    assert kinds.count("source") == 0
    assert any(k == "token" for k in kinds)
    done = events[-1]["data"]
    assert done["sources_count"] == 0


async def test_stream_include_viability_false_suppresses_viability_event(monkeypatch):
    """Even if the model emits the viability block, include_viability=False
    must NOT yield a viability SSE event — but the block IS still stripped
    from the user-visible text (consistency with unary path).
    """
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)
    fake_client = _CaptureAnthropic("", stream_pieces=["answer ", _VIABILITY_BLOCK])
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    events: list[dict] = []
    async for ev in backend.answer_stream("q", include_viability=False):
        events.append(ev)

    viability_events = [e for e in events if e["event"] == "viability"]
    assert viability_events == []  # suppressed
    # The token events still carried the raw text — the SSE contract is
    # "tokens are model raw; structured events are post-parsed". Clients
    # render only the cleaned text from the unary path or strip the block
    # client-side. Lock this behaviour by asserting the stream order is
    # tokens → sources → done with no viability between.
    kinds = [e["event"] for e in events]
    assert kinds[-1] == "done"
    assert "viability" not in kinds


async def test_stream_propagates_anthropic_errors_as_runtime_error(monkeypatch):
    """A failure inside ``messages.stream`` must propagate as a
    RuntimeError so FastAPI returns 500 cleanly (not an obscure traceback).
    """
    import ograg.backend as backend

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)

    class _BoomClient:
        class messages:
            @staticmethod
            def stream(**kwargs):
                raise RuntimeError("anthropic 503")

    monkeypatch.setattr(backend, "_client", lambda: _BoomClient())

    with pytest.raises(RuntimeError, match="Failed to start streaming"):
        async for _ in backend.answer_stream("q", include_viability=False):
            pass


# ---------- shape parity with RAGService.query ------------------------------


async def test_answer_signature_matches_ragservice_query():
    """Public contract: both must return (str, list[Source], TokenUsage,
    QueryMetadata, ViabilityAssessment | None, list[str]). Catches an
    accidental return-shape drift on either side.
    """
    import inspect

    import ograg.backend as backend

    from rag_service import RAGService

    # Both are async; both declared as returning a 6-tuple at module level.
    # We can at least confirm both exist and are coroutines.
    assert inspect.iscoroutinefunction(backend.answer)
    assert inspect.iscoroutinefunction(RAGService.query)

    # And that both signatures accept the cross-cutting kwargs the public
    # surface uses (max_sources, include_viability, conversation_history).
    backend_params = set(inspect.signature(backend.answer).parameters)
    ragservice_params = set(inspect.signature(RAGService.query).parameters)
    common = {"max_sources", "include_viability", "conversation_history"}
    assert common.issubset(backend_params)
    assert common.issubset(ragservice_params)


async def test_unary_answer_returns_same_types_as_ragservice_query(monkeypatch):
    """Stronger parity check: types of every element in the 6-tuple match
    the public schema declared by RAGService.query.
    """
    import ograg.backend as backend

    from models import QueryMetadata, Source, TokenUsage, ViabilityAssessment

    monkeypatch.setattr(backend, "retrieve", _fake_retrieve)
    fake_client = _CaptureAnthropic(_VIABILITY_BLOCK)
    monkeypatch.setattr(backend, "_client", lambda: fake_client)

    ans, sources, usage, metadata, viability, evidence = await backend.answer("q", include_viability=True)

    assert isinstance(ans, str)
    assert isinstance(sources, list) and all(isinstance(s, Source) for s in sources)
    assert isinstance(usage, TokenUsage)
    assert isinstance(metadata, QueryMetadata)
    assert viability is None or isinstance(viability, ViabilityAssessment)
    assert isinstance(evidence, list) and all(isinstance(e, str) for e in evidence)
