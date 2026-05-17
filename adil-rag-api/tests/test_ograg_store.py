"""Integration tests for ograg.store against the real Railway Postgres.

Requires TEST_DATABASE_URL (Postgres public URL) and runs migrations first
to provision pgvector + ograg_chunks. All inserted rows are tagged with
source.test='1' so the teardown can scrub them idempotently.
"""

import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

_TEST_DB_URL = os.getenv("TEST_DATABASE_URL")


async def _cleanup(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("DELETE FROM ograg_chunks WHERE source->>'test' = '1'")
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def store():
    if not _TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set")

    # Ensure migrations have run so pgvector + ograg_chunks exist.
    from db_migrate import run_migrations

    await run_migrations(_TEST_DB_URL)
    await _cleanup(_TEST_DB_URL)

    from ograg.store import Store

    s = Store()
    await s.connect(_TEST_DB_URL)
    try:
        yield s
    finally:
        await s.close()
        await _cleanup(_TEST_DB_URL)


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_insert_chunk_and_search_returns_inserted(store):
    vec_a = [0.1] * 768
    vec_b = [0.9] * 768

    chunk_id_a = uuid.uuid4()
    chunk_id_b = uuid.uuid4()
    await store.insert_chunk(
        text="Section 13 Equality Act 2010 — direct discrimination.",
        source={"test": "1", "kind": "statute", "id": "ea2010-s13"},
        embedding=vec_a,
        chunk_id=chunk_id_a,
    )
    await store.insert_chunk(
        text="Section 26 Equality Act 2010 — harassment.",
        source={"test": "1", "kind": "statute", "id": "ea2010-s26"},
        embedding=vec_b,
        chunk_id=chunk_id_b,
    )

    # Query near vec_a → should rank ea2010-s13 first.
    results = await store.search(query_embedding=vec_a, k=2)
    assert len(results) == 2
    assert results[0]["source"]["id"] == "ea2010-s13"
    assert "text" in results[0] and "Section 13" in results[0]["text"]
    # distance ascending: nearest first
    assert results[0]["distance"] <= results[1]["distance"]


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_insert_chunk_on_conflict_is_noop(store):
    vec = [0.5] * 768
    cid = uuid.uuid4()
    await store.insert_chunk(
        text="duplicate insert test",
        source={"test": "1", "kind": "dup"},
        embedding=vec,
        chunk_id=cid,
    )
    # Re-insert same id with different text — ON CONFLICT DO NOTHING means
    # the original row wins.
    await store.insert_chunk(
        text="DIFFERENT TEXT",
        source={"test": "1", "kind": "dup"},
        embedding=vec,
        chunk_id=cid,
    )
    rows = await store.search(query_embedding=vec, k=5)
    matches = [r for r in rows if r["id"] == cid]
    assert len(matches) == 1
    assert matches[0]["text"] == "duplicate insert test"
