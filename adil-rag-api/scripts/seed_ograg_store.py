"""Seed the ograg_chunks table with static legislation + case law.

Run-once script. Reads LEGISLATION_SNIPPETS and UK_CASE_LAW from
rag_service.py, chunks each entry into <512-token chunks, embeds with
Gemini, and INSERTs with stable IDs. Re-running is a no-op thanks to
``ON CONFLICT (id) DO NOTHING`` on stable UUIDv5 ids.

Usage:
    python scripts/seed_ograg_store.py
Env required:
    GEMINI_API_KEY
    DATABASE_URL  (or TEST_DATABASE_URL — DATABASE_URL is preferred)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

# Make project root importable when running as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_migrate import run_migrations  # noqa: E402
from ograg.embed import embed_one  # noqa: E402
from ograg.store import Store  # noqa: E402

from rag_service import LEGISLATION_SNIPPETS, UK_CASE_LAW  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_ograg")

# Deterministic UUIDv5 namespace so re-runs produce identical IDs.
NAMESPACE = uuid.UUID("d1c0b0a0-0000-4000-8000-000000000001")

# ~2000 chars ≈ 500 tokens. Keep chunks comfortably under 512.
MAX_CHARS = 1800


def _chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    # Greedy paragraph-aware split.
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        if end < len(text):
            # try to break at a sentence boundary near `end`
            window = text.rfind(". ", cursor, end)
            if window > cursor + max_chars // 2:
                end = window + 1
        out.append(text[cursor:end].strip())
        cursor = end
    return [c for c in out if c]


def _stable_id(source_type: str, key: str, chunk_index: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{source_type}::{key}::{chunk_index}")


def _resolve_db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or TEST_DATABASE_URL) must be set")
    return url


async def _seed_legislation(store: Store) -> int:
    inserted = 0
    for act_name, sections in LEGISLATION_SNIPPETS.items():
        for section, snippet in sections.items():
            chunks = _chunk_text(f"{act_name} — Section {section}: {snippet}")
            for idx, chunk_text in enumerate(chunks):
                key = f"{act_name}::s{section}"
                cid = _stable_id("statute", key, idx)
                source = {
                    "kind": "statute",
                    "id": f"{act_name}-s{section}",
                    "title": act_name,
                    "section": section,
                    "chunk_index": idx,
                }
                vec = await embed_one(chunk_text)
                await store.insert_chunk(text=chunk_text, source=source, embedding=vec, chunk_id=cid)
                inserted += 1
                logger.info("statute %s s.%s chunk %d", act_name, section, idx)
    return inserted


async def _seed_case_law(store: Store) -> int:
    inserted = 0
    for case_name, meta in UK_CASE_LAW.items():
        body = f"{case_name} — {meta.get('court', '')} {meta.get('citation', '')}\n\n{meta.get('summary', '')}"
        chunks = _chunk_text(body)
        for idx, chunk_text in enumerate(chunks):
            cid = _stable_id("case_law", case_name, idx)
            source = {
                "kind": "case_law",
                "id": case_name,
                "title": case_name,
                "neutral_citation": meta.get("citation"),
                "court": meta.get("court"),
                "url": meta.get("url"),
                "chunk_index": idx,
            }
            vec = await embed_one(chunk_text)
            await store.insert_chunk(text=chunk_text, source=source, embedding=vec, chunk_id=cid)
            inserted += 1
            logger.info("case_law %s chunk %d", case_name, idx)
    return inserted


async def main() -> None:
    db_url = _resolve_db_url()
    await run_migrations(db_url)

    store = Store()
    await store.connect(db_url)
    try:
        statute_n = await _seed_legislation(store)
        case_n = await _seed_case_law(store)
    finally:
        await store.close()

    total = statute_n + case_n
    print(f"indexed {total} chunks ({statute_n} statute, {case_n} case_law)")


if __name__ == "__main__":
    asyncio.run(main())
