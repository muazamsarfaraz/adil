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
        """Return the top-k nearest chunks by cosine distance (ascending)."""
        conn = self._require_conn()
        rows = await conn.fetch(
            """
            SELECT id,
                   text,
                   source,
                   embedding <=> $1 AS distance
            FROM ograg_chunks
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
