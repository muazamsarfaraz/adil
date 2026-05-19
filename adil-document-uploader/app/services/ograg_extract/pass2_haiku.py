"""OG-RAG extraction pass 2: Claude Haiku 4.5.

Per the OG-RAG migration spec (``docs/superpowers/specs/2026-05-19-og-rag-migration-design.md``)
this pass extracts the LLM-grounded slice of the ontology from a judgment's
paragraph text:

  * ``Topic`` nodes (closed vocabulary — see ``CLOSED_TOPIC_VOCAB``)
  * ``Party`` nodes (name + role)
  * ``Judge`` nodes (name)
  * ``Court`` node (deterministic from the case, no LLM)
  * ``has_topic``, ``judged_by``, ``heard_party`` edges (paragraph-attributed
    when the LLM picks them up inside a paragraph) plus ``decided_in_court``
    (case-level, deterministic).

Batching: 5 paragraphs per Anthropic API call. Few-shot prompt with three
hand-curated examples lives in ``_FEW_SHOT_EXAMPLES``. Cost target:
~$0.02/judgment with prompt-caching on the system + few-shot blocks (the
constant prefix is cache-eligible after the first call within a 5-minute
window, which is the typical backfill cadence).

Retry: exponential backoff (max 3 attempts) on 429 / 5xx. Pydantic schema
validation failures count as a retry. Idempotency key per call:
``(judgment_id, pass_version=2, batch_start_paragraph_idx)``.

The module exposes two entrypoints:

  * ``extract_pass2(judgment, result, *, client=None)`` — async function
    that mutates ``result`` in place with the new nodes/edges and returns
    a ``Pass2Stats`` value (cost, tokens, model, note) so the backfill
    orchestrator can write to ``extraction_spend``.
  * ``make_pass2_runner(client=None)`` — returns a ``PassRunner`` closure
    in the signature expected by ``ograg_backfill.BackfillConfig.pass2_runner``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.ograg_extract.pass1_structural import (
    CaseNode,
    CourtNode,
    Edge,
    ExtractionResult,
    JudgeNode,
    OGRAG_NAMESPACE,
    ParagraphNode,
    PartyNode,
    TopicNode,
    _node_id,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

# Lifted from the spec §5 and confirmed against ``solicitor_directory.py``
# topic enum in adil-rag-api. The LLM MUST pick from this set (schema
# enforces it); free-form topic strings are rejected.
CLOSED_TOPIC_VOCAB: tuple[str, ...] = (
    "discrimination_direct",
    "discrimination_indirect",
    "harassment",
    "victimisation",
    "immigration_asylum",
    "immigration_settlement",
    "employment_dismissal",
    "employment_pay",
    "deputyship",
    "court_of_protection",
    "hate_crime_racial",
    "hate_crime_religious",
    "human_rights_article8",
    "human_rights_article14",
    "mental_capacity_assessment",
    "mental_capacity_dols",
)

_TOPIC_VOCAB_SET = frozenset(CLOSED_TOPIC_VOCAB)

# Party role vocabulary. The LLM may emit anything in this set; an
# unrecognised role falls back to "other" so we still preserve the party
# without rejecting the whole batch.
_VALID_ROLES = frozenset({"appellant", "respondent", "claimant", "defendant", "intervener", "applicant", "other"})


# ---------------------------------------------------------------------------
# Cost model — Claude Haiku 4.5 pricing as of 2026-05-19
# ---------------------------------------------------------------------------

# USD per 1M tokens. Sourced from console.anthropic.com pricing page;
# review on each model upgrade. Cache-write is 25% more than base input;
# cache-read is 10% of base input.
_HAIKU_PRICE = {
    "input": 1.00,
    "cache_write": 1.25,
    "cache_read": 0.10,
    "output": 5.00,
}


def _estimate_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Convert an Anthropic ``usage`` block into a USD cost.

    Anthropic counts cache-write tokens against ``cache_creation_input_tokens``
    and cache-read against ``cache_read_input_tokens``; the regular
    ``input_tokens`` field is everything else. We sum the three at their
    respective rates.
    """
    return (
        input_tokens * _HAIKU_PRICE["input"]
        + cache_creation_input_tokens * _HAIKU_PRICE["cache_write"]
        + cache_read_input_tokens * _HAIKU_PRICE["cache_read"]
        + output_tokens * _HAIKU_PRICE["output"]
    ) / 1_000_000


# ---------------------------------------------------------------------------
# Pydantic schemas for the LLM response
# ---------------------------------------------------------------------------


class _ParagraphAnnotation(BaseModel):
    """Per-paragraph slice of the LLM output."""

    index: int = Field(description="0-based paragraph index within the batch")
    topics: list[str] = Field(default_factory=list)
    parties_mentioned: list[str] = Field(default_factory=list)
    judges_mentioned: list[str] = Field(default_factory=list)

    @field_validator("topics")
    @classmethod
    def _topics_in_vocab(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in _TOPIC_VOCAB_SET]
        if bad:
            raise ValueError(f"unknown topics: {bad!r}")
        # Dedupe preserving order.
        return list(dict.fromkeys(v))


class _PartyOut(BaseModel):
    name: str
    role: str = "other"

    @field_validator("role")
    @classmethod
    def _normalise_role(cls, v: str) -> str:
        return v.lower().strip() if v.lower().strip() in _VALID_ROLES else "other"

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("party name is empty")
        return v


class _BatchOut(BaseModel):
    """The schema Claude Haiku is asked to populate per batch."""

    judges: list[str] = Field(default_factory=list)
    parties: list[_PartyOut] = Field(default_factory=list)
    paragraphs: list[_ParagraphAnnotation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

_FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "user": (
            "CASE: [2018] UKSC 49 — Lee v Ashers Baking Co Ltd\n\n"
            "PARAGRAPHS:\n"
            "[0] This appeal concerns direct discrimination under the Equality Act 2010 on grounds of religion and belief.\n"
            "[1] Lord Hodge JSC delivered the principal judgment. Lady Black JSC agreed.\n"
            "[2] The appellant, Mr Lee, ordered a cake from Ashers Baking Co Ltd.\n"
        ),
        "assistant": {
            "judges": ["Lord Hodge JSC", "Lady Black JSC"],
            "parties": [
                {"name": "Lee", "role": "appellant"},
                {"name": "Ashers Baking Co Ltd", "role": "respondent"},
            ],
            "paragraphs": [
                {"index": 0, "topics": ["discrimination_direct"], "parties_mentioned": [], "judges_mentioned": []},
                {
                    "index": 1,
                    "topics": [],
                    "parties_mentioned": [],
                    "judges_mentioned": ["Lord Hodge JSC", "Lady Black JSC"],
                },
                {
                    "index": 2,
                    "topics": [],
                    "parties_mentioned": ["Lee", "Ashers Baking Co Ltd"],
                    "judges_mentioned": [],
                },
            ],
        },
    },
    {
        "user": (
            "CASE: [2014] UKSC 19 — P v Cheshire West and Chester Council\n\n"
            "PARAGRAPHS:\n"
            "[0] The question is whether the living arrangements of P, an adult with learning disabilities, amount to a deprivation of liberty under the Mental Capacity Act 2005.\n"
            "[1] Lady Hale gave the leading judgment.\n"
        ),
        "assistant": {
            "judges": ["Lady Hale"],
            "parties": [
                {"name": "P", "role": "appellant"},
                {"name": "Cheshire West and Chester Council", "role": "respondent"},
            ],
            "paragraphs": [
                {
                    "index": 0,
                    "topics": ["mental_capacity_dols", "court_of_protection"],
                    "parties_mentioned": ["P"],
                    "judges_mentioned": [],
                },
                {"index": 1, "topics": [], "parties_mentioned": [], "judges_mentioned": ["Lady Hale"]},
            ],
        },
    },
    {
        "user": (
            "CASE: [2021] EWCA Civ 1374 — Higgs v Farmor's School\n\n"
            "PARAGRAPHS:\n"
            "[0] The claimant alleged harassment and direct discrimination on grounds of religious belief.\n"
            "[1] The Employment Appeal Tribunal had considered indirect discrimination under section 19.\n"
            "[2] HHJ Smith presided in the tribunal below.\n"
        ),
        "assistant": {
            "judges": ["HHJ Smith"],
            "parties": [
                {"name": "Higgs", "role": "claimant"},
                {"name": "Farmor's School", "role": "respondent"},
            ],
            "paragraphs": [
                {
                    "index": 0,
                    "topics": ["harassment", "discrimination_direct"],
                    "parties_mentioned": [],
                    "judges_mentioned": [],
                },
                {"index": 1, "topics": ["discrimination_indirect"], "parties_mentioned": [], "judges_mentioned": []},
                {"index": 2, "topics": [], "parties_mentioned": [], "judges_mentioned": ["HHJ Smith"]},
            ],
        },
    },
]


_SYSTEM_PROMPT = """You are a UK legal information extractor.

For each batch you receive a case header and one or more numbered paragraphs from a judgment. Your job is to return a JSON object with three keys:

  * judges: a deduplicated list of every judge name mentioned across the batch (e.g. "Lord Hodge JSC", "Lady Black", "HHJ Smith"). Preserve the honorific.
  * parties: a deduplicated list of {name, role} for every legal party named. role MUST be one of: appellant, respondent, claimant, defendant, intervener, applicant, other.
  * paragraphs: a list of {index, topics, parties_mentioned, judges_mentioned} — one entry per input paragraph, in input order. ``index`` is the 0-based index within the batch.

Topics MUST come from this closed vocabulary (omit if none applies):
  discrimination_direct, discrimination_indirect, harassment, victimisation,
  immigration_asylum, immigration_settlement, employment_dismissal, employment_pay,
  deputyship, court_of_protection, hate_crime_racial, hate_crime_religious,
  human_rights_article8, human_rights_article14, mental_capacity_assessment, mental_capacity_dols.

Return ONLY valid JSON — no commentary, no Markdown fences. Use empty arrays when nothing applies."""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _format_paragraphs(batch: list[ParagraphNode]) -> str:
    """Render a batch into the ``[idx] text`` block format used in the prompt."""
    lines: list[str] = []
    for local_idx, paragraph in enumerate(batch):
        # Hard cap per paragraph to keep batch input under ~3k tokens.
        # Truncation is fine — Pass 1 already split on legal-paragraph
        # boundaries and the topic classifier doesn't need full opinions.
        text = paragraph.text.replace("\n", " ").strip()
        if len(text) > 1500:
            text = text[:1500] + "…"
        lines.append(f"[{local_idx}] {text}")
    return "\n".join(lines)


def _build_user_message(case: CaseNode, batch: list[ParagraphNode]) -> str:
    return f"CASE: {case.neutral_citation} — {case.case_name}\n\n" f"PARAGRAPHS:\n{_format_paragraphs(batch)}\n"


def _build_messages(case: CaseNode, batch: list[ParagraphNode]) -> list[dict[str, Any]]:
    """Build the ``messages`` list including 3-shot examples + the live batch."""
    messages: list[dict[str, Any]] = []
    for shot in _FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": shot["user"]})
        messages.append({"role": "assistant", "content": json.dumps(shot["assistant"])})
    messages.append({"role": "user", "content": _build_user_message(case, batch)})
    return messages


def _system_with_caching() -> list[dict[str, Any]]:
    """Anthropic prompt-caching system block.

    The system + few-shot prefix is identical across every batch in a
    backfill run, so marking the system block with ``cache_control``
    drops the per-call input cost to ~10% of the base price once the
    cache is warm (within the 5-minute TTL).
    """
    return [
        {
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]


# ---------------------------------------------------------------------------
# Retry + backoff
# ---------------------------------------------------------------------------


class HaikuExtractionError(Exception):
    """Raised when Haiku extraction exhausts retries on a batch."""


_MAX_ATTEMPTS = 3
_BASE_BACKOFF_S = 1.0


def _is_retryable(exc: BaseException) -> bool:
    """True for 429 / 5xx anthropic errors and our own pydantic-validation retry."""
    # Avoid a hard import of anthropic at module load — the library is an
    # optional production dep, present only on the worker service.
    name = type(exc).__name__
    if name in {"RateLimitError", "APIStatusError", "InternalServerError", "APIConnectionError", "APITimeoutError"}:
        return True
    if isinstance(exc, ValidationError):
        return True
    # Anthropic SDK raises status-specific errors but also a generic APIStatusError
    # whose ``status_code`` we can inspect when available.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    return False


async def _sleep_backoff(attempt: int) -> None:
    """Exponential backoff with jitter: 1s, 2s, 4s (±25% jitter)."""
    base = _BASE_BACKOFF_S * (2 ** (attempt - 1))
    jittered = base * (0.75 + 0.5 * random.random())
    await asyncio.sleep(jittered)


# ---------------------------------------------------------------------------
# Client + response parsing
# ---------------------------------------------------------------------------


def _default_client() -> Any:
    """Build a default ``AsyncAnthropic`` client from ``ANTHROPIC_API_KEY``.

    Deferred-imported so the module loads even when ``anthropic`` is not
    installed (e.g. in lightweight test environments that stub the client).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HaikuExtractionError(
            "ANTHROPIC_API_KEY not set — required for OG-RAG extraction pass 2 (Claude Haiku 4.5)"
        )
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:  # pragma: no cover — packaging guard
        raise HaikuExtractionError(f"anthropic SDK not installed: {exc}") from exc
    return AsyncAnthropic(api_key=api_key)


def _extract_response_text(response: Any) -> str:
    """Pull the JSON string out of an Anthropic ``Message`` response.

    Anthropic returns ``response.content`` as a list of content blocks; the
    first text block holds our JSON payload.
    """
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    raise HaikuExtractionError("Haiku response contained no text block")


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_payload(text: str) -> _BatchOut:
    """Strip any stray Markdown fence and parse + validate the payload."""
    cleaned = _JSON_FENCE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Surface as ValidationError so ``_is_retryable`` flags it.
        raise ValidationError.from_exception_data(  # type: ignore[call-arg]
            title="JSONDecode",
            line_errors=[{"type": "json_invalid", "loc": (), "input": cleaned[:200], "ctx": {"error": str(exc)}}],
        ) from exc
    return _BatchOut.model_validate(data)


# ---------------------------------------------------------------------------
# Idempotency keys
# ---------------------------------------------------------------------------

_PASS_VERSION = 2


def _idempotency_key(judgment_id: Any, batch_start_idx: int) -> uuid.UUID:
    """Stable per-(judgment, pass, batch) UUID.

    The orchestrator does not currently key on this in the DB (it keys on
    judgment-level extraction status), but the function is exported for
    callers that want batch-grained de-duplication on retries.
    """
    return uuid.uuid5(OGRAG_NAMESPACE, f"pass{_PASS_VERSION}:{judgment_id}:{batch_start_idx}")


# ---------------------------------------------------------------------------
# Deterministic node helpers
# ---------------------------------------------------------------------------


def _court_division_from_citation(neutral_citation: str) -> str | None:
    # Mirrors the regex from pass1_structural._NEUTRAL_CITATION but we only
    # care about the division here.
    m = re.search(
        r"\[(?P<year>\d{4})\]\s+(?:UKSC|UKHL|EWCA|EWHC|UKEAT)"
        r"(?:\s+(?P<division>Civ|Crim|Admin|Comm|Ch|Fam|TCC|Pat|QB|KB))?"
        r"\s+\d+(?:\s*\((?P<paren_div>Admin|Comm|Ch|Fam|TCC|Pat|QB|KB)\))?",
        neutral_citation,
    )
    if not m:
        return None
    return m.group("division") or m.group("paren_div")


def court_node_for(case: CaseNode) -> CourtNode:
    """Deterministic ``CourtNode`` for a case. Pure function — no LLM."""
    division = _court_division_from_citation(case.neutral_citation)
    key = f"{case.court}:{division}" if division else case.court
    return CourtNode(node_id=_node_id("court", key), code=case.court, division=division)


def _judge_node(name: str) -> JudgeNode:
    return JudgeNode(node_id=_node_id("judge", name.lower()), name=name)


def _party_node(name: str, role: str) -> PartyNode:
    role_norm = role.lower() if role.lower() in _VALID_ROLES else "other"
    # Party identity is name-only for dedupe (role may shift across paragraphs).
    return PartyNode(node_id=_node_id("party", name.lower()), name=name, role=role_norm)


def _topic_node(slug: str) -> TopicNode:
    return TopicNode(node_id=_node_id("topic", slug), slug=slug)


# ---------------------------------------------------------------------------
# Merging across batches
# ---------------------------------------------------------------------------


def _merge_batch(
    *,
    result: ExtractionResult,
    batch: list[ParagraphNode],
    parsed: _BatchOut,
    seen_judges: dict[str, JudgeNode],
    seen_parties: dict[str, PartyNode],
    seen_topics: dict[str, TopicNode],
) -> None:
    """Fold one parsed batch into the running ``result``.

    Mutates ``result`` and the caller-owned ``seen_*`` dicts so dedupe
    survives across batches in the same judgment.
    """
    # Case-level: judges and parties accumulate across the whole judgment.
    for raw_name in parsed.judges:
        name = raw_name.strip()
        if not name or name in seen_judges:
            continue
        node = _judge_node(name)
        seen_judges[name] = node
        result.judges.append(node)
        result.edges.append(Edge(kind="judged_by", source_id=result.case.node_id, target_id=node.node_id))

    for party in parsed.parties:
        if party.name in seen_parties:
            continue
        node = _party_node(party.name, party.role)
        seen_parties[party.name] = node
        result.parties.append(node)
        result.edges.append(Edge(kind="heard_party", source_id=result.case.node_id, target_id=node.node_id))

    # Per-paragraph: topic/heard_party/judged_by attribution.
    for annot in parsed.paragraphs:
        if annot.index < 0 or annot.index >= len(batch):
            logger.warning(
                "pass2_haiku: paragraph annotation index %d out of range (batch size=%d) — skipping",
                annot.index,
                len(batch),
            )
            continue
        paragraph = batch[annot.index]
        for slug in annot.topics:
            if slug not in seen_topics:
                seen_topics[slug] = _topic_node(slug)
                result.topics.append(seen_topics[slug])
            result.edges.append(
                Edge(
                    kind="has_topic",
                    source_id=result.case.node_id,
                    target_id=seen_topics[slug].node_id,
                    paragraph_id=paragraph.node_id,
                )
            )
        # Paragraph-attributed party mentions: tighten to existing parties only.
        for name in annot.parties_mentioned:
            node = seen_parties.get(name)
            if node is None:
                continue
            result.edges.append(
                Edge(
                    kind="heard_party",
                    source_id=result.case.node_id,
                    target_id=node.node_id,
                    paragraph_id=paragraph.node_id,
                )
            )
        for name in annot.judges_mentioned:
            node = seen_judges.get(name)
            if node is None:
                continue
            result.edges.append(
                Edge(
                    kind="judged_by",
                    source_id=result.case.node_id,
                    target_id=node.node_id,
                    paragraph_id=paragraph.node_id,
                )
            )


# ---------------------------------------------------------------------------
# Single-batch call
# ---------------------------------------------------------------------------


@dataclass
class _BatchCost:
    cost_usd: float
    input_tokens: int
    output_tokens: int


async def _call_one_batch(
    client: Any,
    *,
    model: str,
    case: CaseNode,
    batch: list[ParagraphNode],
    max_tokens: int,
) -> tuple[_BatchOut, _BatchCost]:
    """Issue one Haiku call with retry + backoff. Returns parsed payload + cost."""
    messages = _build_messages(case, batch)
    last_exc: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=_system_with_caching(),
                messages=messages,
            )
            text = _extract_response_text(response)
            parsed = _parse_json_payload(text)
            usage = getattr(response, "usage", None)
            cost = _BatchCost(
                cost_usd=_estimate_cost(
                    input_tokens=getattr(usage, "input_tokens", 0) or 0,
                    output_tokens=getattr(usage, "output_tokens", 0) or 0,
                    cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                ),
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )
            return parsed, cost
        except Exception as exc:  # noqa: BLE001 — retry policy lives here
            last_exc = exc
            if not _is_retryable(exc) or attempt == _MAX_ATTEMPTS:
                break
            logger.warning(
                "pass2_haiku: batch attempt %d/%d failed (%s); backing off",
                attempt,
                _MAX_ATTEMPTS,
                type(exc).__name__,
            )
            await _sleep_backoff(attempt)

    raise HaikuExtractionError(
        f"Haiku extraction failed after {_MAX_ATTEMPTS} attempts on case "
        f"{case.neutral_citation!r}: {type(last_exc).__name__}: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


@dataclass
class Pass2Stats:
    """Per-judgment summary returned by ``extract_pass2``."""

    cost_usd: float
    model: str
    input_tokens: int
    output_tokens: int
    batches: int
    paragraphs_processed: int


def _chunk(seq: list[ParagraphNode], size: int) -> Iterable[list[ParagraphNode]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def extract_pass2(
    judgment: Any,
    result: ExtractionResult,
    *,
    client: Any | None = None,
    model: str = "claude-haiku-4-5",
    batch_size: int = 5,
    max_tokens: int = 2048,
) -> Pass2Stats:
    """Run pass 2 on a judgment's already-extracted ``ExtractionResult``.

    Mutates ``result`` to add: ``court`` (deterministic), ``topics`` /
    ``parties`` / ``judges`` nodes (deduped), and ``edges`` for ``has_topic``,
    ``decided_in_court``, ``judged_by``, ``heard_party``.

    ``judgment`` is accepted only to surface ``id`` for idempotency keys
    and is otherwise unused (paragraph text comes from ``result``). It
    matches the ``PassRunner`` signature used by the backfill orchestrator.
    """
    if not result.paragraphs:
        # Nothing to send — still emit the deterministic Court node + edge so
        # the writer sees a complete pass-2 result for short judgments.
        result.court = court_node_for(result.case)
        result.edges.append(
            Edge(kind="decided_in_court", source_id=result.case.node_id, target_id=result.court.node_id)
        )
        return Pass2Stats(cost_usd=0.0, model=model, input_tokens=0, output_tokens=0, batches=0, paragraphs_processed=0)

    if client is None:
        client = _default_client()

    # Deterministic Court node + decided_in_court edge first — never costs anything,
    # so even a fully-failing LLM call still leaves a usable partial result.
    result.court = court_node_for(result.case)
    result.edges.append(Edge(kind="decided_in_court", source_id=result.case.node_id, target_id=result.court.node_id))

    seen_judges: dict[str, JudgeNode] = {}
    seen_parties: dict[str, PartyNode] = {}
    seen_topics: dict[str, TopicNode] = {}

    total_cost = 0.0
    total_in = 0
    total_out = 0
    batches = 0

    for batch in _chunk(result.paragraphs, batch_size):
        parsed, cost = await _call_one_batch(client, model=model, case=result.case, batch=batch, max_tokens=max_tokens)
        _merge_batch(
            result=result,
            batch=batch,
            parsed=parsed,
            seen_judges=seen_judges,
            seen_parties=seen_parties,
            seen_topics=seen_topics,
        )
        total_cost += cost.cost_usd
        total_in += cost.input_tokens
        total_out += cost.output_tokens
        batches += 1

    return Pass2Stats(
        cost_usd=total_cost,
        model=model,
        input_tokens=total_in,
        output_tokens=total_out,
        batches=batches,
        paragraphs_processed=len(result.paragraphs),
    )


# ---------------------------------------------------------------------------
# Backfill integration
# ---------------------------------------------------------------------------


def make_pass2_runner(
    *,
    client: Any | None = None,
    model: str = "claude-haiku-4-5",
    batch_size: int = 5,
    max_tokens: int = 2048,
):
    """Return a ``PassRunner`` closure matching ``ograg_backfill.PassRunner``.

    The orchestrator expects ``(judgment, result) -> (cost, model, in_tok,
    out_tok, note)``. We wrap ``extract_pass2`` and pack ``Pass2Stats`` into
    that tuple.
    """

    async def runner(
        judgment: Any, result: ExtractionResult
    ) -> tuple[float, str | None, int | None, int | None, str | None]:
        stats = await extract_pass2(
            judgment,
            result,
            client=client,
            model=model,
            batch_size=batch_size,
            max_tokens=max_tokens,
        )
        note = (
            f"batches={stats.batches} paragraphs={stats.paragraphs_processed} "
            f"topics={len(result.topics)} parties={len(result.parties)} "
            f"judges={len(result.judges)} edges={len(result.edges)}"
        )
        return stats.cost_usd, stats.model, stats.input_tokens, stats.output_tokens, note

    return runner
