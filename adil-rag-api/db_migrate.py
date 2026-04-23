"""Idempotent SQL migration runner for adil-rag-api.

Reads migrations/*.sql in filename order and executes them inside a transaction.
All DDL uses IF NOT EXISTS so re-running is safe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations(database_url: str) -> None:
    """Apply all .sql files in migrations/ in filename order. Idempotent."""
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
