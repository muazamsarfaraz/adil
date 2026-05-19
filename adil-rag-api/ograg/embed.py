"""OpenAI text-embedding-3-small wrapper.

Returns a 1536-dimensional embedding vector for a piece of text. Used by
``ograg.store`` and ``ograg.retriever`` to feed pgvector. The OpenAI API
key is read from the environment lazily so test-only env setups Just Work.

Vendor decision recorded in
``docs/superpowers/specs/2026-05-19-og-rag-migration-design.md`` §14
(revised 2026-05-19): we run OpenAI for embedding so the OG-RAG path has
zero Gemini dependency. Embeddings are recoverable offline — if OpenAI is
ever dropped, every chunk can be re-embedded from its source text.
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536


def _client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=api_key)


async def embed_one(text: str) -> list[float]:
    """Return a 1536-dim embedding for ``text`` via OpenAI text-embedding-3-small."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    client = _client()
    resp = await client.embeddings.create(model=EMBED_MODEL, input=text)
    if not resp.data:
        raise RuntimeError("OpenAI embeddings.create returned no data")
    return [float(v) for v in resp.data[0].embedding]


async def embed_many(texts: list[str]) -> list[list[float]]:
    """Batched variant — single OpenAI call returns multiple embeddings.

    OpenAI accepts up to 2048 inputs per request, but practical throughput
    plateaus around 100 per call. Callers should chunk if they have more.
    Empty/whitespace inputs raise ``ValueError`` before any HTTP call.
    """
    if not texts:
        return []
    cleaned: list[str] = []
    for t in texts:
        if not isinstance(t, str) or not t.strip():
            raise ValueError("every input must be a non-empty string")
        cleaned.append(t)

    client = _client()
    resp = await client.embeddings.create(model=EMBED_MODEL, input=cleaned)
    if len(resp.data) != len(cleaned):
        raise RuntimeError(f"OpenAI returned {len(resp.data)} embeddings for {len(cleaned)} inputs")
    return [[float(v) for v in item.embedding] for item in resp.data]
