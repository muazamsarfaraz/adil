"""Postgres-backed fixed-window rate limiter.

Each (bucket_key, bucket_start) row counts requests in a fixed window.
The window is determined by rounding `now()` down to the window boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg


class RateLimitExceeded(Exception):
    def __init__(self, limit: int, window: timedelta, retry_after_seconds: int):
        self.limit = limit
        self.window = window
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit {limit}/{window} exceeded")


def _bucket_start(window: timedelta, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    seconds = int(now.timestamp())
    window_s = int(window.total_seconds())
    bucket_epoch = (seconds // window_s) * window_s
    return datetime.fromtimestamp(bucket_epoch, tz=UTC)


async def increment_and_count(pool: asyncpg.Pool, key: str, window: timedelta) -> int:
    """Atomically increment the counter for (key, current window) and return the new count."""
    bucket_start = _bucket_start(window)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO rate_limit_counters (bucket_key, bucket_start, count)
            VALUES ($1, $2, 1)
            ON CONFLICT (bucket_key, bucket_start)
            DO UPDATE SET count = rate_limit_counters.count + 1
            RETURNING count
            """,
            key,
            bucket_start,
        )
    return row["count"]


async def check_rate_limit(pool: asyncpg.Pool, key: str, limit: int, window: timedelta) -> int:
    """Increment counter and raise RateLimitExceeded if it passes `limit`."""
    count = await increment_and_count(pool, key, window)
    if count > limit:
        now = datetime.now(UTC)
        bucket_end = _bucket_start(window, now) + window
        retry_after = max(1, int((bucket_end - now).total_seconds()))
        raise RateLimitExceeded(limit=limit, window=window, retry_after_seconds=retry_after)
    return count


@dataclass(frozen=True)
class Limit:
    key_prefix: str
    limit: int
    window: timedelta


async def check_limits(pool: asyncpg.Pool, limits: list[Limit], identity: str) -> None:
    """Apply a list of limits sequentially. Raises RateLimitExceeded on first hit."""
    for limit in limits:
        key = f"{limit.key_prefix}:{identity}"
        await check_rate_limit(pool, key, limit.limit, limit.window)
