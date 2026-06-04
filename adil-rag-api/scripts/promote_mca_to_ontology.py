"""Promote curated MCA + Court of Protection inline snippets in
``rag_service.py`` to ``ontology_node`` + ``ontology_edge`` rows.

Run-once (idempotent) script. Re-running upserts the same UUIDv5 ids,
so it's safe to re-run after adding more MCA sections / CoP cases to
the inline dicts.

Usage:
    python scripts/promote_mca_to_ontology.py
Env required:
    DATABASE_URL  (or TEST_DATABASE_URL — DATABASE_URL is preferred)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402
from db_migrate import run_migrations  # noqa: E402
from ograg.mca_promote import build_nodes_and_edges, promote_to_db  # noqa: E402

from rag_service import LEGISLATION_SNIPPETS, UK_CASE_LAW, UK_LEGISLATION_URLS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("promote_mca")


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL (or TEST_DATABASE_URL) must be set")

    await run_migrations(db_url)

    nodes, edges = build_nodes_and_edges(
        LEGISLATION_SNIPPETS,
        UK_CASE_LAW,
        UK_LEGISLATION_URLS,
    )
    logger.info("Built %d ontology nodes, %d edges", len(nodes), len(edges))

    conn = await asyncpg.connect(db_url)
    try:
        wn, we = await promote_to_db(conn, nodes, edges)
    finally:
        await conn.close()

    if wn == 0:
        logger.warning(
            "ontology_node table not present — wrote 0 rows. Apply migration 004_ontology_init.sql first.",
        )
    else:
        logger.info("Upserted %d nodes, %d edges into ontology tables", wn, we)


if __name__ == "__main__":
    asyncio.run(main())
