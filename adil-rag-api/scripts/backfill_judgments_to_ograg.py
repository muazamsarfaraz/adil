"""P5 — backfill TNA judgments from document-uploader's DB into ograg_chunks.

This is the simplified P5: instead of the full ontology graph (Case →
Paragraph → hyperedge nodes per the spec §5), we chunk each judgment's
``clean_text`` into ~1800-char windows, embed with OpenAI, and insert
straight into the existing flat ``ograg_chunks`` table that the live
retriever already searches.

Why this shape:
  - The deployed retriever (``ograg/retriever.py``) reads ``ograg_chunks``.
    Until the hyperedge retriever (P6) is built, those flat chunks are
    what users actually see.
  - Skipping the LLM extraction pass for now keeps backfill fast and
    cheap (~$0.20 for 1000 judgments). Ontology nodes/edges can be added
    later as a write-side enrichment without touching the read path.

Stable UUIDv5 ids per (judgment_id, chunk_index) so re-runs are idempotent.
ON CONFLICT (id) DO NOTHING in ``ograg_chunks``.

Run from outside Railway with both DB public URLs + OPENAI_API_KEY:

    $env:UPLOADER_DB = "postgresql://postgres:...@junction.proxy.rlwy.net:.../railway"
    $env:RAG_API_DB  = "postgresql://postgres:...@ballast.proxy.rlwy.net:.../railway"
    # OPENAI_API_KEY is injected by `railway run --service adil-rag-api`
    railway run --service adil-rag-api python scripts/backfill_judgments_to_ograg.py

Flags:
    --limit N      Only process the first N judgments (smoke testing).
    --resume       Skip judgments that already have any chunk in ograg_chunks.
                   Default on; pass --no-resume to re-embed everything.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ograg.embed import EMBED_DIM, embed_many  # noqa: E402  (project import)

logger = logging.getLogger("backfill")

# Stable namespace for judgment chunks. Different from the seeder's
# d1c0…001 namespace so static seed chunks and TNA-derived chunks never
# collide on the same UUID.
NAMESPACE = uuid.UUID("d1c0b0a0-0000-4000-8000-000000000002")

# ~1800 chars ≈ 450 tokens — matches the seeder's chunk size so the corpus
# is dimensionally consistent.
MAX_CHARS = 1800

# OpenAI accepts up to 2048 inputs per /v1/embeddings call. Batch at 64 so
# each network round-trip is ~2-3 seconds, easy to monitor.
EMBED_BATCH = 64


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        if end < len(text):
            # try to break at a sentence boundary near `end`
            window = text.rfind(". ", cursor, end)
            if window > cursor + max_chars // 2:
                end = window + 1
        chunk = text[cursor:end].strip()
        if chunk:
            out.append(chunk)
        cursor = end
    return out


def make_chunk_id(judgment_id: str, chunk_index: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"judgment::{judgment_id}::{chunk_index}")


async def fetch_judgments(uploader_db: str, limit: int | None) -> list[dict]:
    conn = await asyncpg.connect(uploader_db)
    try:
        sql = """
            SELECT id, neutral_citation, case_name, court, judgment_date,
                   tna_url, clean_text, search_domain
            FROM judgments
            WHERE clean_text IS NOT NULL AND length(clean_text) > 100
            ORDER BY id
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = await conn.fetch(sql)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def already_chunked_judgment_ids(rag_db: str) -> set[str]:
    """Read judgment ids that already have any chunk in ograg_chunks.

    judgments.id is a UUID — too big for bigint, so we store as text in
    ``source.judgment_id`` and compare as text here.
    """
    conn = await asyncpg.connect(rag_db)
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT source->>'judgment_id' AS jid
            FROM ograg_chunks
            WHERE source->>'judgment_id' IS NOT NULL
            """
        )
        return {r["jid"] for r in rows if r["jid"]}
    finally:
        await conn.close()


async def insert_chunks_batch(
    conn: asyncpg.Connection,
    chunk_rows: list[tuple[uuid.UUID, str, dict, list[float]]],
) -> int:
    """ON CONFLICT (id) DO NOTHING so re-runs are no-ops."""
    import json as _json

    inserted = 0
    for cid, text, source, embedding in chunk_rows:
        result = await conn.execute(
            """
            INSERT INTO ograg_chunks (id, text, source, embedding)
            VALUES ($1, $2, $3::jsonb, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            cid,
            text,
            _json.dumps(source),
            embedding,
        )
        # asyncpg returns "INSERT 0 N" where N=1 if inserted, 0 if conflict skipped
        if result.endswith(" 1"):
            inserted += 1
    return inserted


async def backfill_one(
    rag_conn: asyncpg.Connection,
    judgment: dict,
) -> tuple[int, int]:
    """Chunk + embed + insert one judgment. Returns (n_chunks, n_inserted)."""
    text = judgment["clean_text"]
    chunks = chunk_text(text)
    if not chunks:
        return 0, 0

    embeddings = await embed_many(chunks)
    assert len(embeddings) == len(chunks), f"expected {len(chunks)} embeddings, got {len(embeddings)}"
    assert all(len(e) == EMBED_DIM for e in embeddings), f"all embeddings must be {EMBED_DIM}-d"

    base_source = {
        "kind": "case_law",
        "judgment_id": str(judgment["id"]),
        "id": judgment["neutral_citation"],
        "neutral_citation": judgment["neutral_citation"],
        "title": judgment["case_name"],
        "court": judgment["court"],
        "judgment_date": (judgment["judgment_date"].isoformat() if judgment["judgment_date"] else None),
        "url": judgment["tna_url"],
        "search_domain": judgment["search_domain"],
    }

    rows: list[tuple[uuid.UUID, str, dict, list[float]]] = []
    jid_str = str(judgment["id"])
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
        cid = make_chunk_id(jid_str, idx)
        source = dict(base_source, chunk_index=idx)
        rows.append((cid, chunk, source, emb))

    inserted = await insert_chunks_batch(rag_conn, rows)
    return len(chunks), inserted


async def main_async(args: argparse.Namespace) -> int:
    uploader_db = os.environ.get("UPLOADER_DB")
    rag_db = os.environ.get("RAG_API_DB")
    if not uploader_db or not rag_db:
        print("ERROR: set UPLOADER_DB and RAG_API_DB env vars (public Postgres URLs)", file=sys.stderr)
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    print(f"== backfill: TNA judgments → ograg_chunks (limit={args.limit}, resume={args.resume}) ==")

    print("[1/4] Fetching judgments…")
    judgments = await fetch_judgments(uploader_db, args.limit)
    print(f"  {len(judgments)} judgments with clean_text")

    already: set[str] = set()
    if args.resume:
        print("[2/4] Checking which judgments already have chunks…")
        already = await already_chunked_judgment_ids(rag_db)
        print(f"  {len(already)} already chunked; will skip")

    to_process = [j for j in judgments if str(j["id"]) not in already]
    if not to_process:
        print("Nothing to do. Exiting.")
        return 0
    print(f"[3/4] Processing {len(to_process)} judgments")

    rag_conn = await asyncpg.connect(rag_db)
    try:
        # register vector codec so list[float] encodes as vector(N)
        from pgvector.asyncpg import register_vector

        await register_vector(rag_conn)

        total_chunks = 0
        total_inserted = 0
        for i, j in enumerate(to_process, start=1):
            try:
                n_chunks, n_inserted = await backfill_one(rag_conn, j)
                total_chunks += n_chunks
                total_inserted += n_inserted
                jid_short = str(j["id"])[:8]
                cit = (j.get("neutral_citation") or "")[:25]
                print(
                    f"  [{i}/{len(to_process)}] {jid_short} {cit:<25s} chunks={n_chunks:3d} inserted={n_inserted:3d}",
                    flush=True,
                )
            except Exception as exc:
                print(f"  [{i}/{len(to_process)}] id={j['id']} FAILED: {exc}", file=sys.stderr)
                continue
    finally:
        await rag_conn.close()

    print("[4/4] Done.")
    print(f"  total chunks produced: {total_chunks}")
    print(f"  total rows inserted:   {total_inserted}")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N judgments")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip judgments that already have chunks in ograg_chunks",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
