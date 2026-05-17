"""Real-API test for ograg.embed.

Verifies that the (rotated) Gemini API key works for text-embedding-004
and returns a 768-dim float vector. Skipped when GEMINI_API_KEY is absent.
"""

import os

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set — skipping real Gemini embed test",
)
async def test_embed_one_returns_768_dim_vector():
    from ograg.embed import embed_one

    vec = await embed_one("Section 13 of the Equality Act 2010 defines direct discrimination.")

    assert isinstance(vec, list)
    assert len(vec) == 768
    assert all(isinstance(x, float) for x in vec)
    # not all zeros, not all the same value
    assert any(x != 0.0 for x in vec)
    assert len(set(vec)) > 10


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set",
)
async def test_embed_one_different_text_different_vector():
    from ograg.embed import embed_one

    a = await embed_one("indirect discrimination")
    b = await embed_one("religious harassment in the workplace")

    assert a != b
