"""MSentry probes for OG-RAG failure modes.

Four probes feed the canonical health_bot.notify() helper (which routes to
project-local Telegram AND MSentry's /feedback endpoint):

  1. empty_retrieval_probe  — every PROBE_INTERVAL_SECS, a known-good query
     must return >0 hyperedges from pgvector ANN search.

  2. embedding_health_probe — same cadence; calls Gemini embedding API on a
     trivial input. 5xx is alerted separately from generation 5xx so we can
     tell embedding outages from generation outages.

  3. check_citations()      — synchronous helper called from query handlers.
     Regexes neutral citations out of an answer, verifies each exists as a
     Case node in ontology_node; logs/alerts unknowns ("hallucinated").

  4. extraction_stall_probe — every PROBE_INTERVAL_SECS, queries the
     document-uploader's judgments table for rows stuck in 'extracting' for
     >1h. >50 such rows triggers a warn. Skipped silently if
     UPLOADER_DATABASE_URL is unset (separate DB from rag-api's).

The scheduler is launched from FastAPI's lifespan; it is cooperative and
cancellable. Every probe is wrapped so a probe failure never takes down the
loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import asyncpg
from health_bot import notify

from ograg.embed import embed_one
from ograg.retriever import retrieve
from ograg.store import get_pool

logger = logging.getLogger(__name__)

# Tunables (env-overridable for tests / staging)
PROBE_INTERVAL_SECS = int(os.environ.get("OGRAG_PROBE_INTERVAL_SECS", "300"))  # 5 min
KNOWN_GOOD_QUERY = os.environ.get(
    "OGRAG_KNOWN_GOOD_QUERY",
    "What is direct discrimination under the Equality Act 2010?",
)
STALL_THRESHOLD_ROWS = int(os.environ.get("OGRAG_STALL_THRESHOLD_ROWS", "50"))
STALL_THRESHOLD_HOURS = int(os.environ.get("OGRAG_STALL_THRESHOLD_HOURS", "1"))

# Neutral citation regex — UK form, e.g. [2021] UKSC 12, [2024] EWCA Civ 345,
# [2023] UKEAT 0123/22, [2020] UKUT 100 (AAC). Court tokens: EWCA, EWHC,
# UKSC, UKEAT, UKUT, EAT, IAC, AAC, TCC, Comm, Civ, Crim, Admin, Fam, Ch, QB, KB.
CITATION_REGEX = re.compile(
    r"\[\s*(?:19|20)\d{2}\s*\]\s*"
    r"(?:UKSC|UKPC|UKHL|UKEAT|UKUT|EAT|EWCA(?:\s+(?:Civ|Crim))?|EWHC|IAC|AAC|TCC)"
    r"\s*\d+(?:/\d{2,4})?"
    r"(?:\s*\((?:Ch|QB|KB|Admin|Fam|TCC|Comm|Pat|AAC|IAC|TC|LC)\))?",
    re.IGNORECASE,
)


def _normalize_citation(c: str) -> str:
    """Collapse internal whitespace and strip space inside brackets so
    '[ 2021 ]  UKSC  12' == '[2021] UKSC 12'."""
    s = re.sub(r"\s+", " ", c).strip().upper()
    s = re.sub(r"\[\s*", "[", s)
    s = re.sub(r"\s*\]", "]", s)
    return s


# ── Probe 3: hallucinated citation check ────────────────────────────────────
async def check_citations(answer: str, db_url: str | None = None) -> list[str]:
    """Extract neutral citations from `answer` and return those NOT present
    in ontology_node (type='Case'). Fires a warn for each unknown.

    Safe to call on every served answer — bails silently if:
      - the answer has no citations,
      - DATABASE_URL is unset, or
      - the ontology_node table doesn't exist yet (pre-cutover deploys).
    """
    if not answer:
        return []
    cites = {_normalize_citation(m.group(0)) for m in CITATION_REGEX.finditer(answer)}
    if not cites:
        return []
    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        return []
    # Acquire from the shared bounded pool (same DSN as the retrieval path) rather
    # than opening a fresh asyncpg.connect() per served answer. check_citations runs
    # on EVERY answer, so an unbounded connect here re-exhausted Postgres
    # max_connections under concurrency even after the retrieval path was pooled —
    # surfaced as "sorry, too many clients already" via ograg.retrieval_probe.
    try:
        pool = await get_pool(url)
        conn = await pool.acquire()
    except Exception as e:  # connection problem — don't penalise the user request
        logger.debug("check_citations: db connect failed: %s", e)
        return []
    try:
        exists = await conn.fetchval("SELECT to_regclass('ontology_node') IS NOT NULL")
        if not exists:
            return []
        # Normalize whitespace on both sides so stored values with stray
        # double-spaces or non-breaking spaces still match the regex-extracted
        # (already whitespace-collapsed) citations.
        rows = await conn.fetch(
            r"""
            SELECT regexp_replace(
                     regexp_replace(
                       regexp_replace(UPPER(attrs->>'neutral_citation'), '\s+', ' ', 'g'),
                       '\[\s*', '[', 'g'),
                     '\s*\]', ']', 'g') AS nc
            FROM ontology_node
            WHERE type = 'Case'
              AND regexp_replace(
                    regexp_replace(
                      regexp_replace(UPPER(attrs->>'neutral_citation'), '\s+', ' ', 'g'),
                      '\[\s*', '[', 'g'),
                    '\s*\]', ']', 'g') = ANY($1::text[])
            """,
            list(cites),
        )
        known = {r["nc"] for r in rows if r["nc"]}
    finally:
        await pool.release(conn)
    unknown = sorted(cites - known)
    if unknown:
        preview = ", ".join(unknown[:3])
        more = f" (+{len(unknown) - 3} more)" if len(unknown) > 3 else ""
        notify(
            "warn",
            "ograg.hallucinated_citation",
            f"served answer cites unknown case(s): {preview}{more}",
            citations=", ".join(unknown[:6]),
            total=len(unknown),
        )
    return unknown


# ── Probe 1: empty retrieval ────────────────────────────────────────────────
async def _empty_retrieval_probe() -> None:
    try:
        hits = await retrieve(KNOWN_GOOD_QUERY, k=5)
    except Exception as e:
        notify("error", "ograg.retrieval_probe", f"retrieval probe raised: {e}", query=KNOWN_GOOD_QUERY)
        return
    if not hits:
        notify(
            "error",
            "ograg.retrieval_empty",
            "ANN search returned 0 hyperedges for known-good query",
            query=KNOWN_GOOD_QUERY,
        )


# ── Probe 2: embedding API health ───────────────────────────────────────────
async def _embedding_health_probe() -> None:
    try:
        vec = await embed_one("ping")
        if not vec or len(vec) == 0:
            notify("error", "ograg.embedding_empty", "Gemini embedding returned empty vector")
    except Exception as e:
        msg = str(e)
        # Heuristic 5xx detection — google-genai surfaces server errors with
        # "500", "503", "INTERNAL", "UNAVAILABLE" in the exception text.
        is_5xx = any(tok in msg for tok in ("500", "502", "503", "504", "INTERNAL", "UNAVAILABLE"))
        notify(
            "error" if is_5xx else "warn",
            "ograg.embedding_5xx" if is_5xx else "ograg.embedding_error",
            f"Gemini embedding probe failed: {type(e).__name__}: {msg[:300]}",
        )


# ── Probe 4: extraction worker stalled ──────────────────────────────────────
async def _extraction_stall_probe() -> None:
    url = os.environ.get("UPLOADER_DATABASE_URL")
    if not url:
        return  # silent — separate DB from rag-api's, not always configured
    try:
        conn = await asyncpg.connect(url)
    except Exception as e:
        logger.debug("stall probe: uploader db connect failed: %s", e)
        return
    try:
        exists = await conn.fetchval("SELECT to_regclass('judgments') IS NOT NULL")
        if not exists:
            return
        stalled = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM judgments
            WHERE ograg_status = 'extracting'
              AND updated_at < NOW() - INTERVAL '{STALL_THRESHOLD_HOURS} hours'
            """
        )
    finally:
        await conn.close()
    if stalled and stalled > STALL_THRESHOLD_ROWS:
        notify(
            "warn",
            "ograg.extraction_stalled",
            f"{stalled} judgments stuck in 'extracting' > {STALL_THRESHOLD_HOURS}h",
            stalled=stalled,
            threshold=STALL_THRESHOLD_ROWS,
        )


# ── Scheduler ───────────────────────────────────────────────────────────────
PROBES: tuple[tuple[str, Any], ...] = (
    ("empty_retrieval", _empty_retrieval_probe),
    ("embedding_health", _embedding_health_probe),
    ("extraction_stall", _extraction_stall_probe),
)


async def _run_once() -> None:
    for name, fn in PROBES:
        try:
            await fn()
        except Exception:
            logger.exception("ograg.probe %s crashed", name)


async def run_forever(interval_secs: int | None = None, jitter_first: bool = True) -> None:
    """Run all probes in a loop. Cancellable via task.cancel().

    `jitter_first=True` waits the interval before the first run so app
    startup is not blocked by probe latency.
    """
    interval = interval_secs or PROBE_INTERVAL_SECS
    if jitter_first:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
    while True:
        await _run_once()
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
