"""Tests for OG-RAG extraction pass 2 (Claude Haiku 4.5).

Two suites:

* **Unit** — prompt building, schema validation, retry/backoff, cost
  calculation, merge logic, idempotency. Uses a hand-rolled fake client
  (no anthropic SDK required).
* **Integration** — one real Anthropic API call against fixture 1. Skipped
  automatically when ``ANTHROPIC_API_KEY`` is unset (CI / local dev).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.ograg_extract import (
    CLOSED_TOPIC_VOCAB,
    CourtNode,
    ExtractionResult,
    HaikuExtractionError,
    extract_pass1,
    extract_pass2,
    make_pass2_runner,
)
from app.services.ograg_extract.pass1_structural import _node_id
from app.services.ograg_extract.pass2_haiku import (
    _BatchOut,
    _build_messages,
    _build_user_message,
    _estimate_cost,
    _FEW_SHOT_EXAMPLES,
    _HAIKU_PRICE,
    _idempotency_key,
    _is_retryable,
    _parse_json_payload,
    _PASS_VERSION,
    _ParagraphAnnotation,
    _PartyOut,
    _system_with_caching,
    _VALID_ROLES,
    court_node_for,
)


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 50
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Resp:
    content: list[_Block]
    usage: _Usage


class _FakeMessages:
    def __init__(self, payloads: list[Any]) -> None:
        # ``payloads`` may contain either a dict (success) or an Exception
        # instance (raised on that call). Calls are consumed in order.
        self.payloads = list(payloads)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Resp:
        self.calls.append(kwargs)
        if not self.payloads:
            raise AssertionError("FakeMessages: no more queued responses")
        nxt = self.payloads.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        if isinstance(nxt, _Resp):
            return nxt
        # Plain dict → wrap as a normal success response.
        return _Resp(content=[_Block(text=json.dumps(nxt))], usage=_Usage())


class _FakeClient:
    def __init__(self, payloads: list[Any]) -> None:
        self.messages = _FakeMessages(payloads)


# ---------------------------------------------------------------------------
# Test fixture: an already-extracted ExtractionResult from pass 1
# ---------------------------------------------------------------------------


@dataclass
class _FakeJudgment:
    id: uuid.UUID
    neutral_citation: str
    case_name: str
    court: str
    judgment_date: date | None
    clean_text: str


@pytest.fixture
def judgment_lee() -> _FakeJudgment:
    return _FakeJudgment(
        id=uuid.UUID("99999999-9999-9999-9999-999999999999"),
        neutral_citation="[2018] UKSC 49",
        case_name="Lee v Ashers Baking Co Ltd",
        court="UKSC",
        judgment_date=date(2018, 10, 10),
        clean_text=(
            "1. This appeal concerns direct discrimination under the Equality Act 2010.\n\n"
            "2. The appellant relied on section 13 and section 19 of that Act.\n\n"
            "3. The court considered s.29(1) and s.29(2)(a) in detail.\n\n"
            "4. Reference was also made to the Human Rights Act 1998, in particular s.6.\n"
        ),
    )


@pytest.fixture
def result_lee(judgment_lee: _FakeJudgment) -> ExtractionResult:
    return extract_pass1(judgment_lee)


# ---------------------------------------------------------------------------
# Closed vocabulary
# ---------------------------------------------------------------------------


def test_closed_topic_vocab_matches_spec() -> None:
    """The spec calls out these 16 topics; lock the set to spot accidental edits."""
    assert "discrimination_direct" in CLOSED_TOPIC_VOCAB
    assert "mental_capacity_dols" in CLOSED_TOPIC_VOCAB
    assert "court_of_protection" in CLOSED_TOPIC_VOCAB
    assert len(CLOSED_TOPIC_VOCAB) == 16
    assert len(set(CLOSED_TOPIC_VOCAB)) == 16  # no dupes


def test_valid_party_roles_contains_expected() -> None:
    assert {"appellant", "respondent", "claimant", "defendant", "other"} <= _VALID_ROLES


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def test_few_shot_examples_count_is_three() -> None:
    """Spec requires 3 hand-curated examples; protect against accidental deletion."""
    assert len(_FEW_SHOT_EXAMPLES) == 3


def test_few_shot_assistant_examples_validate_against_schema() -> None:
    """Each few-shot answer must itself pass pydantic — otherwise we've
    taught Haiku to emit invalid JSON."""
    for shot in _FEW_SHOT_EXAMPLES:
        _BatchOut.model_validate(shot["assistant"])


def test_system_message_uses_prompt_caching() -> None:
    system = _system_with_caching()
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # Closed vocab must be embedded so the model can self-check.
    assert "discrimination_direct" in system[0]["text"]
    assert "mental_capacity_dols" in system[0]["text"]


def test_build_user_message_includes_citation_and_paragraphs(
    result_lee: ExtractionResult,
) -> None:
    batch = result_lee.paragraphs[:2]
    text = _build_user_message(result_lee.case, batch)
    assert "[2018] UKSC 49" in text
    assert "Lee v Ashers Baking Co Ltd" in text
    assert "[0]" in text and "[1]" in text


def test_build_messages_has_few_shot_pairs_then_live_batch(
    result_lee: ExtractionResult,
) -> None:
    """Anthropic chat format: user/assistant/user/assistant/... — 3 shots = 6 messages,
    plus the live batch user message = 7 total."""
    msgs = _build_messages(result_lee.case, result_lee.paragraphs[:1])
    assert len(msgs) == 7
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[-1]["role"] == "user"
    # Each assistant turn is valid JSON of the expected shape.
    for i in (1, 3, 5):
        _BatchOut.model_validate(json.loads(msgs[i]["content"]))


def test_build_user_message_truncates_overlong_paragraphs(
    judgment_lee: _FakeJudgment,
) -> None:
    """Per-paragraph hard cap at ~1500 chars keeps prompt size bounded."""
    judgment_lee.clean_text = "1. " + ("x" * 4000)
    result = extract_pass1(judgment_lee)
    text = _build_user_message(result.case, result.paragraphs)
    # 1500 chars + ellipsis + framing; well below the raw 4000.
    assert len(text) < 2000


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_paragraph_annotation_rejects_unknown_topic() -> None:
    with pytest.raises(ValidationError):
        _ParagraphAnnotation(index=0, topics=["totally_made_up_topic"])


def test_paragraph_annotation_dedupes_topics() -> None:
    annot = _ParagraphAnnotation(
        index=0,
        topics=["discrimination_direct", "discrimination_direct", "harassment"],
    )
    assert annot.topics == ["discrimination_direct", "harassment"]


def test_party_out_normalises_unknown_role_to_other() -> None:
    p = _PartyOut(name="Acme Ltd", role="bystander")
    assert p.role == "other"


def test_party_out_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        _PartyOut(name="   ", role="appellant")


def test_parse_json_payload_strips_markdown_fence() -> None:
    raw = '```json\n{"judges": [], "parties": [], "paragraphs": []}\n```'
    parsed = _parse_json_payload(raw)
    assert parsed.judges == []


def test_parse_json_payload_raises_on_invalid_json() -> None:
    with pytest.raises(ValidationError):
        _parse_json_payload("{not valid json")


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------


def test_estimate_cost_haiku_base_input_output() -> None:
    # 1M input @ $1 + 1M output @ $5 = $6
    cost = _estimate_cost(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(6.0)


def test_estimate_cost_with_cache_read_drops_per_call_cost() -> None:
    """Cache-read tokens are billed at 10% of base input."""
    full_input = _estimate_cost(input_tokens=10_000, output_tokens=500)
    cached_input = _estimate_cost(input_tokens=500, output_tokens=500, cache_read_input_tokens=9_500)
    assert cached_input < full_input
    # And the difference is meaningful (cache-read is 10x cheaper).
    assert cached_input < full_input * 0.6


def test_haiku_pricing_constants_match_published_rates() -> None:
    """Catch accidental edits to pricing constants — review on each model upgrade."""
    assert _HAIKU_PRICE["input"] == 1.0
    assert _HAIKU_PRICE["output"] == 5.0
    assert _HAIKU_PRICE["cache_read"] == 0.10
    assert _HAIKU_PRICE["cache_write"] == 1.25


# ---------------------------------------------------------------------------
# Court node (deterministic, no LLM)
# ---------------------------------------------------------------------------


def test_court_node_for_uksc(result_lee: ExtractionResult) -> None:
    court = court_node_for(result_lee.case)
    assert court.code == "UKSC"
    assert court.division is None
    # ID is deterministic on the (code, division) key.
    assert court.node_id == _node_id("court", "UKSC")


def test_court_node_for_ewca_division(judgment_lee: _FakeJudgment) -> None:
    judgment_lee.neutral_citation = "[2021] EWCA Civ 1374"
    judgment_lee.court = "EWCA"
    result = extract_pass1(judgment_lee)
    court = court_node_for(result.case)
    assert court.code == "EWCA"
    assert court.division == "Civ"


def test_court_node_for_ewhc_admin_parenthesised(judgment_lee: _FakeJudgment) -> None:
    judgment_lee.neutral_citation = "[2015] EWHC 2493 (Admin)"
    judgment_lee.court = "EWHC"
    result = extract_pass1(judgment_lee)
    court = court_node_for(result.case)
    assert court.code == "EWHC"
    assert court.division == "Admin"


# ---------------------------------------------------------------------------
# Idempotency keys
# ---------------------------------------------------------------------------


def test_idempotency_key_deterministic() -> None:
    jid = uuid.UUID("99999999-9999-9999-9999-999999999999")
    assert _idempotency_key(jid, 0) == _idempotency_key(jid, 0)
    assert _idempotency_key(jid, 0) != _idempotency_key(jid, 5)


def test_pass_version_is_two() -> None:
    """Locked at 2 — schema migrations on the spend ledger depend on it."""
    assert _PASS_VERSION == 2


# ---------------------------------------------------------------------------
# Retry classification
# ---------------------------------------------------------------------------


class _FakeRateLimit(Exception):
    pass


_FakeRateLimit.__name__ = "RateLimitError"


class _FakeStatusErr(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


def test_is_retryable_429() -> None:
    assert _is_retryable(_FakeStatusErr(429)) is True


def test_is_retryable_500() -> None:
    assert _is_retryable(_FakeStatusErr(503)) is True


def test_is_retryable_4xx_other_is_not() -> None:
    """A 400/401 is permanent — don't retry indefinitely on bad input/auth."""
    assert _is_retryable(_FakeStatusErr(400)) is False
    assert _is_retryable(_FakeStatusErr(401)) is False


def test_is_retryable_named_rate_limit_error() -> None:
    """The Anthropic SDK class name match path."""

    class RateLimitError(Exception):
        pass

    assert _is_retryable(RateLimitError("limit"))


def test_is_retryable_pydantic_validation_error() -> None:
    try:
        _ParagraphAnnotation(index=0, topics=["bogus"])
    except ValidationError as exc:
        assert _is_retryable(exc)


def test_is_retryable_runtime_error_not_retried() -> None:
    assert _is_retryable(RuntimeError("boom")) is False


# ---------------------------------------------------------------------------
# extract_pass2 — happy path with fake client
# ---------------------------------------------------------------------------


def _ok_payload_for_lee() -> dict[str, Any]:
    """A valid response shape for the 4-paragraph Lee fixture."""
    return {
        "judges": ["Lord Hodge JSC", "Lady Black JSC"],
        "parties": [
            {"name": "Lee", "role": "appellant"},
            {"name": "Ashers Baking Co Ltd", "role": "respondent"},
        ],
        "paragraphs": [
            {"index": 0, "topics": ["discrimination_direct"], "parties_mentioned": [], "judges_mentioned": []},
            {"index": 1, "topics": [], "parties_mentioned": ["Lee"], "judges_mentioned": []},
            {"index": 2, "topics": [], "parties_mentioned": [], "judges_mentioned": []},
            {"index": 3, "topics": [], "parties_mentioned": [], "judges_mentioned": []},
        ],
    }


async def test_extract_pass2_emits_court_topics_parties_judges_edges(
    judgment_lee: _FakeJudgment,
    result_lee: ExtractionResult,
) -> None:
    client = _FakeClient([_ok_payload_for_lee()])
    stats = await extract_pass2(judgment_lee, result_lee, client=client)

    # Court is deterministic + decided_in_court edge present.
    assert isinstance(result_lee.court, CourtNode)
    assert result_lee.court.code == "UKSC"
    assert any(e.kind == "decided_in_court" for e in result_lee.edges)

    # Topics: one TopicNode, one paragraph-attributed has_topic edge.
    assert [t.slug for t in result_lee.topics] == ["discrimination_direct"]
    topic_edges = [e for e in result_lee.edges if e.kind == "has_topic"]
    assert len(topic_edges) == 1
    assert topic_edges[0].paragraph_id == result_lee.paragraphs[0].node_id

    # Parties + judges nodes exist with case-level edges.
    assert {p.name for p in result_lee.parties} == {"Lee", "Ashers Baking Co Ltd"}
    assert {j.name for j in result_lee.judges} == {"Lord Hodge JSC", "Lady Black JSC"}
    assert sum(1 for e in result_lee.edges if e.kind == "judged_by" and e.paragraph_id is None) == 2
    assert sum(1 for e in result_lee.edges if e.kind == "heard_party" and e.paragraph_id is None) == 2

    # Stats sanity.
    assert stats.batches == 1
    assert stats.paragraphs_processed == 4
    assert stats.cost_usd > 0
    assert stats.model == "claude-haiku-4-5"


async def test_extract_pass2_batches_in_groups_of_five(
    judgment_lee: _FakeJudgment,
) -> None:
    # Build a 12-paragraph judgment so we get three batches at size 5.
    judgment_lee.clean_text = "\n\n".join(f"{i+1}. Paragraph body {i+1}." for i in range(12))
    result = extract_pass1(judgment_lee)

    empty_payload: dict[str, Any] = {"judges": [], "parties": [], "paragraphs": []}
    client = _FakeClient([empty_payload, empty_payload, empty_payload])
    stats = await extract_pass2(judgment_lee, result, client=client, batch_size=5)
    assert stats.batches == 3
    assert len(client.messages.calls) == 3


async def test_extract_pass2_retries_on_429_then_succeeds(
    judgment_lee: _FakeJudgment, result_lee: ExtractionResult
) -> None:
    err = _FakeStatusErr(429)
    client = _FakeClient([err, _ok_payload_for_lee()])
    stats = await extract_pass2(judgment_lee, result_lee, client=client)
    assert stats.batches == 1
    # First failed, second succeeded ⇒ 2 underlying API calls for 1 batch.
    assert len(client.messages.calls) == 2


async def test_extract_pass2_raises_after_max_attempts(
    judgment_lee: _FakeJudgment, result_lee: ExtractionResult
) -> None:
    client = _FakeClient([_FakeStatusErr(503), _FakeStatusErr(503), _FakeStatusErr(503)])
    with pytest.raises(HaikuExtractionError):
        await extract_pass2(judgment_lee, result_lee, client=client)
    # Three attempts before raising — no fourth call.
    assert len(client.messages.calls) == 3


async def test_extract_pass2_does_not_retry_4xx_other(
    judgment_lee: _FakeJudgment, result_lee: ExtractionResult
) -> None:
    client = _FakeClient([_FakeStatusErr(400)])
    with pytest.raises(HaikuExtractionError):
        await extract_pass2(judgment_lee, result_lee, client=client)
    # 400 is permanent — exactly one call, no retries.
    assert len(client.messages.calls) == 1


async def test_extract_pass2_dedupes_parties_across_batches(
    judgment_lee: _FakeJudgment,
) -> None:
    judgment_lee.clean_text = "\n\n".join(f"{i+1}. p." for i in range(10))
    result = extract_pass1(judgment_lee)
    batch1 = {
        "judges": ["Lord X"],
        "parties": [{"name": "Acme", "role": "appellant"}],
        "paragraphs": [],
    }
    batch2 = {
        "judges": ["Lord X", "Lady Y"],
        "parties": [{"name": "Acme", "role": "respondent"}, {"name": "Beta", "role": "respondent"}],
        "paragraphs": [],
    }
    client = _FakeClient([batch1, batch2])
    await extract_pass2(judgment_lee, result, client=client, batch_size=5)
    assert sorted(p.name for p in result.parties) == ["Acme", "Beta"]
    assert sorted(j.name for j in result.judges) == ["Lady Y", "Lord X"]


async def test_extract_pass2_emits_court_even_when_no_paragraphs(
    judgment_lee: _FakeJudgment,
) -> None:
    """A judgment with no extractable paragraphs still gets the deterministic
    Court node + decided_in_court edge — keeps the writer's invariant happy."""
    judgment_lee.clean_text = ""
    result = ExtractionResult(case=extract_pass1(_judgment_with_min_text(judgment_lee)).case)
    # No client provided, but should not be called either.
    stats = await extract_pass2(judgment_lee, result, client=_FakeClient([]))
    assert stats.batches == 0
    assert isinstance(result.court, CourtNode)
    assert any(e.kind == "decided_in_court" for e in result.edges)


def _judgment_with_min_text(j: _FakeJudgment) -> _FakeJudgment:
    j2 = _FakeJudgment(
        id=j.id,
        neutral_citation=j.neutral_citation,
        case_name=j.case_name,
        court=j.court,
        judgment_date=j.judgment_date,
        clean_text="1. Stub.",
    )
    return j2


async def test_make_pass2_runner_matches_backfill_signature(
    judgment_lee: _FakeJudgment, result_lee: ExtractionResult
) -> None:
    """The runner closure must return ``(cost, model, in, out, note)`` so the
    backfill orchestrator can write its spend ledger row."""
    runner = make_pass2_runner(client=_FakeClient([_ok_payload_for_lee()]))
    cost, model, in_tok, out_tok, note = await runner(judgment_lee, result_lee)
    assert isinstance(cost, float) and cost > 0
    assert model == "claude-haiku-4-5"
    assert in_tok and in_tok > 0
    assert out_tok and out_tok > 0
    assert "batches=1" in note
    assert "topics=1" in note


async def test_extract_pass2_paragraph_index_out_of_range_logged_not_raised(
    judgment_lee: _FakeJudgment, result_lee: ExtractionResult
) -> None:
    """If Haiku hallucinates a paragraph index past the batch, the merger
    logs and skips that annotation instead of crashing the whole batch."""
    payload = {
        "judges": [],
        "parties": [],
        "paragraphs": [
            {"index": 999, "topics": ["discrimination_direct"], "parties_mentioned": [], "judges_mentioned": []}
        ],
    }
    client = _FakeClient([payload])
    await extract_pass2(judgment_lee, result_lee, client=client)
    # No has_topic edge written (the offending annotation was skipped).
    assert not any(e.kind == "has_topic" for e in result_lee.edges)


def test_default_client_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.services.ograg_extract.pass2_haiku import _default_client

    with pytest.raises(HaikuExtractionError):
        _default_client()


# ---------------------------------------------------------------------------
# Integration test — single live call (skipped without ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


# Live API tests are opt-in via RUN_LIVE_API_TESTS=1 — a stray Claude Code
# billing key in ANTHROPIC_API_KEY is not a valid console.anthropic.com key
# (see CLAUDE.md guidance), so we require an explicit signal instead of
# autodetecting from the presence of the env var.
_RUN_LIVE = os.getenv("RUN_LIVE_API_TESTS") == "1" and bool(os.getenv("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not _RUN_LIVE, reason="RUN_LIVE_API_TESTS!=1; integration test skipped")
@pytest.mark.asyncio
async def test_integration_extract_pass2_against_lee(judgment_lee: _FakeJudgment, result_lee: ExtractionResult) -> None:
    """End-to-end against the real Anthropic API on fixture 1.

    Assertions are conservative — Haiku's exact output is non-deterministic,
    so we only assert that the response is shape-valid and the expected
    discrimination topic shows up somewhere. Cost is asserted under a
    generous ceiling that flags ~5x cost regressions.
    """
    stats = await extract_pass2(judgment_lee, result_lee)

    assert stats.batches >= 1
    assert isinstance(result_lee.court, CourtNode)
    # At least one of the expected discrimination topics should be present.
    topic_slugs = {t.slug for t in result_lee.topics}
    assert {"discrimination_direct", "discrimination_indirect", "harassment"} & topic_slugs

    # Sanity: at least one party node, at least one edge of each emitted kind.
    assert len(result_lee.parties) >= 1
    kinds_emitted = {e.kind for e in result_lee.edges}
    assert "decided_in_court" in kinds_emitted

    # Cost ceiling: ~$0.02/judgment target; flag if a single short fixture
    # blew past 5x that.
    assert stats.cost_usd < 0.10, f"cost regression: ${stats.cost_usd:.4f}"
