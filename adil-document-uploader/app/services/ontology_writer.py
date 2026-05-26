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
from typing import Any

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
    """Write Case + Paragraph + (Pass-2/3) nodes + edges + hyperedges.

    Returns ``(nodes_written, edges_written)``. Hyperedges are counted as
    nodes for the stats summary since each hyperedge owns one row in its
    own table.

    No-op (0, 0) when the rag-api DB or its ``ontology_node`` table is
    not yet available — same guard as ``write_act_to_ontology`` so the
    writer activates as soon as P1 ships.

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
        has_hyperedge = await _table_exists(conn, "hyperedge")
        nodes, edges = await _write_case_extraction(conn, result, has_edges)
        extra_nodes, extra_edges = await _write_pass2_pass3_nodes_and_edges(conn, result, has_edges)
        nodes += extra_nodes
        edges += extra_edges
        if has_hyperedge:
            nodes += await _write_hyperedges(conn, result)
        else:
            logger.debug(
                "hyperedge table not present — skipping %d hyperedges for %s",
                len(result.hyperedges),
                result.case.neutral_citation,
            )
        return nodes, edges
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

    Schema (migrations/004_ontology_init.sql): id UUID PK, source_id UUID,
    target_id UUID, relation TEXT, attrs JSONB. There is no UNIQUE on
    (source_id, target_id, relation) so we derive a deterministic UUID
    from the triple and use ON CONFLICT (id) for upsert semantics.
    """
    edge_id = uuid.uuid5(_NS, f"edge:{src}:{dst}:{kind}")
    await conn.execute(
        """
        INSERT INTO ontology_edge (id, source_id, target_id, relation, attrs)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (id) DO UPDATE
          SET attrs = EXCLUDED.attrs
        """,
        edge_id,
        src,
        dst,
        kind,
        json.dumps(attrs),
    )
    return 1


# ---------------------------------------------------------------------------
# Pass 2 + Pass 3 secondary node/edge writer
# ---------------------------------------------------------------------------


async def _write_pass2_pass3_nodes_and_edges(
    conn: asyncpg.Connection,
    result: ExtractionResult,
    has_edges: bool,
) -> tuple[int, int]:
    """Persist Pass-2 (Topic/Party/Judge/Court) and Pass-3 (referenced
    Case stubs) nodes, plus every entry in ``result.edges`` whose kind is
    one of the Pass-2/3 relations.

    Pass-1 statute/section refs are still handled inline in
    ``_write_case_extraction``; this function complements that path.
    """
    nodes = 0
    edges = 0

    def _node_payload(kind: str, ident: uuid.UUID, attrs: dict) -> tuple[uuid.UUID, str, str]:
        return ident, kind, json.dumps(attrs)

    payloads: list[tuple[uuid.UUID, str, str]] = []

    if result.court is not None:
        payloads.append(
            _node_payload(
                "Court",
                result.court.node_id,
                {"code": result.court.code, "division": result.court.division},
            )
        )
    for t in result.topics:
        payloads.append(_node_payload("Topic", t.node_id, {"slug": t.slug}))
    for p in result.parties:
        payloads.append(_node_payload("Party", p.node_id, {"name": p.name, "role": p.role}))
    for j in result.judges:
        payloads.append(_node_payload("Judge", j.node_id, {"name": j.name}))
    for c in result.referenced_cases:
        payloads.append(
            _node_payload(
                "Case",
                c.node_id,
                {
                    "neutral_citation": c.neutral_citation,
                    "case_name": c.case_name,
                    "court": c.court,
                    "year": c.year,
                    "referenced_only": True,
                },
            )
        )

    async with conn.transaction():
        for ident, kind, attrs_json in payloads:
            await conn.execute(
                """
                INSERT INTO ontology_node (id, type, attrs)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (id) DO UPDATE
                  SET type = EXCLUDED.type,
                      attrs = ontology_node.attrs || EXCLUDED.attrs
                """,
                ident,
                kind,
                attrs_json,
            )
            nodes += 1

        if has_edges:
            for edge in result.edges:
                attrs: dict[str, Any] = {}
                if edge.paragraph_id is not None:
                    attrs["paragraph_id"] = str(edge.paragraph_id)
                edges += await _upsert_edge(
                    conn,
                    edge.source_id,
                    edge.target_id,
                    edge.kind,
                    attrs,
                )

    return nodes, edges


# ---------------------------------------------------------------------------
# Hyperedge writer
# ---------------------------------------------------------------------------


async def _write_hyperedges(conn: asyncpg.Connection, result: ExtractionResult) -> int:
    """Persist ``HyperedgeNode`` rows. Idempotent on the deterministic
    ``node_id`` (UUIDv5 of the paragraph node_id). Re-running pass 3
    overwrites the embedding + node_ids — schema deliberately allows
    that so a refreshed embedding model can backfill in place.
    """
    if not result.hyperedges:
        return 0

    count = 0
    async with conn.transaction():
        for h in result.hyperedges:
            await conn.execute(
                """
                INSERT INTO hyperedge (
                    id, node_ids, paragraph_text, source_node_id, embedding, attrs
                )
                VALUES ($1, $2::uuid[], $3, $4, $5, $6::jsonb)
                ON CONFLICT (id) DO UPDATE
                  SET node_ids = EXCLUDED.node_ids,
                      paragraph_text = EXCLUDED.paragraph_text,
                      embedding = EXCLUDED.embedding,
                      attrs = EXCLUDED.attrs
                """,
                h.node_id,
                list(h.node_ids),
                h.paragraph_text,
                h.paragraph_id,
                h.embedding,
                json.dumps({"case_id": str(result.case.node_id)}),
            )
            count += 1
    return count


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
