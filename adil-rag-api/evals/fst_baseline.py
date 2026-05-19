"""Measure FST latency baseline.

Runs each query in queries_seed.jsonl through the live FST path N times,
records per-query latency, writes aggregated P50/P95/P99 to fst_baseline.json.

The output file is committed to the repo; it is the reference number against
which OG-RAG's cutover gate ('P95 <= 2x FST baseline') is evaluated.
"""

from __future__ import annotations


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
