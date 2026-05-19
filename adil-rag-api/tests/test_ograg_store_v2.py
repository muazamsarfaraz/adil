"""Integration tests for ograg.store_v2 against real Postgres.

Requires TEST_DATABASE_URL. Auto-applies migrations so pgvector +
ontology_node/edge/hyperedge exist. Each test truncates ontology_* tables
before running to keep tests isolated.

Schema aligned with 004_ontology_init.sql (UUIDs, text type column) and
007_hyperedge.sql.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

_TEST_DB_URL = os.getenv("TEST_DATABASE_URL")


async def _truncate_ontology(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("TRUNCATE ontology_edge, hyperedge, ontology_node RESTART IDENTITY CASCADE")
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def store():
    if not _TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set")

    from db_migrate import run_migrations

    await run_migrations(_TEST_DB_URL)
    await _truncate_ontology(_TEST_DB_URL)

    from ograg.store_v2 import OntologyStore

    s = OntologyStore(_TEST_DB_URL)
    await s.connect()
    try:
        yield s
    finally:
        await s.close()
        await _truncate_ontology(_TEST_DB_URL)


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_upsert_node_new(store):
    from ograg.store_v2 import NodeRecord

    node_id = await store.upsert_node(
        NodeRecord(
            node_type="statute",
            natural_key="statute:equality-act-2010",
            attrs={"short_title": "Equality Act 2010", "year": 2010},
        )
    )
    assert isinstance(node_id, uuid.UUID)


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_upsert_node_idempotent(store):
    from ograg.store_v2 import NodeRecord

    rec = NodeRecord(
        node_type="statute",
        natural_key="statute:mca-2005",
        attrs={"short_title": "Mental Capacity Act 2005"},
    )
    id1 = await store.upsert_node(rec)
    id2 = await store.upsert_node(rec)
    assert id1 == id2


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_upsert_node_updates_attrs(store):
    from ograg.store_v2 import NodeRecord

    rec1 = NodeRecord(node_type="statute", natural_key="statute:hra-1998", attrs={"v": 1})
    rec2 = NodeRecord(node_type="statute", natural_key="statute:hra-1998", attrs={"v": 2})
    id1 = await store.upsert_node(rec1)
    id2 = await store.upsert_node(rec2)
    assert id1 == id2
    fetched = await store.get_node(id1)
    assert fetched is not None
    assert fetched.attrs["v"] == 2


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_get_node_by_natural_key(store):
    from ograg.store_v2 import NodeRecord

    await store.upsert_node(
        NodeRecord(
            node_type="statute",
            natural_key="statute:poa-1986",
            attrs={"short_title": "Public Order Act 1986"},
        )
    )
    fetched = await store.get_node_by_key("statute", "statute:poa-1986")
    assert fetched is not None
    assert fetched.natural_key == "statute:poa-1986"
    assert fetched.attrs["short_title"] == "Public Order Act 1986"


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_get_node_missing_returns_none(store):
    fetched = await store.get_node_by_key("statute", "statute:does-not-exist")
    assert fetched is None


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_upsert_edge(store):
    from ograg.store_v2 import EdgeRecord, NodeRecord

    statute_id = await store.upsert_node(NodeRecord(node_type="statute", natural_key="statute:test-a", attrs={}))
    section_id = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:test-a-s1", attrs={}))
    edge_id = await store.upsert_edge(EdgeRecord(source_id=section_id, target_id=statute_id, relation="part_of"))
    assert isinstance(edge_id, uuid.UUID)


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_upsert_edge_idempotent(store):
    from ograg.store_v2 import EdgeRecord, NodeRecord

    a = await store.upsert_node(NodeRecord(node_type="statute", natural_key="statute:test-b", attrs={}))
    b = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:test-b-s1", attrs={}))
    e = EdgeRecord(source_id=b, target_id=a, relation="part_of")
    id1 = await store.upsert_edge(e)
    id2 = await store.upsert_edge(e)
    assert id1 == id2


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_batch_upsert_nodes(store):
    from ograg.store_v2 import NodeRecord

    records = [NodeRecord(node_type="section", natural_key=f"section:test-c-s{i}", attrs={"n": i}) for i in range(1, 6)]
    ids = await store.batch_upsert_nodes(records)
    assert len(ids) == 5
    assert len(set(ids)) == 5


@pytest.mark.skipif(not _TEST_DB_URL, reason="TEST_DATABASE_URL not set")
async def test_get_edges_by_source(store):
    from ograg.store_v2 import EdgeRecord, NodeRecord

    statute_id = await store.upsert_node(NodeRecord(node_type="statute", natural_key="statute:test-d", attrs={}))
    s1 = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:test-d-s1", attrs={}))
    s2 = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:test-d-s2", attrs={}))
    await store.upsert_edge(EdgeRecord(source_id=s1, target_id=statute_id, relation="part_of"))
    await store.upsert_edge(EdgeRecord(source_id=s2, target_id=statute_id, relation="part_of"))
    edges = await store.get_edges_from(statute_id, relation="part_of", reverse=True)
    assert {e.source_id for e in edges} == {s1, s2}
