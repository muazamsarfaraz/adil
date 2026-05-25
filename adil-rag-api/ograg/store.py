"""Async pgvector-backed chunk store for OG-RAG.

Reads/writes the ``ograg_chunks`` table provisioned by migration 003.
Embeddings are stored as ``vector(768)``; cosine distance is used for ANN.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector


class Store:
    """Thin async wrapper over a single asyncpg connection."""

    def __init__(self) -> None:
        self._conn: asyncpg.Connection | None = None

    async def connect(self, url: str) -> None:
        self._conn = await asyncpg.connect(url)
        # register_vector lets asyncpg encode list[float] as vector(768).
        await register_vector(self._conn)
        # Probe every IVFFlat list so recall is full while the corpus is small.
        # With <50k chunks this is effectively a sequential scan and avoids
        # the "empty result" gotcha when partitions are sparse.
        await self._conn.execute("SET ivfflat.probes = 10")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> asyncpg.Connection:
        if self._conn is None:
            raise RuntimeError("Store.connect() must be called before use")
        return self._conn

    async def insert_chunk(
        self,
        *,
        text: str,
        source: dict[str, Any],
        embedding: list[float],
        chunk_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Insert one chunk. ON CONFLICT (id) DO NOTHING for idempotency."""
        conn = self._require_conn()
        cid = chunk_id or uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO ograg_chunks (id, text, source, embedding)
            VALUES ($1, $2, $3::jsonb, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            cid,
            text,
            json.dumps(source),
            embedding,
        )
        return cid

    async def search(
        self,
        *,
        query_embedding: list[float],
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the top-k nearest chunks by cosine distance (ascending).

        Filters out rows with NULL ``embedding`` defensively — these appear
        after migration 008 dimensionally-resized the column, NULLing all
        existing data until the seeder re-populates. Without this filter,
        ``r['distance']`` is None and ``float()`` raises TypeError.
        """
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            SELECT id,
                   text,
                   source,
                   embedding <=> $1 AS distance
            FROM ograg_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            query_embedding,
            k,
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            src = r["source"]
            if isinstance(src, str):
                src = json.loads(src)
            out.append(
                {
                    "id": r["id"],
                    "text": r["text"],
                    "source": src or {},
                    "distance": float(r["distance"]),
                }
            )
        return out

    async def insert_hyperedge(
        self,
        *,
        node_ids: list[uuid.UUID],
        paragraph_text: str,
        embedding: list[float],
        source_node_id: uuid.UUID | None = None,
        attrs: dict[str, Any] | None = None,
        hyperedge_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Insert one hyperedge. ON CONFLICT (id) DO NOTHING for idempotency."""
        conn = self._require_conn()
        hid = hyperedge_id or uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO hyperedge (id, node_ids, paragraph_text, source_node_id, embedding, attrs)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            hid,
            node_ids,
            paragraph_text,
            source_node_id,
            embedding,
            json.dumps(attrs or {}),
        )
        return hid

    async def ann_search_hyperedges(
        self,
        *,
        query_embedding: list[float],
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the top-k nearest hyperedges by cosine similarity.

        Each result dict has ``id``, ``node_ids`` (list[UUID]),
        ``paragraph_text``, ``source_node_id``, ``attrs``, ``distance``
        (cosine distance, 0..2) and ``similarity`` (= ``1 - distance``,
        higher is more similar — what Algo-1 cover scoring expects).
        """
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            SELECT id,
                   node_ids,
                   paragraph_text,
                   source_node_id,
                   attrs,
                   embedding <=> $1 AS distance
            FROM hyperedge
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            query_embedding,
            top_k,
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            attrs = r["attrs"]
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            distance = float(r["distance"])
            out.append(
                {
                    "id": r["id"],
                    "node_ids": list(r["node_ids"] or []),
                    "paragraph_text": r["paragraph_text"],
                    "source_node_id": r["source_node_id"],
                    "attrs": attrs or {},
                    "distance": distance,
                    "similarity": max(0.0, 1.0 - distance),
                }
            )
        return out

    async def fetch_citation_nodes(
        self,
        node_ids: list[uuid.UUID],
    ) -> list[dict[str, Any]]:
        """Look up ontology_node rows for the given ids — for citation building.

        Returns ``[{id, type, attrs}, ...]`` in arbitrary order. Caller
        re-orders. Used by the retriever to turn hyperedge.node_ids into
        Source records (statute s.X, case ¶Y).
        """
        if not node_ids:
            return []
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            SELECT id, type, attrs
            FROM ontology_node
            WHERE id = ANY($1::uuid[])
            """,
            node_ids,
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            attrs = r["attrs"]
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            out.append({"id": r["id"], "type": r["type"], "attrs": attrs or {}})
        return out
