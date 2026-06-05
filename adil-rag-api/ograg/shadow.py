"""P9 shadow logging — run OG-RAG alongside the live FST answer and log it.

User traffic is served by FST (the default). When ``RAG_SHADOW=1``, every real
query also fires a background OG-RAG run whose answer is written to the
``eval_run`` table with ``backend='ograg_shadow'`` and **never returned to the
user**. Failures here must not affect the user response — every exception path
is swallowed and logged at WARNING.

The daily eval suite (P8) re-runs against fresh shadow data over a 7-day window
to watch for regressions vs. the first eval. End of week → gate decides P10.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from ograg.store import get_pool

logger = logging.getLogger(__name__)

# Tunable upper bound — if OG-RAG hangs or runs very slow we don't want shadow
# tasks piling up. Cap each shadow run at ~30s.
SHADOW_TIMEOUT_SECONDS = 30.0


def shadow_enabled() -> bool:
    """True if shadow mode is on (``RAG_SHADOW=1`` / ``true`` / ``yes``)."""
    return os.environ.get("RAG_SHADOW", "0").strip().lower() in ("1", "true", "yes", "on")


def fire_and_forget_shadow(
    query_text: str,
    *,
    max_sources: int = 10,
    include_viability: bool = False,
    conversation_history: list[dict[str, str]] | None = None,
) -> None:
    """Schedule a shadow OG-RAG run without awaiting it.

    Called from the FST path right after the live response is computed. Returns
    immediately; the shadow task runs concurrently and writes to ``eval_run``
    when done. Any failure is logged but never surfaced to the caller.
    """
    if not shadow_enabled():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Not in an async context (shouldn't happen from rag_service.query, but
        # belt-and-braces).
        logger.debug("shadow: no running loop, skipping")
        return

    task = loop.create_task(
        _run_shadow(
            query_text,
            max_sources=max_sources,
            include_viability=include_viability,
            conversation_history=conversation_history,
        )
    )
    # Attach a done-callback so an unhandled exception in the shadow task does
    # not produce a "Task exception was never retrieved" warning at GC time.
    task.add_done_callback(_log_task_exception)


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    except Exception:  # pragma: no cover  — defensive
        return
    if exc is not None:
        logger.warning("ograg shadow task ended with unhandled exception: %s", exc)


async def _run_shadow(
    query_text: str,
    *,
    max_sources: int,
    include_viability: bool,
    conversation_history: list[dict[str, str]] | None,
) -> None:
    """Actual shadow execution. Never raises."""
    start = time.time()
    try:
        # Late import: avoid circular dep on rag_service at module load.
        from ograg.backend import answer as ograg_answer

        result = await asyncio.wait_for(
            ograg_answer(
                query_text,
                max_sources=max_sources,
                include_viability=include_viability,
                conversation_history=conversation_history,
            ),
            timeout=SHADOW_TIMEOUT_SECONDS,
        )
        ans, sources, usage, _metadata, _viability, _checklist = result
        latency_ms = int((time.time() - start) * 1000)
        await _log_success(
            query_text=query_text,
            answer=ans,
            sources=sources,
            latency_ms=latency_ms,
            cost_usd=getattr(usage, "estimated_cost_usd", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            conversation_history=conversation_history,
        )
    except TimeoutError:
        latency_ms = int((time.time() - start) * 1000)
        logger.warning("ograg shadow timed out after %d ms", latency_ms)
        await _log_failure(
            query_text=query_text,
            error=f"timeout after {SHADOW_TIMEOUT_SECONDS}s",
            latency_ms=latency_ms,
            conversation_history=conversation_history,
        )
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        # Keep this WARNING — shadow regressions need to be visible in logs but
        # are not user-impacting, so not ERROR.
        logger.warning("ograg shadow failed: %s", e)
        await _log_failure(
            query_text=query_text,
            error=f"{type(e).__name__}: {e}",
            latency_ms=latency_ms,
            conversation_history=conversation_history,
        )


def _sources_to_json(sources: list[Any] | None) -> str:
    if not sources:
        return "[]"
    items: list[dict[str, Any]] = []
    for s in sources:
        if hasattr(s, "model_dump"):
            items.append(s.model_dump(mode="json"))
        elif isinstance(s, dict):
            items.append(s)
        else:
            items.append({"repr": repr(s)})
    return json.dumps(items, default=str)


def _history_to_json(history: list[dict[str, str]] | None) -> str | None:
    if not history:
        return None
    try:
        return json.dumps(history, default=str)
    except Exception:
        return None


async def _log_success(
    *,
    query_text: str,
    answer: str,
    sources: list[Any],
    latency_ms: int,
    cost_usd: float | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    conversation_history: list[dict[str, str]] | None,
) -> None:
    await _insert_row(
        backend="ograg_shadow",
        query_text=query_text,
        answer=answer,
        sources_json=_sources_to_json(sources),
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        error=None,
        history_json=_history_to_json(conversation_history),
    )


async def _log_failure(
    *,
    query_text: str,
    error: str,
    latency_ms: int,
    conversation_history: list[dict[str, str]] | None,
) -> None:
    await _insert_row(
        backend="ograg_shadow",
        query_text=query_text,
        answer=None,
        sources_json="[]",
        latency_ms=latency_ms,
        cost_usd=None,
        prompt_tokens=None,
        completion_tokens=None,
        error=error,
        history_json=_history_to_json(conversation_history),
    )


async def _insert_row(
    *,
    backend: str,
    query_text: str,
    answer: str | None,
    sources_json: str,
    latency_ms: int | None,
    cost_usd: float | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    error: str | None,
    history_json: str | None,
) -> None:
    """Best-effort insert into eval_run. Never raises."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        logger.warning("ograg shadow: DATABASE_URL not set, dropping log row")
        return
    # Acquire from the shared bounded pool (same DSN as the retrieval path)
    # rather than opening a fresh asyncpg.connect() per call. With RAG_SHADOW=1
    # this insert runs fire-and-forget on EVERY served FST query, so an
    # unbounded connect here re-exhausted Postgres max_connections under
    # concurrency even after the retrieval + check_citations paths were pooled —
    # surfaced as "sorry, too many clients already" via ograg.retrieval_probe.
    try:
        pool = await get_pool(dsn)
        conn = await pool.acquire()
    except Exception as e:
        logger.warning("ograg shadow: pool acquire failed: %s", e)
        return
    try:
        await conn.execute(
            """
            INSERT INTO eval_run
              (backend, query_text, answer, sources, latency_ms, cost_usd,
               prompt_tokens, completion_tokens, error, conversation_history)
            VALUES
              ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10::jsonb)
            """,
            backend,
            query_text,
            answer,
            sources_json,
            latency_ms,
            cost_usd,
            prompt_tokens,
            completion_tokens,
            error,
            history_json,
        )
    except Exception as e:
        logger.warning("ograg shadow: insert failed: %s", e)
    finally:
        try:
            await pool.release(conn)
        except Exception:
            pass
