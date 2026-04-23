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
