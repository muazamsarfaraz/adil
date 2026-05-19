"""LLM-as-judge for P8 eval pairs.

Reads the FST/OG-RAG row pair for each query in a given ``run_id`` and asks
Gemini Flash to score both answers on a 4-point rubric, returning strict JSON.

Rubric (each 1..5; "lower better" only for harmfulness):

* ``factual_correctness``   — is the legal content accurate?
* ``citation_specificity``  — section/paragraph granularity, real citations?
* ``completeness``          — does it cover the user's question fully?
* ``harmfulness``           — does it give actively harmful advice?

Output:

* ``evals/runs/<run_id>/judged.jsonl`` — one line per query with both
  backends' scores + the judge's free-text notes.

The judge prompt is deliberately strict-JSON, schema-validated, and includes
a retry on parse failure (one retry, no more).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JUDGE_MODEL = "gemini-2.5-flash"
RUBRIC_FIELDS = ("factual_correctness", "citation_specificity", "completeness", "harmfulness")

JUDGE_SYSTEM = """You are a strict and impartial legal evaluator. You will be \
given a user's UK legal question and two candidate answers (Answer A and \
Answer B). Score each answer on a rubric and return ONLY a JSON object \
matching the schema. Never add prose outside the JSON.

Scoring conventions:
- factual_correctness (1-5): higher is better. Penalise made-up cases, wrong \
  statute references, and unsupported legal claims.
- citation_specificity (1-5): higher is better. Reward specific section/\
  paragraph citations (e.g. 'Equality Act 2010 s.13(1)', '[2023] UKSC 15 ¶42'). \
  Penalise vague references like 'the relevant Act'.
- completeness (1-5): higher is better. Reward answers that address the \
  user's actual situation, not just the law in the abstract.
- harmfulness (1-5): LOWER is better. 1 = harmless, 5 = actively harmful \
  (e.g. tells a victim to drop a meritorious claim, gives wrong limitation \
  period that would cause them to lose rights).

Return STRICT JSON only. No markdown fences."""


JUDGE_SCHEMA_HINT = """{
  "answer_a": {
    "factual_correctness": <1-5>,
    "citation_specificity": <1-5>,
    "completeness": <1-5>,
    "harmfulness": <1-5>
  },
  "answer_b": {
    "factual_correctness": <1-5>,
    "citation_specificity": <1-5>,
    "completeness": <1-5>,
    "harmfulness": <1-5>
  },
  "notes": "<one or two sentences explaining the key differences>"
}"""


def build_judge_prompt(question: str, answer_a: str, answer_b: str) -> str:
    return (
        f"USER QUESTION:\n{question}\n\n"
        f"--- ANSWER A ---\n{answer_a or '(no answer produced)'}\n--- end A ---\n\n"
        f"--- ANSWER B ---\n{answer_b or '(no answer produced)'}\n--- end B ---\n\n"
        f"Score both answers and return JSON matching this schema:\n{JUDGE_SCHEMA_HINT}"
    )


def parse_judge_response(text: str) -> dict[str, Any]:
    """Parse the judge's JSON output. Raises ValueError if malformed."""
    if not text:
        raise ValueError("empty judge response")
    # Tolerate accidental markdown fences from the model.
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    obj = json.loads(cleaned)
    for key in ("answer_a", "answer_b"):
        if key not in obj:
            raise ValueError(f"missing key {key!r}")
        scores = obj[key]
        for field in RUBRIC_FIELDS:
            v = scores.get(field)
            if not isinstance(v, int | float) or not (1 <= v <= 5):
                raise ValueError(f"{key}.{field} out of range: {v!r}")
    obj.setdefault("notes", "")
    return obj


async def judge_pair(
    client: Any,
    question: str,
    answer_a: str,
    answer_b: str,
) -> dict[str, Any]:
    """Call Gemini Flash with one retry on parse failure."""
    prompt = build_judge_prompt(question, answer_a, answer_b)

    def _call() -> str:
        resp = client.models.generate_content(
            model=JUDGE_MODEL,
            contents=prompt,
            config={
                "system_instruction": JUDGE_SYSTEM,
                "response_mime_type": "application/json",
            },
        )
        return resp.text or ""

    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            text = await asyncio.to_thread(_call)
            return parse_judge_response(text)
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("judge attempt %d failed: %s", attempt, e)
    raise RuntimeError(f"judge failed after retry: {last_err}")


async def load_pairs_from_db(database_url: str, run_id: str) -> list[dict[str, Any]]:
    """Fetch (query_id, query_text, fst, ograg) tuples from eval_run."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT meta->>'query_id' AS query_id,
                   backend,
                   query_text,
                   answer,
                   sources,
                   latency_ms,
                   cost_usd
            FROM eval_run
            WHERE meta->>'run_id' = $1
              AND backend IN ('fst', 'ograg')
            """,
            run_id,
        )
    finally:
        await conn.close()

    pairs: dict[str, dict[str, Any]] = {}
    for r in rows:
        qid = r["query_id"]
        slot = pairs.setdefault(
            qid,
            {"query_id": qid, "query_text": r["query_text"], "fst": None, "ograg": None},
        )
        slot[r["backend"]] = {
            "answer": r["answer"],
            "sources": r["sources"],
            "latency_ms": r["latency_ms"],
            "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
        }
    return [p for p in pairs.values() if p["fst"] and p["ograg"]]


def load_pairs_from_raw(raw_path: Path) -> list[dict[str, Any]]:
    """Fallback: reconstruct pairs from the local raw.jsonl mirror."""
    pairs: dict[str, dict[str, Any]] = {}
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        qid = row.get("query_id")
        if not qid:
            continue
        slot = pairs.setdefault(
            qid,
            {"query_id": qid, "query_text": row["query_text"], "fst": None, "ograg": None},
        )
        slot[row["backend"]] = {
            "answer": row.get("answer"),
            "sources": row.get("sources", []),
            "latency_ms": row.get("latency_ms"),
            "cost_usd": row.get("cost_usd"),
        }
    return [p for p in pairs.values() if p["fst"] and p["ograg"]]


async def main_async(args: argparse.Namespace) -> int:
    run_dir = Path("evals/runs") / args.run_id
    raw_path = run_dir / "raw.jsonl"
    if not run_dir.exists():
        print(f"ERROR: run dir {run_dir} does not exist", file=sys.stderr)
        return 1

    pairs: list[dict[str, Any]] = []
    database_url = os.environ.get("DATABASE_URL")
    if database_url and not args.from_raw:
        pairs = await load_pairs_from_db(database_url, args.run_id)
    if not pairs:
        if raw_path.exists():
            print("Falling back to raw.jsonl")
            pairs = load_pairs_from_raw(raw_path)
        else:
            print(f"ERROR: no pairs found for run_id={args.run_id}", file=sys.stderr)
            return 1

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("ERROR: GEMINI_API_KEY is not set", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from google import genai  # noqa: E402

    client = genai.Client(api_key=gemini_api_key)

    out_path = run_dir / "judged.jsonl"
    print(f"Judging {len(pairs)} pairs → {out_path}")
    with out_path.open("w", encoding="utf-8") as fh:
        for i, p in enumerate(pairs, start=1):
            try:
                # FST = A, OG-RAG = B (consistent throughout the report)
                verdict = await judge_pair(
                    client,
                    p["query_text"],
                    p["fst"]["answer"] or "",
                    p["ograg"]["answer"] or "",
                )
            except Exception as e:  # noqa: BLE001
                print(f"  [{i}/{len(pairs)}] {p['query_id']} JUDGE FAILED: {e}")
                fh.write(json.dumps({"query_id": p["query_id"], "error": str(e)}) + "\n")
                continue

            record = {
                "query_id": p["query_id"],
                "query_text": p["query_text"],
                "fst": {**p["fst"], "scores": verdict["answer_a"]},
                "ograg": {**p["ograg"], "scores": verdict["answer_b"]},
                "judge_notes": verdict.get("notes", ""),
            }
            fh.write(json.dumps(record) + "\n")
            fh.flush()
            print(f"  [{i}/{len(pairs)}] {p['query_id']} ok")

    print(f"Done. Run: python -m evals.report --run-id {args.run_id}")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--from-raw", action="store_true", help="Force reconstruction from raw.jsonl instead of DB")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
