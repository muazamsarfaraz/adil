"""Retriever v2 — Algo-1 hyperedge cover + multi-turn query rewriting.

Pipeline (when ``RAG_BACKEND=ograg``):

  1. If conversation_history is non-empty → rewrite the question into a
     standalone retrieval query (Gemini Flash, ~$0.0001/call).
  2. Embed the (rewritten) query (Gemini gemini-embedding-001, 768-d).
  3. ANN top-50 over ``hyperedge.embedding`` (pgvector ivfflat cosine).
  4. Greedy Algorithm-1 cover: pick hyperedges to maximise unique entity
     coverage subject to a ~6000-token budget.
  5. Return ordered list of hyperedge dicts (paragraph_text, citations,
     score, entity_set).

Backward-compat: ``retrieve_chunks()`` keeps the flat MVP path against
``ograg_chunks`` and is routed via ``RAG_BACKEND=ograg_chunks`` so the
eval harness can A/B the two retrievers without re-deploying.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ograg.cover import algo1_cover
from ograg.embed import embed_one
from ograg.rewriter import rewrite_query
from ograg.store import Store

logger = logging.getLogger(__name__)

DEFAULT_TOP_K_CANDIDATES = int(os.environ.get("OGRAG_ANN_TOP_K", "50"))
DEFAULT_TARGET_TOKENS = int(os.environ.get("OGRAG_TARGET_TOKENS", "6000"))


def _resolve_db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or TEST_DATABASE_URL) is not set")
    return url


def _build_source(hyperedge: dict[str, Any], node_lookup: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    """Synthesise a flat `source` dict (compatible with backend._format_context
    and _sources_from_chunks) from the hyperedge + its referenced nodes.

    Picks the "primary" citation: a Section node if present, else the first
    Case node, else the source_node attrs, else generic.
    """
    nodes = [node_lookup.get(nid) for nid in hyperedge.get("node_ids") or []]
    nodes = [n for n in nodes if n]

    def _of_type(t: str) -> dict[str, Any] | None:
        for n in nodes:
            if (n.get("type") or "").lower() == t.lower():
                return n
        return None

    section = _of_type("Section") or _of_type("Subsection")
    case = _of_type("Case")
    statute = _of_type("Statute")
    paragraph = _of_type("Paragraph")

    if section:
        attrs = section.get("attrs") or {}
        statute_attrs = (statute or {}).get("attrs") or {}
        return {
            "id": str(section.get("id")),
            "kind": "statute",
            "title": statute_attrs.get("title") or attrs.get("statute_title") or attrs.get("title") or "UK Statute",
            "section": attrs.get("number") or attrs.get("section") or attrs.get("ref"),
            "url": attrs.get("url") or statute_attrs.get("url"),
            "jurisdiction": attrs.get("jurisdiction") or statute_attrs.get("jurisdiction") or "England and Wales",
        }
    if case:
        attrs = case.get("attrs") or {}
        return {
            "id": str(case.get("id")),
            "kind": "case_law",
            "title": attrs.get("title") or attrs.get("name") or attrs.get("neutral_citation") or "UK Case",
            "neutral_citation": attrs.get("neutral_citation"),
            "section": (paragraph.get("attrs") or {}).get("number") if paragraph else None,
            "url": attrs.get("url"),
            "jurisdiction": attrs.get("jurisdiction") or "England and Wales",
        }
    # Fallback — source_node attrs, or generic.
    if hyperedge.get("source_node_id") and node_lookup.get(hyperedge["source_node_id"]):
        n = node_lookup[hyperedge["source_node_id"]]
        attrs = n.get("attrs") or {}
        return {
            "id": str(n.get("id")),
            "kind": (n.get("type") or "guidance").lower(),
            "title": attrs.get("title") or "Reference",
            "section": attrs.get("number") or attrs.get("section"),
            "url": attrs.get("url"),
            "jurisdiction": attrs.get("jurisdiction") or "England and Wales",
        }
    return {
        "id": str(hyperedge.get("id") or ""),
        "kind": "guidance",
        "title": "Reference",
        "jurisdiction": "England and Wales",
    }


async def retrieve(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    k_target_tokens: int | None = None,
    top_k_candidates: int | None = None,
    k: int | None = None,  # legacy kwarg — accepted for caller compat, ignored
) -> list[dict[str, Any]]:
    """Retriever v2 — hyperedge ANN + Algo-1 cover.

    Returns hyperedge dicts shaped to be drop-in compatible with the old
    chunk-shaped result: ``{id, text, source, distance, similarity,
    node_ids, cover_score, new_entity_count}``. ``text`` is the
    paragraph_text; ``source`` is synthesised from the linked
    ontology_node rows so backend.py's existing _format_context and
    _sources_from_chunks keep working unchanged.

    Args:
        question: User question. Must be non-empty.
        history: Conversation history (role/content dicts). If non-empty,
            triggers query rewriting on the last ``MAX_TURNS`` turns.
        k_target_tokens: Token budget for the Algo-1 cover. Defaults to
            ``OGRAG_TARGET_TOKENS`` (6000).
        top_k_candidates: ANN candidate pool size. Defaults to
            ``OGRAG_ANN_TOP_K`` (50).
        k: Legacy ``k`` kwarg from the MVP chunk retriever. Accepted but
            ignored; the new retriever is budget-bounded, not k-bounded.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    _ = k  # silence unused — kept for caller back-compat (probes.py etc.)

    target_tokens = k_target_tokens if k_target_tokens is not None else DEFAULT_TARGET_TOKENS
    top_k = top_k_candidates if top_k_candidates is not None else DEFAULT_TOP_K_CANDIDATES

    # 1. Multi-turn query rewrite
    effective_question = question.strip()
    if history:
        try:
            effective_question = await rewrite_query(history, question)
        except Exception as e:
            logger.warning("query rewrite raised; using original: %s", e)
            effective_question = question.strip()

    # 2. Embed
    qvec = await embed_one(effective_question)

    # 3. ANN + 4. Cover (single DB connection)
    store = Store()
    await store.connect(_resolve_db_url())
    try:
        candidates = await store.ann_search_hyperedges(query_embedding=qvec, top_k=top_k)
        selected = algo1_cover(candidates, k_target_tokens=target_tokens)

        # Bulk-fetch the ontology nodes referenced by selected hyperedges for
        # citation building. One round-trip instead of per-hyperedge.
        all_node_ids: list[Any] = []
        seen: set[Any] = set()
        for h in selected:
            for nid in h.get("node_ids") or []:
                if nid not in seen:
                    seen.add(nid)
                    all_node_ids.append(nid)
            sid = h.get("source_node_id")
            if sid and sid not in seen:
                seen.add(sid)
                all_node_ids.append(sid)
        nodes = await store.fetch_citation_nodes(all_node_ids) if all_node_ids else []
    finally:
        await store.close()

    node_lookup = {n["id"]: n for n in nodes}

    # 5. Shape results — make them drop-in compatible with chunk consumers.
    out: list[dict[str, Any]] = []
    for h in selected:
        out.append(
            {
                "id": h.get("id"),
                "text": h.get("paragraph_text") or "",
                "source": _build_source(h, node_lookup),
                "distance": h.get("distance"),
                "similarity": h.get("similarity"),
                "node_ids": list(h.get("node_ids") or []),
                "cover_score": h.get("cover_score"),
                "new_entity_count": h.get("new_entity_count"),
            }
        )

    if not out:
        logger.info("ograg.retrieve: no hyperedges returned for query (len=%d)", len(effective_question))
    return out


async def retrieve_chunks(question: str, k: int = 5) -> list[dict[str, Any]]:
    """Legacy flat-chunk retriever (MVP, ``ograg_chunks`` table).

    Kept available behind ``RAG_BACKEND=ograg_chunks`` so the eval harness
    can A/B the flat retriever against the new hyperedge cover during P8.
    Will be removed in P12 alongside the ``ograg_chunks`` table.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")

    query_vec = await embed_one(question)
    store = Store()
    await store.connect(_resolve_db_url())
    try:
        return await store.search(query_embedding=query_vec, k=k)
    finally:
        await store.close()
