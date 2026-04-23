import os
from datetime import timedelta

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_pool():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    pool = await asyncpg.create_pool(url, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_counters (
              bucket_key   TEXT        NOT NULL,
              bucket_start TIMESTAMPTZ NOT NULL,
              count        INT         NOT NULL DEFAULT 0,
              PRIMARY KEY (bucket_key, bucket_start)
            )
            """
        )
        await conn.execute("TRUNCATE rate_limit_counters")
    yield pool
    await pool.close()


async def test_increment_returns_running_count(db_pool):
    from rate_limit import increment_and_count

    key = "chat:ip:1.2.3.4"
    c1 = await increment_and_count(db_pool, key, window=timedelta(minutes=1))
    c2 = await increment_and_count(db_pool, key, window=timedelta(minutes=1))
    c3 = await increment_and_count(db_pool, key, window=timedelta(minutes=1))

    assert c1 == 1
    assert c2 == 2
    assert c3 == 3


async def test_different_keys_isolated(db_pool):
    from rate_limit import increment_and_count

    a = await increment_and_count(db_pool, "chat:ip:1.2.3.4", window=timedelta(minutes=1))
    b = await increment_and_count(db_pool, "chat:ip:5.6.7.8", window=timedelta(minutes=1))

    assert a == 1
    assert b == 1


async def test_check_rate_limit_raises_on_exceed(db_pool):
    from rate_limit import RateLimitExceeded, check_rate_limit

    key = "chat:ip:9.9.9.9"
    # 3 allowed
    for _ in range(3):
        await check_rate_limit(db_pool, key, limit=3, window=timedelta(minutes=1))

    # 4th raises
    with pytest.raises(RateLimitExceeded) as exc:
        await check_rate_limit(db_pool, key, limit=3, window=timedelta(minutes=1))
    assert exc.value.retry_after_seconds > 0
