"""arq worker settings — Redis connection, startup/shutdown, and WorkerSettings class."""

from arq.connections import ArqRedis, RedisSettings, create_pool
from redis.asyncio import Redis

from app.config import settings
from app.workers.tasks import (
    classify_reply,
    compose_email,
    evaluate_contact,
    fire_conversion_webhook,
    launch_campaign,
    research_contact,
    send_email_task,
    send_follow_up,
)

# ---------------------------------------------------------------------------
# Redis connection helpers
# ---------------------------------------------------------------------------


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    return RedisSettings.from_dsn(settings.redis_url)


_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Return a singleton ArqRedis pool for enqueueing jobs."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_redis_settings())
    return _arq_pool


async def close_redis():
    """Close the singleton ArqRedis pool."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


def get_raw_redis() -> Redis:
    """Return a plain redis.asyncio.Redis client for rate limiting / locking."""
    return Redis.from_url(settings.redis_url)


# ---------------------------------------------------------------------------
# Worker lifecycle hooks
# ---------------------------------------------------------------------------


async def on_startup(ctx):
    """Called when arq worker starts — initialise Redis and DB connections."""
    # Raw Redis for rate limiting and distributed locks
    ctx["redis"] = get_raw_redis()
    # arq pool for enqueueing child jobs
    ctx["pool"] = await get_arq_pool()


async def on_shutdown(ctx):
    """Called when arq worker shuts down — close all connections."""
    if "redis" in ctx:
        await ctx["redis"].close()
    await close_redis()
    from app.database import dispose_engine

    await dispose_engine()


# ---------------------------------------------------------------------------
# WorkerSettings — run with: arq app.workers.settings.WorkerSettings
# ---------------------------------------------------------------------------


class WorkerSettings:
    """arq worker configuration."""

    redis_settings = get_redis_settings()

    functions = [
        research_contact,
        compose_email,
        send_email_task,
        evaluate_contact,
        send_follow_up,
        launch_campaign,
        fire_conversion_webhook,
        classify_reply,
    ]

    on_startup = on_startup
    on_shutdown = on_shutdown

    # Concurrency
    max_jobs = 10

    # Timeout: 5 minutes per task (research/compose can be slow)
    job_timeout = 300

    # Retry: 3 attempts with exponential backoff
    max_tries = 3

    # Health check every 30 seconds
    health_check_interval = 30

    # Poll Redis every 1 second
    poll_delay = 1.0
