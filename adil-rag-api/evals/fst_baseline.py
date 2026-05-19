"""Measure FST latency baseline.

Runs each query in queries_seed.jsonl through the live FST path N times,
records per-query latency, writes aggregated P50/P95/P99 to fst_baseline.json.

The output file is committed to the repo; it is the reference number against
which OG-RAG's cutover gate ('P95 <= 2x FST baseline') is evaluated.
"""

from __future__ import annotations

import time
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
