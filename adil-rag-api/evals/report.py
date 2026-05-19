"""Render ``eval_review_<run_id>.md`` from a ``judged.jsonl``.

Computes aggregate scores, P50/P95 latency, cost-per-1k-queries, picks 10
random pairs for human spot-check, and emits a markdown file with empty
pass/fail boxes for the reviewer to tick.

Cutover gate (printed at top of the report and exited non-zero if any fails):

* OG-RAG aggregate (factual + citation + completeness) ≥ FST aggregate.
* No backend has harmfulness ≥ 4 on any query.
* OG-RAG P95 latency ≤ 2× FST P95 latency.

The 8/10 user pass-rate gate is filled in by the human after spot-check; this
script leaves a placeholder.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import statistics
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUBRIC_HIGHER_BETTER = ("factual_correctness", "citation_specificity", "completeness")
HARMFULNESS = "harmfulness"
SPOT_CHECK_N = 10
P95_HEADROOM = 2.0


def load_judged(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("error"):
            continue  # skip rows where the judge failed; counted separately
        rows.append(rec)
    return rows


def count_errors(path: Path) -> int:
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if json.loads(line).get("error"):
            n += 1
    return n


def aggregate(rows: list[dict[str, Any]], backend: str) -> dict[str, float]:
    """Return mean rubric scores + latency stats for one backend."""
    out: dict[str, float] = {}
    for field in (*RUBRIC_HIGHER_BETTER, HARMFULNESS):
        vals = [r[backend]["scores"][field] for r in rows]
        out[field] = round(statistics.mean(vals), 3) if vals else 0.0

    latencies = [r[backend]["latency_ms"] for r in rows if r[backend].get("latency_ms") is not None]
    out["latency_p50_ms"] = float(_percentile(latencies, 50)) if latencies else 0.0
    out["latency_p95_ms"] = float(_percentile(latencies, 95)) if latencies else 0.0
    out["latency_mean_ms"] = round(statistics.mean(latencies), 1) if latencies else 0.0

    costs = [r[backend].get("cost_usd") for r in rows]
    costs = [c for c in costs if c is not None]
    out["total_cost_usd"] = round(sum(costs), 4) if costs else 0.0

    out["aggregate_quality"] = round(sum(out[f] for f in RUBRIC_HIGHER_BETTER), 3)
    return out


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def gate_decisions(
    fst: dict[str, float], ograg: dict[str, float], rows: list[dict[str, Any]]
) -> list[tuple[str, bool, str]]:
    """Return a list of (gate_name, passed, detail) tuples."""
    quality_pass = ograg["aggregate_quality"] >= fst["aggregate_quality"]

    harm_pass = True
    harm_breaches: list[str] = []
    for r in rows:
        for backend in ("fst", "ograg"):
            h = r[backend]["scores"][HARMFULNESS]
            if h >= 4:
                harm_pass = False
                harm_breaches.append(f"{r['query_id']} ({backend}={h})")

    p95_pass = ograg["latency_p95_ms"] <= P95_HEADROOM * fst["latency_p95_ms"] if fst["latency_p95_ms"] else True

    return [
        (
            "OG-RAG aggregate quality ≥ FST aggregate quality",
            quality_pass,
            f"FST={fst['aggregate_quality']} OG-RAG={ograg['aggregate_quality']}",
        ),
        (
            "No harmfulness ≥ 4 on any query (either backend)",
            harm_pass,
            "all clear" if harm_pass else "breaches: " + ", ".join(harm_breaches[:5]),
        ),
        (
            f"OG-RAG P95 latency ≤ {P95_HEADROOM:.0f}× FST P95 latency",
            p95_pass,
            f"FST P95={fst['latency_p95_ms']:.0f}ms OG-RAG P95={ograg['latency_p95_ms']:.0f}ms",
        ),
        (
            "Human spot-check pass rate ≥ 8/10",
            False,  # always pending; human edits the .md
            "pending — fill in below",
        ),
    ]


def pick_spot_check(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return rng.sample(rows, min(n, len(rows)))


def render_report(
    run_id: str,
    rows: list[dict[str, Any]],
    fst: dict[str, float],
    ograg: dict[str, float],
    gates: list[tuple[str, bool, str]],
    spot_check: list[dict[str, Any]],
    judge_errors: int,
) -> str:
    lines: list[str] = []
    a = lines.append

    a(f"# OG-RAG eval — `{run_id}`")
    a("")
    a(
        f"Pairs judged: **{len(rows)}**  ·  judge errors: **{judge_errors}**  ·  "
        f"spot-check sample: **{len(spot_check)}**"
    )
    a("")

    a("## Cutover gate")
    a("")
    a("| Gate | Pass | Detail |")
    a("| --- | --- | --- |")
    for name, passed, detail in gates:
        mark = "✅" if passed else ("⏳" if "pending" in detail else "❌")
        a(f"| {name} | {mark} | {detail} |")
    a("")

    a("## Aggregate scores")
    a("")
    a("| Metric | FST | OG-RAG |")
    a("| --- | ---: | ---: |")
    a(f"| factual_correctness (1-5, higher better) | {fst['factual_correctness']} | {ograg['factual_correctness']} |")
    a(
        f"| citation_specificity (1-5, higher better) | {fst['citation_specificity']} | {ograg['citation_specificity']} |"
    )
    a(f"| completeness (1-5, higher better) | {fst['completeness']} | {ograg['completeness']} |")
    a(f"| harmfulness (1-5, **lower** better) | {fst['harmfulness']} | {ograg['harmfulness']} |")
    a(
        f"| **aggregate quality** (sum of 3 higher-better) | **{fst['aggregate_quality']}** | **{ograg['aggregate_quality']}** |"
    )
    a("")

    a("## Latency + cost")
    a("")
    a("| Metric | FST | OG-RAG |")
    a("| --- | ---: | ---: |")
    a(f"| latency P50 (ms) | {fst['latency_p50_ms']:.0f} | {ograg['latency_p50_ms']:.0f} |")
    a(f"| latency P95 (ms) | {fst['latency_p95_ms']:.0f} | {ograg['latency_p95_ms']:.0f} |")
    a(f"| latency mean (ms) | {fst['latency_mean_ms']:.0f} | {ograg['latency_mean_ms']:.0f} |")
    a(f"| total cost (USD) | {fst['total_cost_usd']:.4f} | {ograg['total_cost_usd']:.4f} |")
    a("")

    a("## Human spot-check (fill in pass/fail per backend)")
    a("")
    a(
        "Mark each backend pass (✓) or fail (✗) per query. The bottom-line "
        f"user pass rate is computed over the {len(spot_check)} queries below."
    )
    a("")
    for i, r in enumerate(spot_check, start=1):
        a(f"### {i}. `{r['query_id']}` — pass: FST [ ]  OG-RAG [ ]")
        a("")
        a(f"**Question:** {r['query_text']}")
        a("")
        a("<details><summary>FST answer</summary>")
        a("")
        a("```")
        a((r["fst"]["answer"] or "(no answer)").strip())
        a("```")
        a("")
        a("Scores: " + ", ".join(f"{k}={v}" for k, v in r["fst"]["scores"].items()))
        a("</details>")
        a("")
        a("<details><summary>OG-RAG answer</summary>")
        a("")
        a("```")
        a((r["ograg"]["answer"] or "(no answer)").strip())
        a("```")
        a("")
        a("Scores: " + ", ".join(f"{k}={v}" for k, v in r["ograg"]["scores"].items()))
        a("</details>")
        a("")
        if r.get("judge_notes"):
            a(f"_Judge notes:_ {r['judge_notes']}")
            a("")

    a("---")
    a("")
    a("## Spot-check tally")
    a("")
    a("After filling boxes above, count and record:")
    a("")
    a("- FST pass rate: __ / 10")
    a("- OG-RAG pass rate: __ / 10")
    a("- Decision (proceed / stop): __")
    a("")
    return "\n".join(lines) + "\n"


def main_async(args: argparse.Namespace) -> int:
    run_dir = Path("evals/runs") / args.run_id
    judged = run_dir / "judged.jsonl"
    if not judged.exists():
        print(f"ERROR: {judged} not found. Run judge.py first.", file=sys.stderr)
        return 1

    rows = load_judged(judged)
    if not rows:
        print(f"ERROR: no valid judged rows in {judged}", file=sys.stderr)
        return 1

    judge_errors = count_errors(judged)
    fst = aggregate(rows, "fst")
    ograg = aggregate(rows, "ograg")
    gates = gate_decisions(fst, ograg, rows)
    spot = pick_spot_check(rows, SPOT_CHECK_N, args.seed)

    md = render_report(args.run_id, rows, fst, ograg, gates, spot, judge_errors)
    out = run_dir / f"eval_review_{args.run_id}.md"
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out}")

    # Non-zero exit if any of the auto-decidable gates failed (last gate is human, ignore).
    auto_fail = any(not passed for name, passed, _ in gates[:3])
    if auto_fail:
        print("One or more auto-decidable cutover gates FAILED. See report.", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", type=int, default=42, help="Seed for spot-check sample selection")
    args = parser.parse_args()
    raise SystemExit(main_async(args))


if __name__ == "__main__":
    main()
