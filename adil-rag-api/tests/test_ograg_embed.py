"""Real-API test for ograg.embed.

Verifies the OpenAI text-embedding-3-small key works and returns a 1536-d
float vector. Skipped when OPENAI_API_KEY is absent.
"""

import os

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping real OpenAI embed test",
)
async def test_embed_one_returns_1536_dim_vector():
    from ograg.embed import embed_one

    vec = await embed_one("Section 13 of the Equality Act 2010 defines direct discrimination.")

    assert isinstance(vec, list)
    assert len(vec) == 1536
    assert all(isinstance(x, float) for x in vec)
    # not all zeros, not all the same value
    assert any(x != 0.0 for x in vec)
    assert len(set(vec)) > 10


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
async def test_embed_one_different_text_different_vector():
    from ograg.embed import embed_one

    a = await embed_one("indirect discrimination")
    b = await embed_one("religious harassment in the workplace")

    assert a != b


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
async def test_embed_many_preserves_order_and_count():
    from ograg.embed import embed_many

    inputs = [
        "direct discrimination",
        "indirect discrimination",
        "harassment under the Equality Act 2010",
    ]
    vecs = await embed_many(inputs)

    assert len(vecs) == 3
    assert all(len(v) == 1536 for v in vecs)
    # each pair distinct
    assert vecs[0] != vecs[1]
    assert vecs[1] != vecs[2]


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
async def test_embed_one_rejects_empty_string():
    from ograg.embed import embed_one

    with pytest.raises(ValueError, match="non-empty"):
        await embed_one("")
