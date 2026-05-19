"""asyncpg helpers for the OG-RAG ontology tables.

Schema reference: migrations/004_ontology_init.sql, 007_hyperedge.sql.

Node IDs are deterministic UUIDv5 hashes of ``(type, natural_key)`` so the
same logical node always lands on the same UUID — gives us upsert semantics
without a schema-level UNIQUE on natural_key. The natural_key itself is
stored inside ``attrs['natural_key']`` so it can be looked up later.

Used both from rag-api (read path) and from document-uploader's worker
(write path, cross-DB).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import asyncpg

# Namespace UUID for natural-key-derived IDs. Stable forever.
_OGRAG_NS = uuid.UUID("0a8e2c4a-5c2f-5e8d-9b1b-3f4a8c1d0e77")


def make_node_id(node_type: str, natural_key: str) -> uuid.UUID:
    """Deterministic UUIDv5 from (type, natural_key)."""
    return uuid.uuid5(_OGRAG_NS, f"{node_type}:{natural_key}")


@dataclass
class NodeRecord:
    node_type: str
    natural_key: str
    attrs: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    id: uuid.UUID | None = None  # auto-derived from (type, natural_key) on upsert


@dataclass
class EdgeRecord:
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str
    attrs: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID | None = None


class OntologyStore:
    """Thin asyncpg wrapper for ontology_node/edge/hyperedge.

    Single-connection client; create multiple instances for concurrency.
    """

    def __init__(self, database_url: str):
        self._dsn = database_url
        self._conn: asyncpg.Connection | None = None

    async def connect(self) -> None:
        self._conn = await asyncpg.connect(self._dsn)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> asyncpg.Connection:
        if self._conn is None:
            raise RuntimeError("OntologyStore not connected; call connect() first")
        return self._conn

    async def upsert_node(self, node: NodeRecord) -> uuid.UUID:
        """Insert or update by deterministic UUID. Returns node id."""
        conn = self._require_conn()
        node_id = make_node_id(node.node_type, node.natural_key)
        attrs = dict(node.attrs)
        attrs["natural_key"] = node.natural_key

        row = await conn.fetchrow(
            """
            INSERT INTO ontology_node (id, type, attrs, embedding)
            VALUES ($1, $2, $3::jsonb, $4)
            ON CONFLICT (id) DO UPDATE
                SET attrs = EXCLUDED.attrs,
                    embedding = COALESCE(EXCLUDED.embedding, ontology_node.embedding),
                    updated_at = now()
            RETURNING id
            """,
            node_id,
            node.node_type,
            json.dumps(attrs),
            node.embedding,
        )
        return row["id"]

    @staticmethod
    def _row_to_node(row) -> NodeRecord:
        attrs = row["attrs"]
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        # natural_key lives in attrs; surface it to the dataclass.
        nat_key = attrs.get("natural_key", "")
        return NodeRecord(
            id=row["id"],
            node_type=row["type"],
            natural_key=nat_key,
            attrs=attrs,
        )

    async def get_node(self, node_id: uuid.UUID) -> NodeRecord | None:
        conn = self._require_conn()
        row = await conn.fetchrow(
            "SELECT id, type, attrs FROM ontology_node WHERE id = $1",
            node_id,
        )
        return self._row_to_node(row) if row else None

    async def get_node_by_key(self, node_type: str, natural_key: str) -> NodeRecord | None:
        """Re-derives the UUID and fetches. Faster than a JSONB lookup."""
        return await self.get_node(make_node_id(node_type, natural_key))

    async def upsert_edge(self, edge: EdgeRecord) -> uuid.UUID:
        """Insert or update by (source_id, target_id, relation). Returns edge id."""
        conn = self._require_conn()
        # Deterministic edge UUID so re-upserts return the same id.
        edge_id = uuid.uuid5(
            _OGRAG_NS,
            f"edge:{edge.source_id}:{edge.target_id}:{edge.relation}",
        )
        # Lookup first — schema has no UNIQUE constraint on (source, target, relation),
        # so we emulate it manually.
        existing = await conn.fetchval(
            "SELECT id FROM ontology_edge WHERE id = $1",
            edge_id,
        )
        if existing:
            await conn.execute(
                "UPDATE ontology_edge SET attrs = $2::jsonb WHERE id = $1",
                edge_id,
                json.dumps(edge.attrs),
            )
            return existing
        await conn.execute(
            """
            INSERT INTO ontology_edge (id, source_id, target_id, relation, attrs)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            edge_id,
            edge.source_id,
            edge.target_id,
            edge.relation,
            json.dumps(edge.attrs),
        )
        return edge_id

    async def batch_upsert_nodes(self, nodes: list[NodeRecord]) -> list[uuid.UUID]:
        """Sequential upsert in a single transaction. ~10x faster than per-call."""
        conn = self._require_conn()
        ids: list[uuid.UUID] = []
        async with conn.transaction():
            for n in nodes:
                ids.append(await self.upsert_node(n))
        return ids

    async def get_edges_from(
        self, node_id: uuid.UUID, relation: str | None = None, reverse: bool = False
    ) -> list[EdgeRecord]:
        conn = self._require_conn()
        if reverse:
            sql = "SELECT id, source_id, target_id, relation, attrs FROM ontology_edge WHERE target_id = $1"
        else:
            sql = "SELECT id, source_id, target_id, relation, attrs FROM ontology_edge WHERE source_id = $1"
        args: list[Any] = [node_id]
        if relation is not None:
            sql += " AND relation = $2"
            args.append(relation)
        rows = await conn.fetch(sql, *args)
        out: list[EdgeRecord] = []
        for r in rows:
            attrs = r["attrs"]
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            out.append(
                EdgeRecord(
                    id=r["id"],
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    relation=r["relation"],
                    attrs=attrs,
                )
            )
        return out
