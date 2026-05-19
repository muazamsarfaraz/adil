"""Unit tests for the P8 eval harness.

Covers the pure-Python pieces: PII anonymisation, judge response parser,
aggregator, gate decisions, and end-to-end report rendering.

The DB / Gemini integration in run.py + judge.py is exercised at the module
boundary; the actual network calls require live keys + a Postgres and are
intentionally out of scope for unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evals import anonymise as anon
from evals import judge, report
from evals import run as evals_run

# ----------------------------------------------------------------------------
# anonymise.py
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_marker",
    [
        ("Reach me at jane.doe@example.org for follow-up.", "[EMAIL]"),
        ("Call me on 07712 345 678 tomorrow.", "[PHONE]"),
        ("Phone +44 20 7946 0958 please.", "[PHONE]"),
        ("My flat is at SW1A 1AA, what should I do?", "[POSTCODE]"),
        ("I live at 12 High Street and was attacked there.", "[ADDRESS]"),
    ],
)
def test_anonymise_replaces_obvious_pii(raw, expected_marker):
    out = anon.anonymise(raw)
    assert expected_marker in out
    # the original PII fragment must be gone
    assert "jane.doe" not in out
    assert "07712" not in out
    assert "+44 20 7946" not in out
    assert "SW1A 1AA" not in out
    assert "12 High Street" not in out


def test_anonymise_name_trigger():
    raw = "My name is Aisha Khan and my manager is rude to me."
    out = anon.anonymise(raw)
    assert "[NAME]" in out
    assert "Aisha" not in out
    assert "Khan" not in out


def test_anonymise_preserves_clean_text():
    raw = "What does section 26 of the Equality Act 2010 say about harassment?"
    assert anon.anonymise(raw) == raw


def test_looks_like_pii():
    assert anon.looks_like_pii("contact me at x@y.co.uk") is True
    assert anon.looks_like_pii("postcode SW1A 1AA") is True
    assert anon.looks_like_pii("Equality Act 2010 s.13") is False


# ----------------------------------------------------------------------------
# judge.py — parser
# ----------------------------------------------------------------------------


def _good_judge_payload(swap_better: bool = False) -> str:
    a_score = 5 if not swap_better else 3
    b_score = 3 if not swap_better else 5
    return json.dumps(
        {
            "answer_a": {
                "factual_correctness": a_score,
                "citation_specificity": a_score,
                "completeness": a_score,
                "harmfulness": 1,
            },
            "answer_b": {
                "factual_correctness": b_score,
                "citation_specificity": b_score,
                "completeness": b_score,
                "harmfulness": 1,
            },
            "notes": "A cites s.13; B is vaguer.",
        }
    )


def test_judge_parser_happy_path():
    obj = judge.parse_judge_response(_good_judge_payload())
    assert obj["answer_a"]["factual_correctness"] == 5
    assert obj["answer_b"]["completeness"] == 3
    assert "A cites" in obj["notes"]


def test_judge_parser_tolerates_markdown_fence():
    raw = "```json\n" + _good_judge_payload() + "\n```"
    obj = judge.parse_judge_response(raw)
    assert obj["answer_a"]["harmfulness"] == 1


@pytest.mark.parametrize(
    "broken",
    [
        "",
        "not json",
        json.dumps({"answer_a": {"factual_correctness": 5}}),  # missing fields
        json.dumps(
            {
                "answer_a": {
                    "factual_correctness": 9,  # out of range
                    "citation_specificity": 5,
                    "completeness": 5,
                    "harmfulness": 1,
                },
                "answer_b": {
                    "factual_correctness": 3,
                    "citation_specificity": 3,
                    "completeness": 3,
                    "harmfulness": 1,
                },
            }
        ),
    ],
)
def test_judge_parser_rejects_broken(broken):
    with pytest.raises(ValueError):
        judge.parse_judge_response(broken)


# ----------------------------------------------------------------------------
# report.py — aggregator + gates + render
# ----------------------------------------------------------------------------


def _row(qid: str, fst_scores: dict, ograg_scores: dict, *, fst_lat=400, ograg_lat=500) -> dict:
    return {
        "query_id": qid,
        "query_text": f"question {qid}?",
        "fst": {
            "answer": f"FST answer {qid}",
            "sources": [],
            "latency_ms": fst_lat,
            "cost_usd": 0.001,
            "scores": fst_scores,
        },
        "ograg": {
            "answer": f"OG-RAG answer {qid}",
            "sources": [],
            "latency_ms": ograg_lat,
            "cost_usd": 0.0012,
            "scores": ograg_scores,
        },
        "judge_notes": "",
    }


def _safe_scores(*, harm: int = 1, q: int = 4) -> dict:
    return {
        "factual_correctness": q,
        "citation_specificity": q,
        "completeness": q,
        "harmfulness": harm,
    }


def test_aggregate_basic_means_and_percentiles():
    rows = [
        _row("q01", _safe_scores(q=4), _safe_scores(q=5), fst_lat=100, ograg_lat=200),
        _row("q02", _safe_scores(q=4), _safe_scores(q=5), fst_lat=300, ograg_lat=400),
        _row("q03", _safe_scores(q=4), _safe_scores(q=5), fst_lat=500, ograg_lat=600),
    ]
    fst = report.aggregate(rows, "fst")
    ograg = report.aggregate(rows, "ograg")
    assert fst["factual_correctness"] == 4.0
    assert ograg["factual_correctness"] == 5.0
    assert fst["aggregate_quality"] == 12.0  # 4+4+4
    assert ograg["aggregate_quality"] == 15.0
    # P50 over [100,300,500] = 300
    assert fst["latency_p50_ms"] == 300.0
    # P95 over [200,400,600] = 580 (linear interp)
    assert pytest.approx(ograg["latency_p95_ms"], rel=0.01) == 580.0


def test_gate_decisions_all_pass():
    rows = [_row("q01", _safe_scores(q=4), _safe_scores(q=5))]
    fst = report.aggregate(rows, "fst")
    ograg = report.aggregate(rows, "ograg")
    gates = report.gate_decisions(fst, ograg, rows)
    quality, harm, p95, human = gates
    assert quality[1] is True
    assert harm[1] is True
    assert p95[1] is True
    assert human[1] is False  # pending


def test_gate_decisions_quality_fail():
    rows = [_row("q01", _safe_scores(q=5), _safe_scores(q=2))]
    fst = report.aggregate(rows, "fst")
    ograg = report.aggregate(rows, "ograg")
    gates = report.gate_decisions(fst, ograg, rows)
    quality, *_ = gates
    assert quality[1] is False


def test_gate_decisions_harmfulness_fail():
    rows = [_row("q01", _safe_scores(q=4), _safe_scores(q=4, harm=5))]
    fst = report.aggregate(rows, "fst")
    ograg = report.aggregate(rows, "ograg")
    gates = report.gate_decisions(fst, ograg, rows)
    _, harm, *_ = gates
    assert harm[1] is False
    assert "q01" in harm[2]


def test_gate_decisions_latency_fail():
    rows = [_row("q01", _safe_scores(q=4), _safe_scores(q=4), fst_lat=100, ograg_lat=10_000)]
    fst = report.aggregate(rows, "fst")
    ograg = report.aggregate(rows, "ograg")
    gates = report.gate_decisions(fst, ograg, rows)
    _, _, p95, _ = gates
    assert p95[1] is False


def test_pick_spot_check_is_deterministic():
    rows = [_row(f"q{i:02d}", _safe_scores(), _safe_scores()) for i in range(30)]
    a = report.pick_spot_check(rows, 10, seed=42)
    b = report.pick_spot_check(rows, 10, seed=42)
    assert [r["query_id"] for r in a] == [r["query_id"] for r in b]
    assert len(a) == 10


def test_render_report_contains_expected_sections(tmp_path: Path):
    rows = [_row(f"q{i:02d}", _safe_scores(q=4), _safe_scores(q=5)) for i in range(12)]
    fst = report.aggregate(rows, "fst")
    ograg = report.aggregate(rows, "ograg")
    gates = report.gate_decisions(fst, ograg, rows)
    spot = report.pick_spot_check(rows, 10, seed=42)

    md = report.render_report("test-run", rows, fst, ograg, gates, spot, judge_errors=0)
    assert "# OG-RAG eval — `test-run`" in md
    assert "## Cutover gate" in md
    assert "## Aggregate scores" in md
    assert "## Latency + cost" in md
    assert "## Human spot-check" in md
    # 10 spot-check entries with pass-fail boxes
    assert md.count("pass: FST [ ]  OG-RAG [ ]") == 10
    # Quality gate passes when OG-RAG > FST → green tick
    assert "✅" in md


# ----------------------------------------------------------------------------
# run.py — load_queries + backend env context manager
# ----------------------------------------------------------------------------


def test_load_queries_round_trips(tmp_path: Path):
    p = tmp_path / "q.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"id": "a", "query": "first?"}),
                json.dumps({"query": "second?"}),  # id auto-assigned
                "",  # blank line tolerated
            ]
        )
    )
    out = evals_run.load_queries(p)
    assert len(out) == 2
    assert out[0]["id"] == "a"
    assert out[1]["id"] == "q02"


def test_load_queries_rejects_missing_field(tmp_path: Path):
    p = tmp_path / "q.jsonl"
    p.write_text(json.dumps({"id": "a", "text": "no query field"}))
    with pytest.raises(ValueError):
        evals_run.load_queries(p)


def test_backend_env_restores_after_use(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND", "preset")
    with evals_run._backend_env("ograg"):
        import os

        assert os.environ["RAG_BACKEND"] == "ograg"
    import os

    assert os.environ["RAG_BACKEND"] == "preset"


def test_backend_env_clears_when_unset(monkeypatch):
    monkeypatch.delenv("RAG_BACKEND", raising=False)
    with evals_run._backend_env("fst"):
        import os

        assert os.environ["RAG_BACKEND"] == "fst"
    import os

    assert "RAG_BACKEND" not in os.environ


# ----------------------------------------------------------------------------
# Eval set sanity
# ----------------------------------------------------------------------------


def test_queries_jsonl_30_entries_no_pii():
    """The committed eval set has exactly 30 entries and none trip the PII regexes."""
    p = Path(__file__).resolve().parent.parent / "evals" / "queries.jsonl"
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 30
    seen_ids: set[str] = set()
    for ln in lines:
        obj = json.loads(ln)
        assert "id" in obj
        assert "query" in obj
        assert obj["id"] not in seen_ids, f"duplicate id {obj['id']}"
        seen_ids.add(obj["id"])
        assert not anon.looks_like_pii(obj["query"]), f"PII leaked in {obj['id']}: {obj['query']!r}"
