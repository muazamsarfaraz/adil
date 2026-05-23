"""
adil-whatsapp-bridge — Meta WhatsApp Cloud API ⇄ adil-rag-api.

Endpoints:
    GET  /webhook   — Meta subscription verification (echoes hub.challenge)
    POST /webhook   — inbound messages from Meta (HMAC-verified)
    GET  /health    — liveness
    GET  /stats     — outbound count + spend today (operator-only)

Inbound flow lives in handler.py. This module is the wiring.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from db_migrate import run_migrations
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, Security
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader
from handler import build_dispatcher, parse_inbound
from meta_client import from_env as meta_from_env
from meta_client import verify_signature
from rag_client import from_env as rag_from_env

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("adil-whatsapp-bridge")

VERSION = "0.1.0"

META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
OPERATOR_KEY = os.environ.get("OPERATOR_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        try:
            await run_migrations(db_url)
            app.state.pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
            logger.info("Postgres pool ready")
        except Exception:
            logger.exception("Postgres init failed — bridge will run in degraded mode")
            app.state.pool = None
    else:
        logger.warning("DATABASE_URL not set — running without persistence")
        app.state.pool = None

    meta = meta_from_env()
    rag = rag_from_env()
    if app.state.pool and meta and rag:
        app.state.dispatcher = build_dispatcher(app.state.pool, meta, rag)
        logger.info("Dispatcher wired (Meta + rag-api + Postgres)")
    else:
        app.state.dispatcher = None
        missing = [
            name for name, ok in (("META_*", meta), ("RAG_API_*", rag), ("DATABASE_URL", app.state.pool)) if not ok
        ]
        logger.warning("Dispatcher disabled — missing: %s", ", ".join(missing))

    try:
        yield
    finally:
        if getattr(app.state, "pool", None):
            await app.state.pool.close()


app = FastAPI(
    title="adil-whatsapp-bridge",
    description="WhatsApp Cloud API bridge for AskAdil",
    version=VERSION,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "version": VERSION,
        "dispatcher_ready": app.state.dispatcher is not None,
    }


operator_header = APIKeyHeader(name="X-Operator-Key", auto_error=False)


def _operator_only(key: str | None = Security(operator_header)) -> None:
    if not OPERATOR_KEY:
        raise HTTPException(status_code=503, detail="Operator key not configured")
    if not key or key != OPERATOR_KEY:
        raise HTTPException(status_code=401, detail="Invalid operator key")


@app.get("/stats")
async def stats(_: None = Security(_operator_only)) -> dict[str, Any]:
    pool = app.state.pool
    if not pool:
        return {"error": "no pool"}
    async with pool.acquire() as conn:
        spend = await conn.fetchrow("SELECT day, messages, cents_spent FROM wa_outbound_spend WHERE day = CURRENT_DATE")
        sessions = await conn.fetchval("SELECT count(*) FROM wa_sessions")
        active_24h = await conn.fetchval(
            "SELECT count(*) FROM wa_sessions WHERE last_message_at > now() - interval '24 hours'"
        )
    return {
        "outbound_today": dict(spend) if spend else {"day": None, "messages": 0, "cents_spent": 0},
        "total_sessions": sessions,
        "active_sessions_24h": active_24h,
    }


@app.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> Any:
    """Echo the challenge if the verify token matches what we configured in Meta."""
    if hub_mode == "subscribe" and META_VERIFY_TOKEN and hub_verify_token == META_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_inbound(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, Any]:
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256, META_APP_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    dispatcher = app.state.dispatcher
    if dispatcher is None:
        logger.warning("Inbound dropped — dispatcher not ready")
        return {"status": "skipped"}

    messages = parse_inbound(payload)
    for m in messages:
        background.add_task(dispatcher.handle, m)
    return {"status": "ok", "accepted": len(messages)}
