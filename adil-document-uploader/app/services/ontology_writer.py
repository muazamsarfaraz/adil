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
from app.services.ograg_extract import ExtractionResult

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


# ---------------------------------------------------------------------------
# Case extraction writer (used by backfill_ograg)
# ---------------------------------------------------------------------------


async def write_case_extraction(
    rag_database_url: str | None,
    result: ExtractionResult,
) -> tuple[int, int]:
    """Write Case + Paragraph nodes and Refs edges for one judgment.

    Returns ``(nodes_written, edges_written)``. No-op (0, 0) when the rag-api
    DB or its ``ontology_node`` table is not yet available — same guard as
    ``write_act_to_ontology`` so the writer activates as soon as P1 ships.

    Idempotent: all writes are ``INSERT ... ON CONFLICT`` against the
    deterministic node IDs already on the dataclass instances.
    """
    if not rag_database_url:
        logger.debug("RAG_DATABASE_URL unset — skipping case ontology write for %s", result.case.neutral_citation)
        return 0, 0

    conn = await asyncpg.connect(rag_database_url)
    try:
        if not await _table_exists(conn, "ontology_node"):
            logger.info(
                "ontology_node table not yet present in rag-api DB — skipping case ontology write for %s",
                result.case.neutral_citation,
            )
            return 0, 0

        has_edges = await _table_exists(conn, "ontology_edge")
        return await _write_case_extraction(conn, result, has_edges)
    finally:
        await conn.close()


async def _write_case_extraction(
    conn: asyncpg.Connection,
    result: ExtractionResult,
    has_edges: bool,
) -> tuple[int, int]:
    nodes = 0
    edges = 0

    case = result.case
    case_attrs = {
        "neutral_citation": case.neutral_citation,
        "case_name": case.case_name,
        "court": case.court,
        "year": case.year,
    }

    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO ontology_node (id, type, attrs)
            VALUES ($1, 'Case', $2::jsonb)
            ON CONFLICT (id) DO UPDATE
              SET type = EXCLUDED.type,
                  attrs = EXCLUDED.attrs
            """,
            case.node_id,
            json.dumps(case_attrs),
        )
        nodes += 1

        for para in result.paragraphs:
            para_attrs = {
                "case_id": str(case.node_id),
                "index": para.index,
                "number": para.number,
                "text": para.text,
                "sentence_count": para.sentence_count,
            }
            await conn.execute(
                """
                INSERT INTO ontology_node (id, type, attrs)
                VALUES ($1, 'Paragraph', $2::jsonb)
                ON CONFLICT (id) DO UPDATE
                  SET type = EXCLUDED.type,
                      attrs = EXCLUDED.attrs
                """,
                para.node_id,
                json.dumps(para_attrs),
            )
            nodes += 1

            if has_edges:
                edges += await _upsert_edge(conn, case.node_id, para.node_id, "HAS_PARAGRAPH", {"index": para.index})

        if has_edges:
            for ref in result.statute_refs:
                target = ref.resolved_node_id or ref.candidate_node_id
                edges += await _upsert_edge(
                    conn,
                    ref.paragraph_id,
                    target,
                    "CITES_STATUTE",
                    {"slug": ref.statute_slug, "resolved": ref.resolved_node_id is not None},
                )

            for ref in result.section_refs:
                target = ref.resolved_node_id or ref.candidate_node_id
                edges += await _upsert_edge(
                    conn,
                    ref.paragraph_id,
                    target,
                    "CITES_SECTION",
                    {
                        "section": ref.section,
                        "subsection": ref.subsection,
                        "statute_slug": ref.statute_slug,
                        "resolved": ref.resolved_node_id is not None,
                    },
                )

    return nodes, edges


async def _upsert_edge(
    conn: asyncpg.Connection,
    src: uuid.UUID,
    dst: uuid.UUID,
    kind: str,
    attrs: dict,
) -> int:
    """Upsert one ontology_edge row.

    Edge identity is (src_id, dst_id, kind); attrs are overwritten on
    conflict. Returns 1 on success, 0 on no-op (none currently — kept for
    symmetry with node writes).
    """
    await conn.execute(
        """
        INSERT INTO ontology_edge (src_id, dst_id, kind, attrs)
        VALUES ($1, $2, $3, $4::jsonb)
        ON CONFLICT (src_id, dst_id, kind) DO UPDATE
          SET attrs = EXCLUDED.attrs
        """,
        src,
        dst,
        kind,
        json.dumps(attrs),
    )
    return 1


async def case_has_ontology_rows(rag_database_url: str | None, case_node_id: uuid.UUID) -> bool:
    """Check whether a Case node already has any Paragraph children written.

    Used by the backfill to skip judgments that already have ontology rows
    (idempotency). Returns ``False`` when the rag-api DB or ontology_node
    table is not yet available — backfill should then attempt the write so
    it can detect schema readiness on each judgment without manual config.
    """
    if not rag_database_url:
        return False

    conn = await asyncpg.connect(rag_database_url)
    try:
        if not await _table_exists(conn, "ontology_node"):
            return False
        row = await conn.fetchrow(
            """
            SELECT 1 FROM ontology_node
            WHERE type = 'Paragraph'
              AND (attrs ->> 'case_id') = $1
            LIMIT 1
            """,
            str(case_node_id),
        )
        return row is not None
    finally:
        await conn.close()
