"""OG-RAG backend: retrieve top-k chunks then generate via Gemini Flash.

Public surface mirrors ``RAGService.query()``: returns the same 6-tuple
``(answer, sources, usage, metadata, viability, evidence_checklist)`` so
the call sites in app.py don't change. The File Search Tool is NOT used.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
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
    """Build typed Source records directly from retrieved chunks.

    Re-uses RAGService.extract_citations_from_answer logic by going through
    the retrieved metadata first — simpler and more reliable than re-parsing
    the model output for the MVP.
    """
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


async def answer(
    question: str,
    *,
    jurisdiction: str | None = None,
    topic: str | None = None,
    max_sources: int = 10,
    include_viability: bool = False,
    conversation_history: list[dict[str, str]] | None = None,
) -> tuple[str, list[Source], TokenUsage, QueryMetadata, ViabilityAssessment | None, list[str]]:
    """Drop-in replacement for RAGService.query() using OG-RAG retrieval."""
    # Late-import the system prompt so importing this module doesn't drag in
    # the full FST-tied rag_service module at process start.
    from rag_service import SYSTEM_INSTRUCTION

    start_time = time.time()

    chunks = await retrieve(question, k=DEFAULT_K)
    context_block = _format_context(chunks)
    user_prompt = _build_user_prompt(question, context_block, jurisdiction, topic)

    # Build contents — multi-turn if history present.
    contents: list[Any]
    if conversation_history:
        contents = []
        for turn in conversation_history[-50:]:
            role = "user" if turn.get("role") == "user" else "model"
            text_val = turn.get("content") or turn.get("text") or ""
            if text_val:
                contents.append({"role": role, "parts": [{"text": text_val}]})
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})
    else:
        contents = user_prompt

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

    sources = _sources_from_chunks(chunks, max_sources)
    usage = _calc_usage(response)
    processing_ms = int((time.time() - start_time) * 1000)
    metadata = QueryMetadata(
        original_language="en",
        processing_time_ms=processing_ms,
        model_used=MODEL_NAME,
    )

    # Viability assessment is not implemented in the OG-RAG MVP path.
    viability: ViabilityAssessment | None = None
    evidence_checklist: list[str] = []
    return ans, sources, usage, metadata, viability, evidence_checklist
