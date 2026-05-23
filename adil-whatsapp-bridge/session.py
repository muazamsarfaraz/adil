"""
session.py — Postgres-backed per-phone session state for adil-whatsapp-bridge.

Each phone number owns one row in `wa_sessions`. The row carries:
  - jurisdiction (EW / SCO / NI) chosen on first contact
  - rolling conversation history (last 50 turns, JSONB)
  - consent_at — set when the user accepts the privacy notice
  - rate-limit counters (per-minute and per-day windows)
The table is created by ``migrations/001_wa_sessions.sql`` via db_migrate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 50
SESSION_TTL = timedelta(hours=24)


@dataclass
class Session:
    phone: str
    jurisdiction: str | None
    history: list[dict[str, str]]
    consent_at: datetime | None
    last_message_at: datetime
    msg_count_minute: int
    msg_minute_start: datetime
    msg_count_day: int
    msg_day_start: datetime

    @property
    def has_consent(self) -> bool:
        return self.consent_at is not None

    @property
    def has_jurisdiction(self) -> bool:
        return self.jurisdiction in {"EW", "SCO", "NI"}

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) - self.last_message_at > SESSION_TTL


async def load(pool: asyncpg.Pool, phone: str) -> Session:
    """Load or create the row for ``phone``. Always returns a Session."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO wa_sessions (phone_e164)
            VALUES ($1)
            ON CONFLICT (phone_e164) DO UPDATE SET phone_e164 = EXCLUDED.phone_e164
            RETURNING phone_e164, jurisdiction, history, consent_at, last_message_at,
                      msg_count_minute, msg_minute_start, msg_count_day, msg_day_start
            """,
            phone,
        )
    history_raw = row["history"]
    if isinstance(history_raw, str):
        history = json.loads(history_raw or "[]")
    else:
        history = list(history_raw or [])
    return Session(
        phone=row["phone_e164"],
        jurisdiction=row["jurisdiction"],
        history=history,
        consent_at=row["consent_at"],
        last_message_at=row["last_message_at"],
        msg_count_minute=row["msg_count_minute"],
        msg_minute_start=row["msg_minute_start"],
        msg_count_day=row["msg_count_day"],
        msg_day_start=row["msg_day_start"],
    )


async def set_consent(pool: asyncpg.Pool, phone: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE wa_sessions SET consent_at = now() WHERE phone_e164 = $1",
            phone,
        )


async def set_jurisdiction(pool: asyncpg.Pool, phone: str, jurisdiction: str) -> None:
    if jurisdiction not in {"EW", "SCO", "NI"}:
        raise ValueError(f"unknown jurisdiction: {jurisdiction}")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE wa_sessions SET jurisdiction = $1 WHERE phone_e164 = $2",
            jurisdiction,
            phone,
        )


async def append_turn(pool: asyncpg.Pool, phone: str, role: str, content: str) -> None:
    """Append a turn and trim history to the last HISTORY_LIMIT entries."""
    if role not in {"user", "model"}:
        raise ValueError(f"unknown role: {role}")
    turn = {"role": role, "content": content}
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE wa_sessions
            SET history = (
                COALESCE(history, '[]'::jsonb) || $1::jsonb
            ),
                last_message_at = now()
            WHERE phone_e164 = $2
            """,
            json.dumps([turn]),
            phone,
        )
        await conn.execute(
            """
            UPDATE wa_sessions
            SET history = (
                SELECT COALESCE(jsonb_agg(elem ORDER BY idx), '[]'::jsonb)
                FROM (
                    SELECT elem, idx
                    FROM jsonb_array_elements(history) WITH ORDINALITY AS t(elem, idx)
                    ORDER BY idx DESC
                    LIMIT $2
                ) sub
            )
            WHERE phone_e164 = $1
              AND jsonb_array_length(history) > $2
            """,
            phone,
            HISTORY_LIMIT,
        )


async def reset(pool: asyncpg.Pool, phone: str) -> None:
    """Wipe history + jurisdiction but keep the row (and consent)."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE wa_sessions
            SET history = '[]'::jsonb,
                jurisdiction = NULL,
                last_message_at = now()
            WHERE phone_e164 = $1
            """,
            phone,
        )


async def delete(pool: asyncpg.Pool, phone: str) -> None:
    """Right-to-delete: remove the entire session row."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM wa_sessions WHERE phone_e164 = $1", phone)


@dataclass
class RateCheck:
    allowed: bool
    reason: str | None = None
    retry_after_seconds: int = 0


async def check_rate(
    pool: asyncpg.Pool,
    phone: str,
    *,
    per_minute: int,
    per_day: int,
) -> RateCheck:
    """Increment per-phone counters and return whether the message is allowed.

    Rolls the per-minute and per-day windows lazily on each call.
    """
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT msg_count_minute, msg_minute_start, msg_count_day, msg_day_start
            FROM wa_sessions WHERE phone_e164 = $1
            """,
            phone,
        )
        if row is None:
            return RateCheck(allowed=True)

        m_start = row["msg_minute_start"]
        d_start = row["msg_day_start"]
        m_count = row["msg_count_minute"]
        d_count = row["msg_count_day"]

        if now - m_start >= timedelta(minutes=1):
            m_count = 0
            m_start = now
        if now - d_start >= timedelta(days=1):
            d_count = 0
            d_start = now

        if m_count + 1 > per_minute:
            retry = max(1, int(60 - (now - m_start).total_seconds()))
            return RateCheck(allowed=False, reason="minute", retry_after_seconds=retry)
        if d_count + 1 > per_day:
            retry = max(1, int(86400 - (now - d_start).total_seconds()))
            return RateCheck(allowed=False, reason="day", retry_after_seconds=retry)

        await conn.execute(
            """
            UPDATE wa_sessions
            SET msg_count_minute = $2,
                msg_minute_start = $3,
                msg_count_day = $4,
                msg_day_start = $5
            WHERE phone_e164 = $1
            """,
            phone,
            m_count + 1,
            m_start,
            d_count + 1,
            d_start,
        )
    return RateCheck(allowed=True)


async def history_for_rag(pool: asyncpg.Pool, phone: str) -> list[dict[str, str]]:
    """Return history shaped for ``QueryRequest.conversation_history``."""
    s = await load(pool, phone)
    return [{"role": t["role"], "content": t["content"]} for t in s.history]


async def daily_outbound_spend_cents(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT cents_spent FROM wa_outbound_spend WHERE day = CURRENT_DATE")
    return int(row["cents_spent"]) if row else 0


async def record_outbound(pool: asyncpg.Pool, *, cost_cents: int = 1) -> None:
    """Increment today's spend counter. Default 1¢ per message (Meta avg)."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO wa_outbound_spend (day, messages, cents_spent, updated_at)
            VALUES (CURRENT_DATE, 1, $1, now())
            ON CONFLICT (day) DO UPDATE
              SET messages    = wa_outbound_spend.messages + 1,
                  cents_spent = wa_outbound_spend.cents_spent + EXCLUDED.cents_spent,
                  updated_at  = now()
            """,
            cost_cents,
        )
