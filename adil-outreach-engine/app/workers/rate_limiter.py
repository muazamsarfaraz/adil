"""Redis counter-based rate limiter for API call throttling."""

import asyncio
import time

from redis.asyncio import Redis


class RateLimiter:
    """Rate limiter using Redis INCR + EXPIRE pattern."""

    def __init__(
        self,
        redis: Redis,
        resource: str,
        max_requests: int,
        window_seconds: int,
    ):
        self.redis = redis
        self.resource = resource
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _key(self) -> str:
        bucket = int(time.time() / self.window_seconds)
        return f"ratelimit:{self.resource}:{bucket}"

    async def acquire(self) -> bool:
        """Attempt to acquire a rate limit slot. Returns True if under limit, False if exceeded."""
        key = self._key()
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window_seconds)
        results = await pipe.execute()
        current_count = results[0]
        return current_count <= self.max_requests

    async def wait_for_slot(self, max_wait: float = 120.0) -> bool:
        """Block until a rate limit slot is available. Returns False on timeout."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            if await self.acquire():
                return True
            # Sleep for a fraction of the window before retrying
            await asyncio.sleep(min(1.0, self.window_seconds / 10))
        return False


# Pre-configured limiter factories
def sendgrid_limiter(redis: Redis, daily_limit: int = 100) -> RateLimiter:
    """Rate limiter for SendGrid sends (default 100/day)."""
    return RateLimiter(redis, "sendgrid", max_requests=daily_limit, window_seconds=86400)


def llm_limiter(redis: Redis, provider: str, per_minute: int = 60) -> RateLimiter:
    """Rate limiter for LLM API calls (per provider, per minute)."""
    return RateLimiter(redis, f"llm:{provider}", max_requests=per_minute, window_seconds=60)


def scrape_limiter(redis: Redis, domain: str) -> RateLimiter:
    """Rate limiter for web scraping (1 request per 2 seconds per domain)."""
    return RateLimiter(redis, f"scrape:{domain}", max_requests=1, window_seconds=2)
