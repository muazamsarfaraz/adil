"""Gemini text-embedding-004 wrapper.

Returns a 768-dimensional embedding vector for a piece of text. Used by
ograg.store and ograg.retriever to feed pgvector. The Gemini API key is
read from the environment lazily so test-only env setups Just Work.
"""

from __future__ import annotations

import asyncio
import os

from google import genai
from google.genai import types as genai_types

# gemini-embedding-001 with output_dimensionality=768 is the current production
# embedding endpoint. text-embedding-004 was retired. 768 dims is plenty for
# legal retrieval and matches the pgvector column width.
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768


def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


async def embed_one(text: str) -> list[float]:
    """Return a 768-dim embedding for `text` via Gemini text-embedding-004."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    def _call() -> list[float]:
        client = _client()
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=text,
            config=genai_types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
        )
        # google-genai returns an EmbedContentResponse with .embeddings list
        embeddings = getattr(resp, "embeddings", None)
        if not embeddings:
            raise RuntimeError("Gemini embed_content returned no embeddings")
        values = getattr(embeddings[0], "values", None) or embeddings[0]["values"]
        return [float(v) for v in values]

    return await asyncio.to_thread(_call)
