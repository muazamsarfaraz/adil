"""Promote inline MCA / Court of Protection snippets to ontology nodes.

Reads curated entries from ``rag_service.LEGISLATION_SNIPPETS`` and
``rag_service.UK_CASE_LAW`` and emits Statute / Section / Case
``ontology_node`` rows plus contains / interprets / cites
``ontology_edge`` rows.

The inline dicts stay in ``rag_service.py`` (belt-and-braces): they keep
serving as the citation-snippet fallback for the legacy FST path and as
a stable source of truth this promoter reads from. Once the ograg flat
backfill is decommissioned (parent feature, later subtask), retrieval
will join through these ontology rows instead.

Idempotency
-----------
Node IDs are deterministic UUIDv5 in the same namespace
adil-document-uploader's ``ontology_writer`` uses, so when the
legislation.gov.uk acts fetcher (P1.5) re-ingests these same statutes
from CLML, the rows merge cleanly on the natural key.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from typing import Any

import asyncpg

# Match adil-document-uploader/app/services/ontology_writer.py exactly so
# Statute/Section IDs collide on re-ingest from the legislation.gov.uk
# CLML pipeline. Do not change without coordinating both writers.
_NS = uuid.UUID("d8e8a8e8-1d0c-4b87-9d76-1f7e1fa1ad11")

# Separate namespace for nodes / edges the uploader doesn't produce
# (Cases, edges).
_CASE_NS = uuid.UUID("e9f9b9f9-2e1d-5c98-ae87-2f8e2fb2be22")


def _statute_id(leg_type: str, year: int, leg_number: int) -> uuid.UUID:
    return uuid.uuid5(_NS, f"statute:{leg_type}/{year}/{leg_number}")


def _section_id(statute_id: uuid.UUID, number: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"section:{statute_id}:{number}")


def _case_id(neutral_citation: str) -> uuid.UUID:
    return uuid.uuid5(_CASE_NS, f"case:{neutral_citation.strip()}")


def _edge_id(source: uuid.UUID, target: uuid.UUID, relation: str) -> uuid.UUID:
    return uuid.uuid5(_CASE_NS, f"edge:{source}:{relation}:{target}")


# Map inline snippet keys → legislation.gov.uk (leg_type, year, number).
# Parsed from UK_LEGISLATION_URLS in rag_service.py.
MCA_ACT_REFS: dict[str, tuple[str, int, int]] = {
    "Mental Capacity Act 2005": ("ukpga", 2005, 9),
    "Adults with Incapacity (Scotland) Act 2000": ("asp", 2000, 4),
    "Mental Capacity Act (Northern Ireland) 2016": ("nia", 2016, 18),
}

# Cases tagged as MCA / Court of Protection coverage. Source: the curated
# block in rag_service.UK_CASE_LAW headed "Court of Protection / Mental
# Capacity Act landmark cases".
MCA_CASE_NAMES = {
    "Cheshire West and Chester Council v P [2014] UKSC 19",
    "A Local Authority v JB [2021] UKSC 52",
    "Re D (A Child) [2019] UKSC 42",
    "Re MN (Adult) [2015] EWCOP 76",
    "NHS Trust v Y [2018] UKSC 46",
}

# Specific section refs each case interprets, derived from the curated
# summaries. Cases not listed link only to the parent Statute via
# ``interprets``.
CASE_TO_SECTION: dict[str, list[tuple[str, str]]] = {
    # JB's summary explicitly cites s.3 MCA (information-relevance).
    "A Local Authority v JB [2021] UKSC 52": [
        ("Mental Capacity Act 2005", "3"),
    ],
}


@dataclasses.dataclass(frozen=True)
class Node:
    id: uuid.UUID
    type: str
    attrs: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class Edge:
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str
    attrs: dict[str, Any]


def build_nodes_and_edges(
    legislation_snippets: dict[str, dict[str, str]],
    uk_case_law: dict[str, dict[str, str]],
    legislation_urls: dict[str, dict[str, str]],
) -> tuple[list[Node], list[Edge]]:
    """Pure function: turn the inline dicts into (nodes, edges).

    Only entries in ``MCA_ACT_REFS`` / ``MCA_CASE_NAMES`` are emitted.
    Re-runs produce byte-identical results given the same inputs.
    """
    nodes: list[Node] = []
    edges: list[Edge] = []
    statute_id_by_name: dict[str, uuid.UUID] = {}
    section_id_by_key: dict[tuple[str, str], uuid.UUID] = {}

    for act_name, (leg_type, year, leg_number) in MCA_ACT_REFS.items():
        if act_name not in legislation_snippets:
            continue
        statute_uuid = _statute_id(leg_type, year, leg_number)
        statute_id_by_name[act_name] = statute_uuid
        url_meta = legislation_urls.get(act_name, {})
        nodes.append(
            Node(
                id=statute_uuid,
                type="Statute",
                attrs={
                    "name": act_name,
                    "year": year,
                    "leg_type": leg_type,
                    "leg_number": leg_number,
                    "url": url_meta.get("base"),
                    "source": "mca_inline_promote",
                },
            )
        )

        for section_number, snippet in legislation_snippets[act_name].items():
            section_uuid = _section_id(statute_uuid, section_number)
            section_id_by_key[(act_name, section_number)] = section_uuid
            nodes.append(
                Node(
                    id=section_uuid,
                    type="Section",
                    attrs={
                        "number": section_number,
                        "statute_id": str(statute_uuid),
                        "text": snippet,
                        "source": "mca_inline_promote",
                    },
                )
            )
            edges.append(
                Edge(
                    id=_edge_id(statute_uuid, section_uuid, "contains"),
                    source_id=statute_uuid,
                    target_id=section_uuid,
                    relation="contains",
                    attrs={},
                )
            )

    for case_name in MCA_CASE_NAMES:
        if case_name not in uk_case_law:
            continue
        meta = uk_case_law[case_name]
        citation = (meta.get("citation") or case_name).strip()
        case_uuid = _case_id(citation)
        nodes.append(
            Node(
                id=case_uuid,
                type="Case",
                attrs={
                    "name": case_name,
                    "neutral_citation": citation,
                    "court": meta.get("court"),
                    "url": meta.get("url"),
                    "summary": meta.get("summary"),
                    "source": "mca_inline_promote",
                },
            )
        )
        # Every MCA-tagged case interprets the Mental Capacity Act 2005.
        # Scotland / NI mental-capacity cases would link to their own
        # statute instead — add as needed when those cases are curated.
        statute_uuid = statute_id_by_name.get("Mental Capacity Act 2005")
        if statute_uuid is not None:
            edges.append(
                Edge(
                    id=_edge_id(case_uuid, statute_uuid, "interprets"),
                    source_id=case_uuid,
                    target_id=statute_uuid,
                    relation="interprets",
                    attrs={},
                )
            )
        for act_name, section in CASE_TO_SECTION.get(case_name, []):
            section_uuid = section_id_by_key.get((act_name, section))
            if section_uuid is None:
                continue
            edges.append(
                Edge(
                    id=_edge_id(case_uuid, section_uuid, "cites"),
                    source_id=case_uuid,
                    target_id=section_uuid,
                    relation="cites",
                    attrs={},
                )
            )

    return nodes, edges


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM information_schema.tables WHERE table_name = $1",
        table,
    )
    return row is not None


async def promote_to_db(
    conn: asyncpg.Connection,
    nodes: list[Node],
    edges: list[Edge],
) -> tuple[int, int]:
    """Upsert nodes and edges into the ontology tables.

    Returns ``(nodes_written, edges_written)``. Returns ``(0, 0)`` if
    ``ontology_node`` doesn't exist — same belt-and-braces no-op pattern
    used by ``adil-document-uploader/app/services/ontology_writer.py``.
    """
    if not await _table_exists(conn, "ontology_node"):
        return 0, 0

    has_edges = await _table_exists(conn, "ontology_edge")

    written_n = 0
    written_e = 0
    async with conn.transaction():
        for n in nodes:
            await conn.execute(
                """
                INSERT INTO ontology_node (id, type, attrs)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (id) DO UPDATE
                  SET type = EXCLUDED.type,
                      attrs = EXCLUDED.attrs,
                      updated_at = now()
                """,
                n.id,
                n.type,
                json.dumps(n.attrs),
            )
            written_n += 1
        if has_edges:
            for e in edges:
                await conn.execute(
                    """
                    INSERT INTO ontology_edge (id, source_id, target_id, relation, attrs)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (id) DO UPDATE
                      SET relation = EXCLUDED.relation,
                          attrs = EXCLUDED.attrs
                    """,
                    e.id,
                    e.source_id,
                    e.target_id,
                    e.relation,
                    json.dumps(e.attrs),
                )
                written_e += 1
    return written_n, written_e
