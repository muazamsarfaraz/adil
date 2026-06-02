"""Anonymised conversation logging for AskAdil.

Logs conversation metadata to Postgres for analytics without storing PII.
All message content is summarised into topic categories — no raw text stored.

Tables:
  - conversation_logs       (always-on metadata, no raw text)
  - debug_conversation_logs (raw query/response/sources, gated by DEBUG_LOG_RAW=1)

The debug table is empty by default; flip DEBUG_LOG_RAW=1 on the rag-api
service only while actively debugging a prod issue, then back to 0. Rows are
auto-pruned after 7 days regardless.
"""

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

# Lazy connection pool
_pool = None
_pool_lock = asyncio.Lock()

# Gate for raw query/response capture. Off by default — flip to "1" on Railway
# only while debugging a specific issue.
DEBUG_LOG_RAW = os.getenv("DEBUG_LOG_RAW", "0") == "1"
DEBUG_LOG_TTL_DAYS = int(os.getenv("DEBUG_LOG_TTL_DAYS", "7"))
# Prune roughly every Nth write so cleanup runs without a separate scheduler.
_DEBUG_PRUNE_EVERY = 100
_debug_write_counter = 0

TOPIC_KEYWORDS = {
    "workplace_discrimination": [
        "employer",
        "work",
        "job",
        "fired",
        "dismissed",
        "colleague",
        "manager",
        "office",
        "workplace",
        "employment",
    ],
    "hate_crime": ["hate", "attack", "assault", "threat", "slur", "abuse", "violence", "racist", "islamophob"],
    "online_hate": [
        "online",
        "social media",
        "twitter",
        "facebook",
        "instagram",
        "youtube",
        "post",
        "comment",
        "tiktok",
    ],
    "education": ["school", "university", "teacher", "student", "college", "education"],
    "housing": ["landlord", "tenant", "housing", "rent", "evict", "accommodation"],
    "policing": ["police", "stop and search", "arrest", "officer"],
    "public_services": ["hospital", "nhs", "council", "government", "service"],
    "hijab_religious_dress": ["hijab", "niqab", "headscarf", "beard", "religious dress", "prayer"],
    "compensation": ["compensation", "sue", "tribunal", "claim", "vento", "solicitor"],
}

JURISDICTION_KEYWORDS = {
    "england": ["england", "london", "manchester", "birmingham", "english"],
    "wales": ["wales", "cardiff", "welsh"],
    "scotland": ["scotland", "glasgow", "edinburgh", "scottish"],
    "northern_ireland": ["northern ireland", "belfast", "ni"],
}


def _classify_topic(text: str) -> str:
    """Classify conversation topic from message text. Returns category, not content."""
    text_lower = text.lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general_enquiry"


def _detect_jurisdiction(text: str) -> str | None:
    """Detect jurisdiction from message text."""
    text_lower = text.lower()
    for jurisdiction, keywords in JURISDICTION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return jurisdiction
    return None


async def _get_pool():
    """Lazy-init the asyncpg connection pool."""
    global _pool
    async with _pool_lock:
        if _pool is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                return None
            try:
                import asyncpg

                _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
                # Create table if not exists
                async with _pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS conversation_logs (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            endpoint VARCHAR(50) NOT NULL,
                            topic VARCHAR(50),
                            jurisdiction VARCHAR(30),
                            message_count INT DEFAULT 1,
                            has_urls BOOLEAN DEFAULT FALSE,
                            has_images BOOLEAN DEFAULT FALSE,
                            viability_requested BOOLEAN DEFAULT FALSE,
                            report_submitted BOOLEAN DEFAULT FALSE,
                            report_target VARCHAR(50),
                            report_success BOOLEAN,
                            response_time_ms INT,
                            model_used VARCHAR(50),
                            token_count INT
                        )
                    """)
                logger.info("Conversation logging initialised (Postgres)")
            except Exception as e:
                logger.warning("Failed to initialise conversation logging: %s", e)
                _pool = None
                return None
    return _pool


async def get_analytics_summary() -> dict | None:
    """Query conversation_logs for aggregate analytics."""
    pool = await _get_pool()
    if not pool:
        return None

    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM conversation_logs")

        topic_rows = await conn.fetch(
            "SELECT topic, COUNT(*) as count FROM conversation_logs GROUP BY topic ORDER BY count DESC LIMIT 10"
        )

        jurisdiction_rows = await conn.fetch(
            "SELECT jurisdiction, COUNT(*) as count FROM conversation_logs "
            "WHERE jurisdiction IS NOT NULL "
            "GROUP BY jurisdiction ORDER BY count DESC"
        )

        report_rows = await conn.fetch(
            "SELECT report_target, COUNT(*) as count, "
            "SUM(CASE WHEN report_success THEN 1 ELSE 0 END) as successes "
            "FROM conversation_logs WHERE report_submitted = true "
            "GROUP BY report_target ORDER BY count DESC"
        )

        recent_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM conversation_logs WHERE timestamp > NOW() - INTERVAL '24 hours'"
        )

        avg_response = await conn.fetchval(
            "SELECT AVG(response_time_ms) FROM conversation_logs WHERE response_time_ms IS NOT NULL"
        )

    return {
        "total_conversations": total or 0,
        "last_24h": recent_24h or 0,
        "avg_response_time_ms": round(avg_response or 0),
        "topics": {row["topic"]: row["count"] for row in topic_rows},
        "jurisdictions": {row["jurisdiction"]: row["count"] for row in jurisdiction_rows},
        "reports": [
            {"target": row["report_target"], "total": row["count"], "successful": row["successes"]}
            for row in report_rows
        ],
    }


async def log_conversation(
    endpoint: str,
    query_text: str = "",
    conversation_history: list[dict] | None = None,
    has_urls: bool = False,
    has_images: bool = False,
    viability_requested: bool = False,
    report_submitted: bool = False,
    report_target: str | None = None,
    report_success: bool | None = None,
    response_time_ms: int | None = None,
    model_used: str | None = None,
    token_count: int | None = None,
):
    """Log anonymised conversation metadata. Fire-and-forget — never blocks the response."""
    try:
        pool = await _get_pool()
        if not pool:
            return

        # Build combined text for classification (no raw text stored)
        combined = query_text
        if conversation_history:
            combined += " " + " ".join(t.get("content", "") for t in conversation_history if t.get("role") == "user")

        topic = _classify_topic(combined)
        jurisdiction = _detect_jurisdiction(combined)
        message_count = len(conversation_history) if conversation_history else 1

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_logs
                (endpoint, topic, jurisdiction, message_count, has_urls, has_images,
                 viability_requested, report_submitted, report_target, report_success,
                 response_time_ms, model_used, token_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
                endpoint,
                topic,
                jurisdiction,
                message_count,
                has_urls,
                has_images,
                viability_requested,
                report_submitted,
                report_target,
                report_success,
                response_time_ms,
                model_used,
                token_count,
            )

    except Exception as e:
        # Never let logging failures affect the user
        logger.debug("Conversation log write failed: %s", e)


async def _maybe_prune_debug_logs(conn) -> None:
    """Delete debug rows older than DEBUG_LOG_TTL_DAYS. Cheap; runs every Nth write."""
    global _debug_write_counter
    _debug_write_counter += 1
    if _debug_write_counter % _DEBUG_PRUNE_EVERY != 1:
        return
    try:
        await conn.execute(
            "DELETE FROM debug_conversation_logs " "WHERE created_at < NOW() - ($1::text || ' days')::interval",
            str(DEBUG_LOG_TTL_DAYS),
        )
    except Exception as e:
        logger.debug("Debug log prune failed: %s", e)


async def log_conversation_raw(
    endpoint: str,
    *,
    conversation_id: str | None = None,
    query: str = "",
    response: str = "",
    sources: list | None = None,
    error: str | None = None,
    response_time_ms: int | None = None,
) -> None:
    """Append raw conversation content to debug_conversation_logs.

    No-op when DEBUG_LOG_RAW != "1". Fire-and-forget — never blocks the
    response and never raises. Rows expire after DEBUG_LOG_TTL_DAYS (default 7).
    """
    if not DEBUG_LOG_RAW:
        return
    try:
        pool = await _get_pool()
        if not pool:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO debug_conversation_logs
                    (conversation_id, endpoint, query, response, sources_json,
                     error, response_time_ms)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                """,
                conversation_id,
                endpoint,
                query or None,
                response or None,
                json.dumps(sources) if sources is not None else None,
                error,
                response_time_ms,
            )
            await _maybe_prune_debug_logs(conn)
    except Exception as e:
        logger.debug("Raw conversation log write failed: %s", e)
