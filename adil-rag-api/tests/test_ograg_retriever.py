"""End-to-end retriever test: embed a query + ANN search over real chunks.

Seeds two distinct legal snippets (with real Gemini embeddings) and asserts
the retriever returns the semantically relevant one first.
"""

import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

_DB = os.getenv("TEST_DATABASE_URL")
_KEY = os.getenv("GEMINI_API_KEY")


async def _cleanup(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("DELETE FROM ograg_chunks WHERE source->>'test' = '1'")
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def seeded_corpus():
    if not (_DB and _KEY):
        pytest.skip("TEST_DATABASE_URL and GEMINI_API_KEY required")

    from db_migrate import run_migrations
    from ograg.embed import embed_one
    from ograg.store import Store

    await run_migrations(_DB)
    await _cleanup(_DB)

    store = Store()
    await store.connect(_DB)
    try:
        chunks = [
            (
                "Section 13 Equality Act 2010: direct discrimination means a person "
                "treats someone less favourably because of a protected characteristic.",
                {"test": "1", "id": "ea2010-s13", "kind": "statute"},
            ),
            (
                "The Mental Capacity Act 2005 governs decisions for people lacking "
                "capacity in England and Wales, including Lasting Powers of Attorney.",
                {"test": "1", "id": "mca2005-overview", "kind": "statute"},
            ),
        ]
        for text, src in chunks:
            vec = await embed_one(text)
            await store.insert_chunk(text=text, source=src, embedding=vec, chunk_id=uuid.uuid4())
        yield
    finally:
        await store.close()
        await _cleanup(_DB)


@pytest.mark.skipif(not (_DB and _KEY), reason="TEST_DATABASE_URL and GEMINI_API_KEY required")
async def test_retriever_returns_relevant_chunk_first(seeded_corpus):
    from ograg.retriever import retrieve

    results = await retrieve("What is direct discrimination under UK law?", k=2)

    assert len(results) == 2
    top = results[0]
    assert top["source"]["id"] == "ea2010-s13"
    assert "direct discrimination" in top["text"].lower()


@pytest.mark.skipif(not (_DB and _KEY), reason="TEST_DATABASE_URL and GEMINI_API_KEY required")
async def test_retriever_other_topic_picks_other_chunk(seeded_corpus):
    from ograg.retriever import retrieve

    results = await retrieve("Who handles decisions when someone lacks mental capacity?", k=1)

    assert len(results) == 1
    assert results[0]["source"]["id"] == "mca2005-overview"
