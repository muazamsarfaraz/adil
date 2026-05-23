"""Idempotent SQL migration runner for adil-whatsapp-bridge.

Mirrors adil-rag-api/db_migrate.py: reads migrations/*.sql in filename order
and executes them inside a single transaction. All DDL uses IF NOT EXISTS so
re-running is safe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations(database_url: str) -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.info("No migrations to run")
        return

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            for sql_file in files:
                logger.info("Applying migration %s", sql_file.name)
                sql = sql_file.read_text(encoding="utf-8")
                await conn.execute(sql)
    finally:
        await conn.close()

    logger.info("Applied %d migration(s)", len(files))
