"""Embed-then-search retriever for OG-RAG.

The DB URL is taken from ``DATABASE_URL`` (or ``TEST_DATABASE_URL`` in tests).
A new asyncpg connection is opened per call — fine for MVP traffic; can be
swapped for a pool later.
"""

from __future__ import annotations

import os
from typing import Any

from ograg.embed import embed_one
from ograg.store import Store


def _resolve_db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or TEST_DATABASE_URL) is not set")
    return url


async def retrieve(question: str, k: int = 5) -> list[dict[str, Any]]:
    """Return top-k chunks for `question`, nearest first by cosine distance."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")

    query_vec = await embed_one(question)
    store = Store()
    await store.connect(_resolve_db_url())
    try:
        return await store.search(query_embedding=query_vec, k=k)
    finally:
        await store.close()
