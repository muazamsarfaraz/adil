# P8 eval harness — FST vs OG-RAG

Pipeline:

```
queries.jsonl ──► run.py ──► eval_run table + raw.jsonl
                                       │
                                       ▼
                              judge.py (Gemini Flash)
                                       │
                                       ▼
                              report.py ──► eval_review_<run_id>.md
                                       │
                                       ▼
                       human spot-checks 10 random pairs
                       and updates the .md with pass/fail
```

## One-shot run

```bash
# from adil-rag-api/
export DATABASE_URL=...
export GEMINI_API_KEY=...
export FILE_SEARCH_STORE_ID=...

python -m evals.run               # ~10–15 minutes
# emit "Next: python -m evals.judge --run-id 2026-05-19T09-15-22Z"

python -m evals.judge --run-id 2026-05-19T09-15-22Z
python -m evals.report --run-id 2026-05-19T09-15-22Z
```

`report.py` exits non-zero if any auto-decidable cutover gate fails (quality,
harmfulness, P95 latency). The human spot-check gate is filled in afterwards
by editing `evals/runs/<run_id>/eval_review_<run_id>.md`.

## Refreshing `queries.jsonl` from real shadow traffic

After P9 shadow mode has run for ~7 days:

```bash
python -m evals.extract_queries --days 7 --out evals/candidates.jsonl
# Then manually review every line, redact anything left, copy 30 chosen
# lines into evals/queries.jsonl.
```

`anonymise.py` does best-effort PII stripping (emails, phones, postcodes,
addresses, "my name is X" patterns). The human pass is still mandatory.

## Cutover gate

All must hold to merge `RAG_BACKEND=ograg` as the new default (P10):

| Gate | Source |
| --- | --- |
| OG-RAG aggregate quality ≥ FST | judge.py + report.py |
| No harmfulness ≥ 4 on any query | judge.py + report.py |
| OG-RAG P95 latency ≤ 2× FST P95 | run.py + report.py |
| Human spot-check ≥ 8/10 on both backends | manual |

If any fails: investigate, do not cut over.
