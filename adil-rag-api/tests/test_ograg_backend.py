"""End-to-end backend test: retrieve + Gemini Flash generation.

Seeds a tiny legal corpus, asks a question, and verifies the answer
references the seeded content. The backend MUST NOT touch the File
Search Tool — that's the whole point of OG-RAG.
"""

import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

from models import QueryMetadata, Source, TokenUsage

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
async def seeded():
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
                "Section 13 Equality Act 2010: a person (A) discriminates against another (B) "
                "if, because of a protected characteristic, A treats B less favourably than A "
                "treats or would treat others. This is called direct discrimination.",
                {"test": "1", "id": "ea2010-s13", "kind": "statute", "title": "Equality Act 2010", "section": "13"},
            ),
            (
                "Section 26 Equality Act 2010: harassment is unwanted conduct related to a "
                "relevant protected characteristic which has the purpose or effect of violating "
                "B's dignity or creating an intimidating, hostile, degrading, humiliating or "
                "offensive environment.",
                {"test": "1", "id": "ea2010-s26", "kind": "statute", "title": "Equality Act 2010", "section": "26"},
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
async def test_backend_answer_returns_query_shape(seeded):
    from ograg.backend import answer

    result = await answer("What is direct discrimination under section 13 of the Equality Act 2010?")

    # Same 6-tuple shape as RAGService.query()
    assert isinstance(result, tuple)
    assert len(result) == 6
    ans, sources, usage, metadata, viability, evidence = result

    assert isinstance(ans, str) and len(ans) > 50
    # Answer should reference the seeded statute
    assert "13" in ans or "direct discrimination" in ans.lower()

    assert isinstance(sources, list)
    assert all(isinstance(s, Source) for s in sources)

    assert isinstance(usage, TokenUsage)
    assert usage.total_tokens > 0

    assert isinstance(metadata, QueryMetadata)
    assert metadata.processing_time_ms >= 0

    assert viability is None
    assert evidence == []
