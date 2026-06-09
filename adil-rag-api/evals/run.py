"""P8 eval runner — runs every query in ``queries.jsonl`` through BOTH backends.

For each query we get one FST answer and one OG-RAG answer, then write both
rows to ``eval_run`` tagged with ``meta = {run_id, eval_set_version, query_id}``.

The harness flips ``RAG_BACKEND`` per call rather than instantiating two
services — ``rag_service.RAGService.query`` reads the env var on every call, so
this is the correct and only routing seam.

Usage::

    DATABASE_URL=... GEMINI_API_KEY=... FILE_SEARCH_STORE_ID=... \\
        python -m evals.run --queries evals/queries.jsonl

Outputs:

* Rows in ``eval_run`` (DB) — used by ``judge.py``.
* A local ``evals/runs/<run_id>/raw.jsonl`` mirror — handy when DB is offline.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EVAL_SET_VERSION = "v1"
BACKENDS: tuple[str, ...] = ("fst", "ograg")


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def load_queries(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "query" not in obj:
            raise ValueError(f"{path}:{i} missing 'query' field")
        obj.setdefault("id", f"q{i:02d}")
        out.append(obj)
    return out


@contextlib.contextmanager
def _backend_env(name: str):
    """Temporarily set RAG_BACKEND for the duration of one query call."""
    prev = os.environ.get("RAG_BACKEND")
    os.environ["RAG_BACKEND"] = name
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("RAG_BACKEND", None)
        else:
            os.environ["RAG_BACKEND"] = prev


def _sources_to_json(sources: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sources or []:
        if hasattr(s, "model_dump"):
            out.append(s.model_dump(mode="json"))
        elif isinstance(s, dict):
            out.append(s)
        else:
            out.append({"raw": str(s)})
    return out


async def run_one(
    service: Any,
    backend: str,
    query_text: str,
) -> dict[str, Any]:
    """Run a single (backend, query) pair. Returns a row ready for eval_run."""
    start = time.time()
    err: str | None = None
    answer = ""
    sources_json: list[dict[str, Any]] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None

    try:
        with _backend_env(backend):
            ans, sources, usage, _meta, _viability, _checklist = await service.query(query_text)
        answer = ans
        sources_json = _sources_to_json(sources)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        cost = getattr(usage, "estimated_cost_usd", None)
    except Exception as e:  # noqa: BLE001 — we want every failure recorded
        err = f"{type(e).__name__}: {e}"
        logger.warning("backend=%s query failed: %s", backend, err)

    latency_ms = int((time.time() - start) * 1000)
    return {
        "backend": backend,
        "query_text": query_text,
        "answer": answer or None,
        "sources": sources_json,
        "latency_ms": latency_ms,
        "cost_usd": cost,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "error": err,
    }


async def insert_eval_row(
    pool: Any,
    row: dict[str, Any],
    *,
    run_id: str,
    query_id: str,
) -> None:
    """Write one row to the eval_run table. Best-effort — logs on failure."""
    meta = {
        "run_id": run_id,
        "eval_set_version": EVAL_SET_VERSION,
        "query_id": query_id,
    }
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO eval_run
                  (backend, query_text, answer, sources, latency_ms, cost_usd,
                   prompt_tokens, completion_tokens, error, meta)
                VALUES
                  ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10::jsonb)
                """,
                row["backend"],
                row["query_text"],
                row["answer"],
                json.dumps(row["sources"]),
                row["latency_ms"],
                row["cost_usd"],
                row["prompt_tokens"],
                row["completion_tokens"],
                row["error"],
                json.dumps(meta),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("eval_run insert failed: %s", e)


async def main_async(args: argparse.Namespace) -> int:
    queries_path = Path(args.queries)
    queries = load_queries(queries_path)
    if not queries:
        print(f"No queries found in {queries_path}", file=sys.stderr)
        return 1

    run_id = args.run_id or _utc_now_iso()
    out_dir = Path("evals/runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw.jsonl"

    # Lazy imports — keep CLI startup snappy and avoid Gemini key check at parse time.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rag_service import RAGService  # noqa: E402

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    file_search_store_id = os.environ.get("FILE_SEARCH_STORE_ID")
    if not gemini_api_key or not file_search_store_id:
        print("ERROR: GEMINI_API_KEY and FILE_SEARCH_STORE_ID must be set", file=sys.stderr)
        return 2

    service = RAGService(gemini_api_key, file_search_store_id)

    pool = None
    database_url = os.environ.get("DATABASE_URL")
    if database_url and not args.no_db:
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
    else:
        logger.warning("DATABASE_URL not set — writing local mirror only.")

    n_total = len(queries) * len(BACKENDS)
    n_done = 0
    print(f"Run {run_id}: {len(queries)} queries × {len(BACKENDS)} backends = {n_total} calls")

    try:
        with raw_path.open("w", encoding="utf-8") as fh:
            for q in queries:
                qid = q["id"]
                qtext = q["query"]
                for backend in BACKENDS:
                    row = await run_one(service, backend, qtext)
                    row["query_id"] = qid
                    row["run_id"] = run_id
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
                    if pool is not None:
                        await insert_eval_row(pool, row, run_id=run_id, query_id=qid)
                    n_done += 1
                    status = "ok" if row["error"] is None else f"err: {row['error']}"
                    print(f"  [{n_done}/{n_total}] {qid} {backend} {row['latency_ms']}ms {status}")
    finally:
        if pool is not None:
            await pool.close()

    print(f"Done. Raw mirror: {raw_path}")
    print(f"Next: python -m evals.judge --run-id {run_id}")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", default="evals/queries.jsonl")
    parser.add_argument("--run-id", default=None, help="Stable run identifier (default: UTC timestamp)")
    parser.add_argument("--no-db", action="store_true", help="Skip eval_run inserts; only write the local mirror")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
