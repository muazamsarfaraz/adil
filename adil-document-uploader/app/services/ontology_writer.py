"""Cross-DB writer that promotes ``ParsedAct`` trees into rag-api's
``ontology_node`` table via raw asyncpg.

Stays a no-op when:
  - ``RAG_DATABASE_URL`` is not set, OR
  - the ``ontology_node`` table does not yet exist on the target DB.

The second guard lets this code ship before P1 (alembic 004 — ontology
schema) lands in rag-api. As soon as P1 ships, this writer activates on
the next ``fetch_acts`` run without further code changes.

Node shapes (matches the planned ontology in
``docs/plans/2026-05-17-ograg-migration.md`` §5):

  Statute    — one per Act; attrs: {name, year, leg_type, leg_number, url}
  Section    — one per ActSection; attrs: {number, title, statute_id, ...}
  Subsection — one per ActSubsection; attrs: {number, section_id, ...}
"""

from __future__ import annotations

import json
import logging
import uuid

import asyncpg

from app.services.legislation_client import ParsedAct

logger = logging.getLogger(__name__)


# Stable namespace for deriving UUIDv5 ids from natural keys (leg_type/year/num/...).
# Keeps re-ingests idempotent without needing a lookup round-trip.
_NS = uuid.UUID("d8e8a8e8-1d0c-4b87-9d76-1f7e1fa1ad11")


def _statute_id(leg_type: str, year: int, leg_number: int) -> uuid.UUID:
    return uuid.uuid5(_NS, f"statute:{leg_type}/{year}/{leg_number}")


def _section_id(statute_id: uuid.UUID, number: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"section:{statute_id}:{number}")


def _subsection_id(section_id: uuid.UUID, number: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"subsection:{section_id}:{number}")


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM information_schema.tables WHERE table_name = $1",
        table,
    )
    return row is not None


async def write_act_to_ontology(
    rag_database_url: str | None,
    act: ParsedAct,
) -> int:
    """Write Statute + Section + Subsection nodes for one Act.

    Returns the number of node rows upserted. Returns 0 (no-op) if
    ``rag_database_url`` is unset or ``ontology_node`` does not yet exist.
    """
    if not rag_database_url:
        logger.debug("RAG_DATABASE_URL unset — skipping ontology write for %s", act.name)
        return 0

    conn = await asyncpg.connect(rag_database_url)
    try:
        if not await _table_exists(conn, "ontology_node"):
            logger.info(
                "ontology_node table not yet present in rag-api DB — "
                "skipping ontology write for %s (P1 hasn't shipped yet?)",
                act.name,
            )
            return 0

        return await _write_act(conn, act)
    finally:
        await conn.close()


async def _write_act(conn: asyncpg.Connection, act: ParsedAct) -> int:
    """Idempotent ON CONFLICT-DO-UPDATE write of one Act's ontology subtree.

    Assumes ``ontology_node(id UUID PK, type TEXT, attrs JSONB, ...)``
    per the OG-RAG migration plan §5. The actual P1 alembic may add more
    columns (e.g. ``embedding``); we leave those NULL for now.
    """
    written = 0
    statute_uuid = _statute_id(act.leg_type, act.year, act.leg_number)
    statute_attrs = {
        "name": act.name,
        "year": act.year,
        "leg_type": act.leg_type,
        "leg_number": act.leg_number,
        "url": act.url,
    }

    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO ontology_node (id, type, attrs)
            VALUES ($1, 'Statute', $2::jsonb)
            ON CONFLICT (id) DO UPDATE
              SET type = EXCLUDED.type,
                  attrs = EXCLUDED.attrs
            """,
            statute_uuid,
            json.dumps(statute_attrs),
        )
        written += 1

        for section in act.sections:
            section_uuid = _section_id(statute_uuid, section.number)
            section_attrs = {
                "number": section.number,
                "title": section.title,
                "statute_id": str(statute_uuid),
                "text": section.text,
            }
            await conn.execute(
                """
                INSERT INTO ontology_node (id, type, attrs)
                VALUES ($1, 'Section', $2::jsonb)
                ON CONFLICT (id) DO UPDATE
                  SET type = EXCLUDED.type,
                      attrs = EXCLUDED.attrs
                """,
                section_uuid,
                json.dumps(section_attrs),
            )
            written += 1

            for sub in section.subsections:
                sub_uuid = _subsection_id(section_uuid, sub.number)
                sub_attrs = {
                    "number": sub.number,
                    "section_id": str(section_uuid),
                    "text": sub.text,
                }
                await conn.execute(
                    """
                    INSERT INTO ontology_node (id, type, attrs)
                    VALUES ($1, 'Subsection', $2::jsonb)
                    ON CONFLICT (id) DO UPDATE
                      SET type = EXCLUDED.type,
                          attrs = EXCLUDED.attrs
                    """,
                    sub_uuid,
                    json.dumps(sub_attrs),
                )
                written += 1

    return written
