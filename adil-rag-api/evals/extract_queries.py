"""Pull candidate eval queries from the ``eval_run`` shadow table.

Source of truth for "real user queries" is the ``eval_run`` table populated by
P9 shadow mode (``backend='ograg_shadow'``). The anonymised
``conversation_logs`` table referenced in the spec only stores topic categories,
not raw query text, so shadow rows are the actual feed.

Workflow:

1. Wait for shadow mode to run for a few days in prod.
2. Run ``python -m evals.extract_queries --days 7 --out evals/candidates.jsonl``.
3. Manually review every line in candidates.jsonl, redact anything the
   anonymiser missed, then move 30 lines into ``evals/queries.jsonl``.

This script never overwrites ``queries.jsonl`` directly — the human review
gate is mandatory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from evals.anonymise import anonymise, looks_like_pii

logger = logging.getLogger(__name__)


async def fetch_candidates(database_url: str, days: int, limit: int) -> list[dict]:
    """Return distinct shadow queries from the last ``days`` days."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (query_text)
              id, created_at, query_text, latency_ms
            FROM eval_run
            WHERE backend = 'ograg_shadow'
              AND created_at > NOW() - ($1::int * INTERVAL '1 day')
              AND query_text IS NOT NULL
              AND char_length(query_text) BETWEEN 20 AND 600
            ORDER BY query_text, created_at DESC
            LIMIT $2
            """,
            days,
            limit,
        )
    finally:
        await conn.close()

    return [
        {
            "id": f"shadow-{row['id']}",
            "query": row["query_text"],
            "created_at": row["created_at"].isoformat(),
            "latency_ms": row["latency_ms"],
        }
        for row in rows
    ]


def write_candidates(rows: list[dict], out_path: Path) -> int:
    """Write anonymised candidates as JSONL. Returns the count flagged for review."""
    flagged = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            raw = r["query"]
            redacted = anonymise(raw)
            needs_review = looks_like_pii(redacted)  # post-redact: should be false
            if needs_review:
                flagged += 1
            fh.write(
                json.dumps(
                    {
                        "id": r["id"],
                        "query": redacted,
                        "needs_review": needs_review,
                        "created_at": r.get("created_at"),
                    }
                )
                + "\n"
            )
    return flagged


async def main_async(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        return 2

    candidates = await fetch_candidates(database_url, args.days, args.limit)
    if not candidates:
        print("No shadow rows found in the lookback window.", file=sys.stderr)
        return 1

    flagged = write_candidates(candidates, Path(args.out))
    print(
        f"Wrote {len(candidates)} candidates to {args.out} "
        f"({flagged} still match a PII regex after redaction — review carefully)."
    )
    print("Next: manually skim every line, then copy 30 reviewed lines into evals/queries.jsonl.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out", default="evals/candidates.jsonl")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
