"""Tests for FST baseline measurement helpers."""

from __future__ import annotations

import pytest
from evals.fst_baseline import percentile


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
