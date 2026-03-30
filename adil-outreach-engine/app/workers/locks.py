"""Redis distributed lock context manager.

Prevents race condition between classify_reply and evaluate_contact
operating on the same contact simultaneously (spec section 14.1).
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from redis.asyncio import Redis


class LockAcquisitionError(Exception):
    """Raised when a Redis lock cannot be acquired after max retries."""

    pass


@asynccontextmanager
async def redis_lock(redis: Redis, key: str, timeout: int = 60):
    """Distributed lock using Redis SET NX EX.

    Args:
        redis: Redis connection
        key: Lock key (e.g. "lock:contact:{contact_id}")
        timeout: Lock TTL in seconds (auto-releases if holder crashes)

    Raises:
        LockAcquisitionError: If lock cannot be acquired after retries
    """
    lock_value = str(uuid4())
    acquired = False
    retries = 0
    max_retries = 10

    try:
        while not acquired and retries < max_retries:
            acquired = await redis.set(key, lock_value, nx=True, ex=timeout)
            if not acquired:
                retries += 1
                await asyncio.sleep(0.5 * retries)  # linear backoff

        if not acquired:
            raise LockAcquisitionError(f"Could not acquire lock: {key}")

        yield

    finally:
        # Only release if we still hold the lock (compare-and-delete)
        if acquired:
            current = await redis.get(key)
            if current and current.decode() == lock_value:
                await redis.delete(key)
