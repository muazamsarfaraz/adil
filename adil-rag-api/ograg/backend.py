"""OG-RAG backend: retrieve top-k chunks then generate via Gemini Flash.

Public surface mirrors ``RAGService.query()``: returns the same 6-tuple
``(answer, sources, usage, metadata, viability, evidence_checklist)`` so
the call sites in app.py don't change. The File Search Tool is NOT used.

Also exposes :func:`answer_stream` which mirrors ``RAGService.stream_query``
— yields SSE-shaped ``{"event", "data"}`` dicts using Gemini's
``generate_content_stream`` API. Sources are emitted from the
already-retrieved chunks (retrieval is unary, before generation, so we
know them up-front — simpler than the FST stream which parses citations
out of the answer).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from google import genai

from models import QueryMetadata, Source, SourceType, TokenUsage, ViabilityAssessment
from ograg.retriever import retrieve

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"
DEFAULT_K = 5
PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006


def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


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


def _calc_usage(response) -> TokenUsage:
    usage_meta = getattr(response, "usage_metadata", None)
    prompt = (getattr(usage_meta, "prompt_token_count", 0) or 0) if usage_meta else 0
    completion = (getattr(usage_meta, "candidates_token_count", 0) or 0) if usage_meta else 0
    total = prompt + completion
    cost = prompt / 1000 * PRICE_PER_1K_INPUT + completion / 1000 * PRICE_PER_1K_OUTPUT
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        estimated_cost_usd=round(cost, 6),
    )


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


def _build_contents(
    question: str,
    context_block: str,
    jurisdiction: str | None,
    topic: str | None,
    conversation_history: list[dict[str, str]] | None,
) -> Any:
    user_prompt = _build_user_prompt(question, context_block, jurisdiction, topic)
    if conversation_history:
        contents: list[Any] = []
        for turn in conversation_history[-50:]:
            role = "user" if turn.get("role") == "user" else "model"
            text_val = turn.get("content") or turn.get("text") or ""
            if text_val:
                contents.append({"role": role, "parts": [{"text": text_val}]})
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})
        return contents
    return user_prompt


def _parse_and_strip_blocks(
    answer: str,
    include_viability: bool,
) -> tuple[str, ViabilityAssessment | None, list[str]]:
    """Extract viability + evidence_checklist blocks, return cleaned answer.

    Reuses ``RAGService`` static parsers so the OG-RAG path is byte-for-byte
    consistent with the FST path's parsing rules.
    """
    if not include_viability:
        return answer, None, []
    # Late import to avoid pulling rag_service at module load.
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

    If ``images`` is supplied, image parts are attached to the current turn
    (Gemini multimodal). Retrieval still runs over the question text — the
    image is treated as supplementary content, not a query input.
    """
    from rag_service import SYSTEM_INSTRUCTION

    start_time = time.time()

    effective_question = _apply_viability_trigger(question, include_viability)

    chunks = await retrieve(question, k=DEFAULT_K)
    context_block = _format_context(chunks)

    if images:
        from google.genai import types as genai_types

        parts: list[Any] = []
        for img in images:
            import base64 as _b64

            image_bytes = _b64.b64decode(img["data"])
            parts.append(genai_types.Part.from_bytes(data=image_bytes, mime_type=img["mime_type"]))
        user_prompt = _build_user_prompt(effective_question, context_block, jurisdiction, topic)
        parts.append(genai_types.Part.from_text(text=user_prompt))
        contents: Any = []
        if conversation_history:
            for turn in conversation_history[-50:]:
                role = "user" if turn.get("role") == "user" else "model"
                text_val = turn.get("content") or turn.get("text") or ""
                if text_val:
                    contents.append({"role": role, "parts": [{"text": text_val}]})
        contents.append({"role": "user", "parts": parts})
    else:
        contents = _build_contents(effective_question, context_block, jurisdiction, topic, conversation_history)

    def _call():
        client = _client()
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={"system_instruction": SYSTEM_INSTRUCTION},
        )

    try:
        response = await asyncio.to_thread(_call)
    except Exception as e:
        logger.error("ograg.backend Gemini error: %s", e)
        raise RuntimeError("Failed to generate response from AI model") from e

    try:
        ans = response.text or ""
    except (ValueError, AttributeError):
        logger.warning("Gemini response had no text (safety block?)")
        ans = (
            "I apologise, but I was unable to generate a response for this query. "
            "Please try rephrasing your question."
        )

    ans, viability, evidence_checklist = _parse_and_strip_blocks(ans, include_viability)

    sources = _sources_from_chunks(chunks, max_sources)
    usage = _calc_usage(response)
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
    ``token``, ``source``, ``viability``, ``done`` (and ``error`` raised
    by the caller). Because retrieval is unary in OG-RAG, sources are
    known up front and can be emitted before token streaming starts —
    but to keep parity with the FST stream's ordering (tokens first,
    sources/viability after), we emit them after the token stream.
    """
    from rag_service import SYSTEM_INSTRUCTION

    effective_question = _apply_viability_trigger(question, include_viability)

    chunks = await retrieve(question, k=DEFAULT_K)
    context_block = _format_context(chunks)
    contents = _build_contents(effective_question, context_block, jurisdiction, topic, conversation_history)

    def _start_stream():
        client = _client()
        return client.models.generate_content_stream(
            model=MODEL_NAME,
            contents=contents,
            config={"system_instruction": SYSTEM_INSTRUCTION},
        )

    try:
        stream = await asyncio.to_thread(_start_stream)
    except Exception as e:
        logger.error("ograg.backend streaming start failed: %s", e)
        raise RuntimeError("Failed to start streaming response from AI model") from e

    full_text = ""
    usage_metadata = None

    def _next_chunk(it):
        try:
            return next(it)
        except StopIteration:
            return None

    it = iter(stream)
    while True:
        chunk = await asyncio.to_thread(_next_chunk, it)
        if chunk is None:
            break
        text = getattr(chunk, "text", None)
        if text:
            full_text += text
            yield {"event": "token", "data": text}
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            usage_metadata = um

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

    tokens_used = 0
    if usage_metadata is not None:
        prompt = getattr(usage_metadata, "prompt_token_count", 0) or 0
        completion = getattr(usage_metadata, "candidates_token_count", 0) or 0
        total = getattr(usage_metadata, "total_token_count", None)
        tokens_used = int(total) if total else int(prompt + completion)

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
