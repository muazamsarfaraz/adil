import os

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — skipping DB integration test",
)
async def test_migrations_create_tables():
    from db_migrate import run_migrations

    db_url = os.getenv("TEST_DATABASE_URL")
    await run_migrations(db_url)

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_name IN ('rate_limit_counters', 'uploads')"
        )
        names = {r["table_name"] for r in rows}
        assert names == {"rate_limit_counters", "uploads"}
    finally:
        await conn.close()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)
async def test_migrations_idempotent():
    from db_migrate import run_migrations

    db_url = os.getenv("TEST_DATABASE_URL")
    await run_migrations(db_url)
    await run_migrations(db_url)


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)
async def test_hyperedge_attrs_added_to_preexisting_table():
    """Regression for ograg.retrieval_probe `column "attrs" does not exist`.

    Reproduces a production DB whose hyperedge table was first created from
    007_hyperedge.sql (no `attrs` column) before 006_hyperedge.sql existed.
    Running all migrations must add `attrs` (migration 010), otherwise the
    retrieval path's `SELECT ... attrs ... FROM hyperedge` raises.
    """
    from db_migrate import run_migrations

    db_url = os.getenv("TEST_DATABASE_URL")
    conn = await asyncpg.connect(db_url)
    try:
        # Simulate the legacy (007-style) hyperedge table with no attrs column.
        await conn.execute("DROP TABLE IF EXISTS hyperedge CASCADE")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            """
            CREATE TABLE hyperedge (
              id              UUID         PRIMARY KEY,
              node_ids        UUID[]       NOT NULL,
              paragraph_text  TEXT         NOT NULL,
              source_node_id  UUID,
              embedding       vector(1536) NOT NULL,
              created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
            """
        )
        col = await conn.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'hyperedge' AND column_name = 'attrs'"
        )
        assert col is None, "precondition: legacy table must lack attrs"

        await run_migrations(db_url)

        col = await conn.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'hyperedge' AND column_name = 'attrs'"
        )
        assert col == "attrs", "migration 010 must add hyperedge.attrs"
    finally:
        await conn.close()
