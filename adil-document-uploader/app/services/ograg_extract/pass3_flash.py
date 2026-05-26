"""OG-RAG extraction pass 3: Gemini Flash 2.5 cross-references.

For one judgment:

  1. Regex pre-pass finds every *other* neutral citation mentioned in the
     judgment text (the judgment's own citation is skipped). Each unique
     citation gets a candidate ``CaseNode`` with a deterministic UUID.
  2. One Gemini Flash call per judgment (NOT per paragraph) classifies
     each candidate as one of: ``cites`` / ``overrules`` /
     ``distinguished_by`` (or ``unknown`` → dropped). The model also
     attributes the relation to a specific paragraph_id when possible.
  3. Returns ``Pass3Stats`` and mutates ``result`` in place to append
     candidate ``CaseNode`` rows + ``Edge`` records.

Then ``build_hyperedges`` (separate entry point invoked by the backfill
orchestrator after all three passes complete) collects per-paragraph
entity sets, embeds the paragraph text via Gemini ``gemini-embedding-001``,
and emits ``HyperedgeNode`` rows that the writer persists into the
``hyperedge`` table.

Cost target: ~$0.005/judgment for Flash classification, ~$0.001/judgment
for hyperedge embeddings → ~$6 total for 1000 judgments.

Idempotent: candidate Case IDs and Edge identities are derived from
deterministic UUIDv5 hashes of the underlying neutral citations + kinds.
Re-running the pass produces byte-identical output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.services.ograg_extract.pass1_structural import (
    CaseNode,
    Edge,
    ExtractionResult,
    OGRAG_NAMESPACE,
    ParagraphNode,
    _NEUTRAL_CITATION,
    _node_id,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# Gemini Flash 2.5 pricing as of 2026-05 — update on price changes.
_FLASH_PRICE_PER_1K_INPUT = 0.000125
_FLASH_PRICE_PER_1K_OUTPUT = 0.000375

_VALID_RELATIONS: frozenset[str] = frozenset({"cites", "overrules", "distinguished_by"})
_MAX_ATTEMPTS = 3
_BASE_BACKOFF_S = 1.0
_PASS_VERSION = 3

# Gemini embedding tunables — match adil-rag-api/ograg/embed.py exactly so
# the hyperedge vectors live in the same space as live query vectors.
_EMBED_MODEL = "gemini-embedding-001"
_EMBED_DIM = 768
# Conservative price for batched embed (lumped under hyperedge cost).
_EMBED_PRICE_PER_1K_TOKENS = 0.00015


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HyperedgeNode:
    """One pgvector hyperedge row.

    ``node_ids`` is the set of entity UUIDs the paragraph references
    (Statute / Section / Subsection / Case / Topic / Party / Judge ...).
    ``embedding`` is the 768-d Gemini vector for ``paragraph_text``.
    """

    node_id: uuid.UUID
    paragraph_id: uuid.UUID
    paragraph_text: str
    node_ids: list[uuid.UUID]
    embedding: list[float]


@dataclass
class Pass3Stats:
    cost_usd: float
    model: str
    input_tokens: int
    output_tokens: int
    candidates: int
    classified: int


@dataclass
class HyperedgeStats:
    cost_usd: float
    paragraphs_embedded: int
    hyperedges_built: int


# ---------------------------------------------------------------------------
# Regex pre-pass: gather candidate cross-cited neutral citations
# ---------------------------------------------------------------------------


def _normalise_citation(year: str, court: str, division: str | None, number: str, paren_div: str | None) -> str:
    """Canonical surface form, e.g. ``[2019] EWCA Civ 1374`` or ``[2015] EWHC 2493 (Admin)``."""
    parts = [f"[{year}]", court]
    if division:
        parts.append(division)
    parts.append(number)
    base = " ".join(parts)
    if paren_div:
        base = f"{base} ({paren_div})"
    return base


def _candidate_case(citation: str) -> CaseNode:
    """Build a deterministic CaseNode for a cited (but not necessarily
    ingested) judgment. court + year extracted from the citation itself;
    case_name is unknown at this point and left blank — pass3 doesn't
    invent names.
    """
    nc_match = _NEUTRAL_CITATION.search(citation)
    year = int(nc_match.group("year")) if nc_match else 0
    court = nc_match.group("court") if nc_match else ""
    return CaseNode(
        node_id=_node_id("case", citation),
        neutral_citation=citation,
        case_name="",  # filled later if/when the case itself is ingested
        court=court,
        year=year,
    )


def _collect_candidates(result: ExtractionResult) -> dict[str, tuple[CaseNode, list[uuid.UUID]]]:
    """Walk paragraphs, regex out every *other* neutral citation, dedup,
    and return ``{citation: (case_node, [paragraph_ids_where_seen])}``.
    """
    self_citation = result.case.neutral_citation.strip()
    candidates: dict[str, tuple[CaseNode, list[uuid.UUID]]] = {}

    for para in result.paragraphs:
        for m in _NEUTRAL_CITATION.finditer(para.text):
            citation = _normalise_citation(
                m.group("year"),
                m.group("court"),
                m.group("division"),
                m.group("number"),
                m.group("paren_div"),
            )
            if citation == self_citation:
                continue
            if citation not in candidates:
                candidates[citation] = (_candidate_case(citation), [para.node_id])
            else:
                _, paras = candidates[citation]
                if para.node_id not in paras:
                    paras.append(para.node_id)
    return candidates


# ---------------------------------------------------------------------------
# Pydantic schemas (Gemini structured output)
# ---------------------------------------------------------------------------


class _CrossRefOut(BaseModel):
    """One cross-reference classification."""

    cited_citation: str = Field(..., description="The cited neutral citation, verbatim as in input.")
    relation: str = Field(..., description="One of: cites, overrules, distinguished_by.")
    paragraph_index: int | None = Field(
        default=None,
        description="0-based paragraph index in the input where the strongest evidence appears, if confident.",
    )


class _CrossRefBatch(BaseModel):
    refs: list[_CrossRefOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You classify the relationship between a judgment and the
other cases it mentions.

For each candidate neutral citation in the CANDIDATES list, decide which of
these UK-legal relations the judgment expresses toward it, based on the
PARAGRAPHS text:

  * cites — the judgment merely cites/references the case (most common).
  * overrules — the judgment explicitly overrules or departs from the cited case.
  * distinguished_by — the judgment distinguishes itself from the cited case
    on the facts or applicable principles (the judgment IS distinguishing
    away from the cited case).

If the relation is unclear, ambiguous, or none of the above applies, omit
that citation from the output. Do NOT invent citations not in CANDIDATES.

When confident, set `paragraph_index` to the 0-based index of the paragraph
that best evidences the relation. Use the indices shown in `[para N]`
markers in the PARAGRAPHS block. When unsure, omit `paragraph_index`.

Reply ONLY with a JSON object matching this schema:
{
  "refs": [
    {"cited_citation": "<verbatim>", "relation": "cites|overrules|distinguished_by", "paragraph_index": <int or null>}
  ]
}
"""


def _format_paragraphs_for_prompt(paragraphs: list[ParagraphNode]) -> str:
    """Compact paragraph block with explicit indices the model can cite."""
    parts: list[str] = []
    for p in paragraphs:
        text = p.text.strip()
        if len(text) > 1200:
            text = text[:1200].rstrip() + "…"
        parts.append(f"[para {p.index}] {text}")
    return "\n\n".join(parts)


def _build_user_prompt(result: ExtractionResult, candidate_citations: list[str]) -> str:
    candidates_block = "\n".join(f"- {c}" for c in candidate_citations)
    paragraphs_block = _format_paragraphs_for_prompt(result.paragraphs)
    return (
        f"JUDGMENT: {result.case.neutral_citation} — {result.case.case_name}\n\n"
        f"CANDIDATES:\n{candidates_block}\n\n"
        f"PARAGRAPHS:\n{paragraphs_block}"
    )


# ---------------------------------------------------------------------------
# Gemini client + retry
# ---------------------------------------------------------------------------


class FlashExtractionError(Exception):
    """Pass 3 fatal failure after retry exhaustion."""


def _is_retryable(exc: BaseException) -> bool:
    msg = str(exc)
    return any(
        tok in msg for tok in ("429", "500", "502", "503", "504", "UNAVAILABLE", "INTERNAL", "RESOURCE_EXHAUSTED")
    )


async def _sleep_backoff(attempt: int) -> None:
    await asyncio.sleep(_BASE_BACKOFF_S * (2**attempt))


def _default_client() -> Any:
    """Lazy import + construct the google-genai client.

    Importing at module load is avoided so unit tests can monkeypatch
    ``client`` without pulling the real SDK.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    from google import genai  # noqa: WPS433 — lazy import is intentional

    return genai.Client(api_key=api_key)


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_payload(text: str) -> _CrossRefBatch:
    cleaned = _JSON_FENCE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise FlashExtractionError(f"Gemini Flash returned non-JSON output: {cleaned[:200]!r}") from exc
    try:
        return _CrossRefBatch.model_validate(data)
    except ValidationError as exc:
        raise FlashExtractionError(f"Gemini Flash output failed schema validation: {exc}") from exc


def _calc_cost(input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1000.0 * _FLASH_PRICE_PER_1K_INPUT + output_tokens / 1000.0 * _FLASH_PRICE_PER_1K_OUTPUT


async def _call_flash(
    client: Any,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
) -> tuple[_CrossRefBatch, int, int]:
    """One Flash call with retry on transient 5xx/429. Returns
    ``(parsed, input_tokens, output_tokens)``.
    """
    last_exc: BaseException | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:

            def _sync_call() -> Any:
                return client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config={
                        "system_instruction": system_prompt,
                        "temperature": 0.0,
                        "max_output_tokens": max_output_tokens,
                        "response_mime_type": "application/json",
                    },
                )

            response = await asyncio.to_thread(_sync_call)
            text = getattr(response, "text", None) or ""
            parsed = _parse_json_payload(text)

            usage = getattr(response, "usage_metadata", None)
            in_tok = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
            out_tok = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0

            return parsed, in_tok, out_tok
        except FlashExtractionError:
            # Schema failure counts as a retry — model sometimes responds
            # with prose on the first attempt despite response_mime_type.
            raise
        except Exception as exc:
            last_exc = exc
            if attempt + 1 == _MAX_ATTEMPTS or not _is_retryable(exc):
                break
            logger.warning("pass3 Gemini Flash attempt %d failed: %s", attempt + 1, exc)
            await _sleep_backoff(attempt)
    raise FlashExtractionError(f"Gemini Flash failed after {_MAX_ATTEMPTS} attempts: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Public entry point — pass 3 extraction
# ---------------------------------------------------------------------------


async def extract_pass3(
    judgment: Any,  # noqa: ARG001 — accepted for orchestrator signature parity
    result: ExtractionResult,
    *,
    client: Any | None = None,
    model: str = "gemini-2.5-flash",
    max_output_tokens: int = 2048,
) -> Pass3Stats:
    """Run pass 3 on an already-extracted ``ExtractionResult``.

    Mutates ``result`` to append candidate ``Case`` nodes (for cross-cited
    cases that haven't been ingested as judgments themselves) and ``cites``
    / ``overrules`` / ``distinguished_by`` edges.

    No paragraphs → no candidates → skip the LLM call entirely.
    """
    candidates = _collect_candidates(result)
    if not candidates or not result.paragraphs:
        return Pass3Stats(
            cost_usd=0.0,
            model=model,
            input_tokens=0,
            output_tokens=0,
            candidates=0,
            classified=0,
        )

    if client is None:
        client = _default_client()

    user_prompt = _build_user_prompt(result, sorted(candidates.keys()))
    parsed, in_tok, out_tok = await _call_flash(
        client,
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_output_tokens=max_output_tokens,
    )

    # Index paragraphs by their position so the model's paragraph_index
    # can be resolved to a node_id.
    para_by_idx = {p.index: p for p in result.paragraphs}

    classified = 0
    # Track which (source, target, kind) triples we've already emitted to
    # keep edges deduped within a single pass run.
    seen_edges: set[tuple[str, str, str]] = set()

    appended_cases: dict[str, CaseNode] = {}

    for ref in parsed.refs:
        relation = ref.relation.strip().lower()
        if relation not in _VALID_RELATIONS:
            continue
        candidate = candidates.get(ref.cited_citation)
        if candidate is None:
            # Hallucinated citation — drop, do not invent.
            logger.debug("pass3: dropping hallucinated citation %r", ref.cited_citation)
            continue
        cited_case, seen_paragraph_ids = candidate

        # Append the candidate Case node exactly once.
        if ref.cited_citation not in appended_cases:
            appended_cases[ref.cited_citation] = cited_case
            result.referenced_cases.append(cited_case)

        # Resolve paragraph attribution — prefer the model's pick, else the
        # first paragraph where the citation was seen.
        paragraph_node_id: uuid.UUID | None = None
        if ref.paragraph_index is not None:
            para = para_by_idx.get(ref.paragraph_index)
            if para is not None:
                paragraph_node_id = para.node_id
        if paragraph_node_id is None and seen_paragraph_ids:
            paragraph_node_id = seen_paragraph_ids[0]

        key = (str(result.case.node_id), str(cited_case.node_id), relation)
        if key in seen_edges:
            continue
        seen_edges.add(key)

        result.edges.append(
            Edge(
                kind=relation,
                source_id=result.case.node_id,
                target_id=cited_case.node_id,
                paragraph_id=paragraph_node_id,
            )
        )
        classified += 1

    return Pass3Stats(
        cost_usd=_calc_cost(in_tok, out_tok),
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        candidates=len(candidates),
        classified=classified,
    )


# ---------------------------------------------------------------------------
# Hyperedge build
# ---------------------------------------------------------------------------


def _collect_paragraph_entities(result: ExtractionResult, paragraph: ParagraphNode) -> list[uuid.UUID]:
    """Return all ontology node IDs the paragraph references — across all
    three passes. Caller-stable ordering: case → statute_refs → section_refs
    → pass2 edges (topics/parties/judges) → pass3 edges (cited cases).
    Dedup preserves first-seen order.
    """
    pid = paragraph.node_id
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()

    def _push(nid: uuid.UUID) -> None:
        if nid not in seen:
            seen.add(nid)
            out.append(nid)

    # The Case itself is always part of the hyperedge — it's the structural
    # anchor for the paragraph.
    _push(result.case.node_id)

    for ref in result.statute_refs:
        if ref.paragraph_id == pid:
            _push(ref.resolved_node_id or ref.candidate_node_id)
    for ref in result.section_refs:
        if ref.paragraph_id == pid:
            _push(ref.resolved_node_id or ref.candidate_node_id)
    for edge in result.edges:
        if edge.paragraph_id == pid:
            _push(edge.target_id)

    return out


def _estimate_embed_cost(texts: Iterable[str]) -> float:
    # Cheap tokens-by-chars estimate; embedding API doesn't return usage.
    chars = sum(len(t) for t in texts)
    tokens = max(1, chars // 4)
    return tokens / 1000.0 * _EMBED_PRICE_PER_1K_TOKENS


# An embedder is any awaitable that maps text → list[float].
Embedder = Callable[[str], Awaitable[list[float]]]


def _default_embedder() -> Embedder:
    """Default embedder using google-genai's gemini-embedding-001."""

    async def _embed(text: str) -> list[float]:
        from google import genai  # noqa: WPS433 — lazy
        from google.genai import types as genai_types  # noqa: WPS433

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        client = genai.Client(api_key=api_key)

        def _call() -> list[float]:
            resp = client.models.embed_content(
                model=_EMBED_MODEL,
                contents=text,
                config=genai_types.EmbedContentConfig(output_dimensionality=_EMBED_DIM),
            )
            embeddings = getattr(resp, "embeddings", None)
            if not embeddings:
                raise RuntimeError("Gemini embed_content returned no embeddings")
            values = getattr(embeddings[0], "values", None) or embeddings[0]["values"]
            return [float(v) for v in values]

        return await asyncio.to_thread(_call)

    return _embed


async def build_hyperedges(
    result: ExtractionResult,
    *,
    embedder: Embedder | None = None,
    skip_empty: bool = True,
) -> HyperedgeStats:
    """Build hyperedge rows for every paragraph in ``result`` and append
    them to ``result.hyperedges``.

    A paragraph with zero entity references is skipped when ``skip_empty``
    (the default) — those paragraphs add no structural signal beyond the
    Case anchor and bloat the index. Set ``skip_empty=False`` to force
    one hyperedge per paragraph (useful for tests).
    """
    if embedder is None:
        embedder = _default_embedder()

    built = 0
    texts_embedded: list[str] = []

    for para in result.paragraphs:
        entity_ids = _collect_paragraph_entities(result, para)
        # entity_ids always contains at least the Case node. "Empty" here
        # means *no domain entities beyond the Case anchor*.
        if skip_empty and len(entity_ids) <= 1:
            continue
        text = para.text or ""
        if not text.strip():
            continue
        embedding = await embedder(text)
        result.hyperedges.append(
            HyperedgeNode(
                node_id=uuid.uuid5(OGRAG_NAMESPACE, f"hyperedge:{para.node_id}"),
                paragraph_id=para.node_id,
                paragraph_text=text,
                node_ids=entity_ids,
                embedding=embedding,
            )
        )
        texts_embedded.append(text)
        built += 1

    return HyperedgeStats(
        cost_usd=_estimate_embed_cost(texts_embedded),
        paragraphs_embedded=built,
        hyperedges_built=built,
    )


# ---------------------------------------------------------------------------
# Backfill integration
# ---------------------------------------------------------------------------


def make_pass3_runner(
    *,
    client: Any | None = None,
    model: str = "gemini-2.5-flash",
    max_output_tokens: int = 2048,
    embedder: Embedder | None = None,
    build_hyperedges_after: bool = True,
    skip_empty_hyperedges: bool = True,
):
    """Return a ``PassRunner`` closure matching ``ograg_backfill.PassRunner``.

    Runs ``extract_pass3`` and (by default) ``build_hyperedges`` in one
    pass slot. The orchestrator records the combined cost under the
    ``pass3_gemini`` ledger entry; the ``note`` separates the two
    components so the operator can see the breakdown.
    """

    async def runner(judgment: Any, result: ExtractionResult):
        stats = await extract_pass3(
            judgment,
            result,
            client=client,
            model=model,
            max_output_tokens=max_output_tokens,
        )
        hyperedge_cost = 0.0
        hyperedges_built = 0
        if build_hyperedges_after:
            h_stats = await build_hyperedges(result, embedder=embedder, skip_empty=skip_empty_hyperedges)
            hyperedge_cost = h_stats.cost_usd
            hyperedges_built = h_stats.hyperedges_built

        total_cost = stats.cost_usd + hyperedge_cost
        note = (
            f"candidates={stats.candidates} classified={stats.classified} "
            f"hyperedges={hyperedges_built} "
            f"flash_cost={stats.cost_usd:.6f} embed_cost={hyperedge_cost:.6f}"
        )
        return total_cost, stats.model, stats.input_tokens, stats.output_tokens, note

    return runner
