"""One-off OG-RAG backfill entrypoint.

Usage from a developer laptop:

    railway run --service adil-document-uploader-worker \
        python -m scripts.run_backfill --limit 500 --kill-switch-usd 50

The script connects to the same DBs the worker uses (``DATABASE_URL`` for
judgments/extraction_spend_usd, ``RAG_API_DATABASE_URL`` for ontology rows)
via the existing ``app.database.async_session`` factory, then calls the same
orchestrator the ``backfill_ograg`` arq task uses. No Redis dependency —
this is plain async, monitored via MSentry's Telegram bot rather than arq.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from app.database import async_session
from app.services.ograg_backfill import BackfillConfig, run_backfill
from app.services.telegram import TelegramNotifier


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run OG-RAG ontology backfill (one-off)")
    p.add_argument("--limit", type=int, default=None, help="Max judgments to process (default: all eligible)")
    p.add_argument(
        "--since-id", type=str, default=None, help="Only consider judgment ids strictly greater than this UUID"
    )
    p.add_argument(
        "--kill-switch-usd",
        type=float,
        default=float(os.getenv("OGRAG_KILL_SWITCH_USD", "50")),
        help="Cumulative USD ceiling; backfill exits early once exceeded (default $50)",
    )
    p.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return p


async def _main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
    )
    log = logging.getLogger("run_backfill")

    rag_db_url = os.getenv("RAG_API_DATABASE_URL") or os.getenv("RAG_DATABASE_URL")
    if not rag_db_url:
        log.warning(
            "RAG_API_DATABASE_URL not set — ontology writes will be a no-op. "
            "Set it before re-running for a real backfill."
        )

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    notifier = TelegramNotifier(tg_token, tg_chat) if tg_token and tg_chat else None
    if notifier is None:
        log.info("Telegram not configured — kill-switch alert will only be logged")

    cfg = BackfillConfig(
        kill_switch_usd=args.kill_switch_usd,
        limit=args.limit,
        since_id=args.since_id,
    )

    log.info(
        "Starting backfill (limit=%s since_id=%s kill_switch=$%.2f)",
        args.limit,
        args.since_id,
        args.kill_switch_usd,
    )
    stats = await run_backfill(
        session_factory=async_session,
        rag_database_url=rag_db_url,
        notifier=notifier,
        config=cfg,
    )

    log.info(
        "Done: selected=%d extracted=%d failed=%d skipped=%d nodes=%d edges=%d spend=$%.4f kill_switch=%s",
        stats.selected,
        stats.extracted,
        stats.failed,
        stats.skipped_already_done,
        stats.nodes_written,
        stats.edges_written,
        stats.spend_usd,
        stats.kill_switch_tripped,
    )

    return 2 if stats.kill_switch_tripped else (0 if stats.failed == 0 else 1)


def main() -> None:
    args = _build_parser().parse_args()
    sys.exit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
