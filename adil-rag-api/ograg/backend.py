"""OG-RAG backend: retrieve top-k chunks then generate via Claude Sonnet 4.6.

Public surface mirrors ``RAGService.query()``: returns the same 6-tuple
``(answer, sources, usage, metadata, viability, evidence_checklist)`` so
the call sites in app.py don't change. The File Search Tool is NOT used.

Also exposes :func:`answer_stream` which mirrors ``RAGService.stream_query``
— yields SSE-shaped ``{"event", "data"}`` dicts using Anthropic's native
async streaming API.

Vendor decision recorded in
``docs/superpowers/specs/2026-05-19-og-rag-migration-design.md`` §14
(revised 2026-05-19): zero Gemini dependency in the OG-RAG hot path.
Anthropic Claude Sonnet for generation; Claude Haiku for cheap structured
calls (judge, query rewriting); OpenAI for embeddings. Key rotation can
never break the OG-RAG service because no key is bound to a project-owned
resource.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from models import QueryMetadata, Source, SourceType, TokenUsage, ViabilityAssessment
from ograg.retriever import retrieve

logger = logging.getLogger(__name__)

MODEL_NAME = "claude-sonnet-4-6"
DEFAULT_K = 5
MAX_TOKENS = 4096

# Anthropic pricing as of 2026-05 (Sonnet 4.6). Update on price changes.
PRICE_PER_1K_INPUT = 0.003  # $3 / M tokens
PRICE_PER_1K_OUTPUT = 0.015  # $15 / M tokens


def _client() -> AsyncAnthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return AsyncAnthropic(api_key=api_key)


def _format_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(no retrieved context)"
    blocks: list[str] = []
    for i, c in enumerate(chunks, start=1):
        src = c.get("source") or {}
        title = src.get("title") or src.get("id") or "Unknown"
        section = src.get("section")
        header = f"[{i}] {title}" + (f" s.{section}" if section else "")
        blocks.append(f"{header}\n{c.get('text', '').strip()}")
    return "\n\n".join(blocks)


def _build_user_prompt(question: str, context: str, jurisdiction: str | None, topic: str | None) -> str:
    extras: list[str] = []
    if jurisdiction:
        extras.append(f"Jurisdiction hint: {jurisdiction}")
    if topic:
        extras.append(f"Topic hint: {topic}")
    extras_block = ("\n" + "\n".join(extras)) if extras else ""
    return (
        "Use ONLY the retrieved context below to answer the question. Cite specific "
        "sections and cases as you would in your normal style. If the context is "
        "insufficient, say so plainly.\n\n"
        f"--- RETRIEVED CONTEXT ---\n{context}\n--- END CONTEXT ---{extras_block}\n\n"
        f"Question: {question}"
    )


def _calc_usage_from_anthropic(usage_obj) -> TokenUsage:
    """Build TokenUsage from anthropic.types.Usage.

    Accepts the response.usage object (sync or stream-final). Handles None
    fields defensively because the streaming API may emit partial usage.
    """
    prompt = int(getattr(usage_obj, "input_tokens", 0) or 0)
    completion = int(getattr(usage_obj, "output_tokens", 0) or 0)
    total = prompt + completion
    cost = prompt / 1000 * PRICE_PER_1K_INPUT + completion / 1000 * PRICE_PER_1K_OUTPUT
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        estimated_cost_usd=round(cost, 6),
    )


def _zero_usage() -> TokenUsage:
    return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0, estimated_cost_usd=0.0)


def _sources_from_chunks(chunks: list[dict[str, Any]], max_sources: int) -> list[Source]:
    """Build typed Source records directly from retrieved chunks."""
    out: list[Source] = []
    for c in chunks[:max_sources]:
        src = c.get("source") or {}
        kind = (src.get("kind") or "").lower()
        if kind == "case_law":
            stype = SourceType.CASE_LAW
        elif kind == "guidance":
            stype = SourceType.GUIDANCE
        else:
            stype = SourceType.STATUTE

        title = src.get("title") or src.get("id") or "Unknown source"
        doc_id = str(src.get("id") or src.get("chunk_id") or c.get("id"))
        excerpt = (c.get("text") or "")[:500]

        out.append(
            Source(
                document_id=doc_id,
                title=title,
                excerpt=excerpt,
                source_type=stype,
                section=src.get("section"),
                act_name=src.get("title") if stype == SourceType.STATUTE else None,
                neutral_citation=src.get("neutral_citation"),
                url=src.get("url"),
                jurisdiction=src.get("jurisdiction") or "England and Wales",
            )
        )
    return out


def _apply_viability_trigger(question: str, include_viability: bool) -> str:
    if include_viability:
        return "INCLUDE VIABILITY ASSESSMENT. " + question
    return question


def _build_messages(
    user_prompt: str,
    conversation_history: list[dict[str, str]] | None,
    image_blocks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build Anthropic messages array.

    Anthropic schema: ``[{"role": "user"|"assistant", "content": str | list[block]}]``.
    System prompt is passed separately (NOT inside messages).

    Maps the legacy Gemini ``"model"`` role to Anthropic ``"assistant"``.
    Drops empty turns. Images attach to the final user message.
    """
    messages: list[dict[str, Any]] = []
    if conversation_history:
        for turn in conversation_history[-50:]:
            role_raw = turn.get("role") or "user"
            role = "user" if role_raw == "user" else "assistant"
            text_val = (turn.get("content") or turn.get("text") or "").strip()
            if text_val:
                messages.append({"role": role, "content": text_val})

    if image_blocks:
        content_blocks: list[dict[str, Any]] = list(image_blocks)
        content_blocks.append({"type": "text", "text": user_prompt})
        messages.append({"role": "user", "content": content_blocks})
    else:
        messages.append({"role": "user", "content": user_prompt})

    return messages


def _parse_and_strip_blocks(
    answer: str,
    include_viability: bool,
) -> tuple[str, ViabilityAssessment | None, list[str]]:
    """Extract viability + evidence_checklist blocks, return cleaned answer.

    Reuses ``RAGService`` static parsers so the OG-RAG path is byte-for-byte
    consistent with the FST path's parsing rules. Claude follows the same
    output format because the SYSTEM_INSTRUCTION specifies it.
    """
    if not include_viability:
        return answer, None, []
    from rag_service import RAGService

    evidence = RAGService._parse_evidence_checklist(answer)
    cleaned = RAGService._strip_evidence_checklist(answer)
    viability = RAGService._parse_viability(cleaned)
    cleaned = RAGService._strip_viability_block(cleaned)
    return cleaned, viability, evidence


async def answer(
    question: str,
    *,
    jurisdiction: str | None = None,
    topic: str | None = None,
    max_sources: int = 10,
    include_viability: bool = False,
    conversation_history: list[dict[str, str]] | None = None,
    images: list[dict[str, Any]] | None = None,
) -> tuple[str, list[Source], TokenUsage, QueryMetadata, ViabilityAssessment | None, list[str]]:
    """Drop-in replacement for ``RAGService.query()`` / ``query_with_images()``.

    If ``images`` is supplied, image content blocks attach to the current
    user message. Retrieval still runs over the question text only — the
    image is supplementary, not a query input.
    """
    from rag_service import SYSTEM_INSTRUCTION

    start_time = time.time()

    effective_question = _apply_viability_trigger(question, include_viability)

    chunks = await retrieve(question, k=DEFAULT_K)
    context_block = _format_context(chunks)
    user_prompt = _build_user_prompt(effective_question, context_block, jurisdiction, topic)

    image_blocks: list[dict[str, Any]] | None = None
    if images:
        image_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("mime_type", "image/png"),
                    "data": img["data"],
                },
            }
            for img in images
        ]

    messages = _build_messages(user_prompt, conversation_history, image_blocks)

    client = _client()
    try:
        response = await client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_INSTRUCTION,
            messages=messages,
        )
    except Exception as e:
        logger.error("ograg.backend Anthropic error: %s", e)
        raise RuntimeError("Failed to generate response from AI model") from e

    ans = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            ans += block.text
    if not ans:
        logger.warning("Anthropic response had no text content")
        ans = (
            "I apologise, but I was unable to generate a response for this query. "
            "Please try rephrasing your question."
        )

    ans, viability, evidence_checklist = _parse_and_strip_blocks(ans, include_viability)

    sources = _sources_from_chunks(chunks, max_sources)
    usage = _calc_usage_from_anthropic(response.usage)
    processing_ms = int((time.time() - start_time) * 1000)
    metadata = QueryMetadata(
        original_language="en",
        processing_time_ms=processing_ms,
        model_used=MODEL_NAME,
    )
    return ans, sources, usage, metadata, viability, evidence_checklist


async def answer_stream(
    question: str,
    *,
    jurisdiction: str | None = None,
    topic: str | None = None,
    max_sources: int = 10,
    include_viability: bool = True,
    conversation_history: list[dict[str, str]] | None = None,
    conversation_id: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """SSE-shaped event stream mirroring ``RAGService.stream_query``.

    Yields dicts of ``{"event": str, "data": Any}`` with event types:
    ``token``, ``source``, ``viability``, ``done``. Uses Anthropic's native
    streaming API (``client.messages.stream``) which is fully async.
    """
    from rag_service import SYSTEM_INSTRUCTION

    effective_question = _apply_viability_trigger(question, include_viability)

    chunks = await retrieve(question, k=DEFAULT_K)
    context_block = _format_context(chunks)
    user_prompt = _build_user_prompt(effective_question, context_block, jurisdiction, topic)
    messages = _build_messages(user_prompt, conversation_history)

    client = _client()
    full_text = ""
    final_usage = None

    try:
        async with client.messages.stream(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_INSTRUCTION,
            messages=messages,
        ) as stream:
            async for text_delta in stream.text_stream:
                if text_delta:
                    full_text += text_delta
                    yield {"event": "token", "data": text_delta}
            # The final_message gives us the authoritative usage object.
            final_message = await stream.get_final_message()
            final_usage = final_message.usage
    except Exception as e:
        logger.error("ograg.backend streaming failed: %s", e)
        raise RuntimeError("Failed to start streaming response from AI model") from e

    answer_text, viability, evidence_checklist = _parse_and_strip_blocks(full_text, include_viability)

    sources = _sources_from_chunks(chunks, max_sources)
    for s in sources:
        data = s.model_dump(mode="json") if hasattr(s, "model_dump") else dict(s)
        yield {"event": "source", "data": data}

    if viability is not None:
        data = viability.model_dump(mode="json") if hasattr(viability, "model_dump") else dict(viability)
        if evidence_checklist and not data.get("evidence_checklist"):
            data["evidence_checklist"] = evidence_checklist
        yield {"event": "viability", "data": data}

    if final_usage is not None:
        usage = _calc_usage_from_anthropic(final_usage)
        tokens_used = usage.total_tokens
    else:
        tokens_used = 0

    # Keep `answer_text` reachable for callers that introspect the generator.
    _ = answer_text

    yield {
        "event": "done",
        "data": {
            "conversation_id": str(conversation_id) if conversation_id else None,
            "sources_count": len(sources),
            "tokens_used": tokens_used,
        },
    }
