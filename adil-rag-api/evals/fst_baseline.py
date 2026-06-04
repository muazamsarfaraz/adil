"""Measure FST latency baseline.

Runs each query in queries_seed.jsonl through the live FST path N times,
records per-query latency, writes aggregated P50/P95/P99 to fst_baseline.json.

The output file is committed to the repo; it is the reference number against
which OG-RAG's cutover gate ('P95 <= 2x FST baseline') is evaluated.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


def percentile(samples: list[float | int], p: int) -> float:
    """Nearest-rank percentile. Pure function — pure for testing."""
    if not samples:
        raise ValueError("percentile of empty sample set is undefined")
    if not 0 <= p <= 100:
        raise ValueError(f"p must be in [0, 100], got {p}")
    s = sorted(samples)
    # Nearest-rank: ceil(p/100 * N), 1-indexed.
    idx = max(1, -(-p * len(s) // 100)) - 1
    return s[idx]


class BaselineRunner:
    """Run baseline measurement against the live rag-api FST path."""

    def __init__(self, api_url: str, api_key: str, timeout_s: float = 60.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def measure_one(self, query_id: str, query: str) -> dict[str, Any]:
        """Send one query, record latency and status. Does not retry."""
        payload = {"query": query, "max_sources": 5, "include_viability_score": False}
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        url = f"{self.api_url}/api/v1/query"

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    return {
                        "query_id": query_id,
                        "latency_ms": elapsed_ms,
                        "status": "ok",
                        "http_status": 200,
                    }
                return {
                    "query_id": query_id,
                    "latency_ms": elapsed_ms,
                    "status": "fail",
                    "http_status": resp.status_code,
                }
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                return {
                    "query_id": query_id,
                    "latency_ms": elapsed_ms,
                    "status": "error",
                    "error": str(exc)[:200],
                }


async def run_baseline(
    api_url: str,
    api_key: str,
    queries: list[dict[str, str]],
    repetitions: int = 10,
    throttle_s: float = 2.1,
) -> dict[str, Any]:
    """Run each query `repetitions` times; aggregate latency stats.

    `throttle_s` enforces ~28 calls/min — comfortably under the 30/min rate limit.
    """
    runner = BaselineRunner(api_url=api_url, api_key=api_key)
    all_results: list[dict[str, Any]] = []
    for rep in range(repetitions):
        for q in queries:
            r = await runner.measure_one(q["id"], q["query"])
            all_results.append(r)
            if throttle_s > 0:
                await asyncio.sleep(throttle_s)
        print(f"  rep {rep + 1}/{repetitions}: {len(all_results)} samples so far")

    ok = [r for r in all_results if r["status"] == "ok"]
    latencies = [r["latency_ms"] for r in ok]
    return {
        "total_runs": len(all_results),
        "ok_runs": len(ok),
        "fail_runs": len(all_results) - len(ok),
        "p50_ms": percentile(latencies, 50) if latencies else None,
        "p95_ms": percentile(latencies, 95) if latencies else None,
        "p99_ms": percentile(latencies, 99) if latencies else None,
        "min_ms": min(latencies) if latencies else None,
        "max_ms": max(latencies) if latencies else None,
        "queries_used": [q["id"] for q in queries],
        "repetitions": repetitions,
        "api_url": api_url,
    }


def _load_seed_queries() -> list[dict[str, str]]:
    path = Path(__file__).parent / "queries_seed.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _resolve_api_key() -> str:
    """Prefer BASELINE_API_KEY; otherwise take first entry from ADIL_API_KEY CSV."""
    direct = os.environ.get("BASELINE_API_KEY")
    if direct:
        return direct
    csv = os.environ.get("ADIL_API_KEY", "")
    first = csv.split(",")[0].strip()
    if not first:
        raise RuntimeError(
            "No API key found. Set BASELINE_API_KEY or run via "
            "`railway run --service adil-rag-api python -m evals.fst_baseline`"
        )
    return first


async def _cli_main() -> None:
    api_url = os.environ.get("BASELINE_API_URL", "https://adil-rag-api-production.up.railway.app")
    api_key = _resolve_api_key()
    repetitions = int(os.environ.get("BASELINE_REPS", "10"))
    queries = _load_seed_queries()

    print(f"Running baseline: {api_url} | {len(queries)} queries × {repetitions} reps")
    summary = await run_baseline(api_url, api_key, queries, repetitions)

    out_path = Path(__file__).parent / "fst_baseline.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    p50 = summary["p50_ms"]
    p95 = summary["p95_ms"]
    print(
        f"Wrote {out_path}: ok={summary['ok_runs']}/{summary['total_runs']} P50={p50:.0f}ms P95={p95:.0f}ms"
        if p50
        else "no ok results"
    )


if __name__ == "__main__":
    asyncio.run(_cli_main())
