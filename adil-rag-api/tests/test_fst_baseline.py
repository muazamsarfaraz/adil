"""Tests for FST baseline measurement helpers."""

from __future__ import annotations

import pytest
import respx
from evals.fst_baseline import BaselineRunner, percentile
from httpx import Response


class TestPercentile:
    def test_p50_of_sorted_list(self):
        assert percentile([10, 20, 30, 40, 50], 50) == 30

    def test_p95_of_100_items(self):
        # 1..100; the 95th percentile by nearest-rank should be 95
        assert percentile(list(range(1, 101)), 95) == 95

    def test_p99_of_100_items(self):
        assert percentile(list(range(1, 101)), 99) == 99

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="empty"):
            percentile([], 50)

    def test_unsorted_input_sorted_internally(self):
        # P50 must be invariant to input order
        assert percentile([50, 10, 30, 40, 20], 50) == 30


class TestBaselineRunner:
    @pytest.mark.asyncio
    @respx.mock
    async def test_measure_one_records_latency(self):
        route = respx.post("https://api.example.test/api/v1/query").mock(
            return_value=Response(200, json={"answer": "yes", "sources": []})
        )
        runner = BaselineRunner(api_url="https://api.example.test", api_key="k")
        result = await runner.measure_one(query_id="q1", query="test")
        assert route.called
        assert result["query_id"] == "q1"
        assert result["latency_ms"] >= 0
        assert result["status"] == "ok"
        assert result["http_status"] == 200

    @pytest.mark.asyncio
    @respx.mock
    async def test_measure_one_records_failure(self):
        respx.post("https://api.example.test/api/v1/query").mock(return_value=Response(500, json={"detail": "boom"}))
        runner = BaselineRunner(api_url="https://api.example.test", api_key="k")
        result = await runner.measure_one(query_id="q1", query="test")
        assert result["status"] == "fail"
        assert result["http_status"] == 500
