"""P8 eval harness for the FST → OG-RAG cutover.

Pipeline:

1. ``queries.jsonl``       — 30 anonymised queries (the eval set).
2. ``run.py``              — runs both backends per query, writes to ``eval_run``.
3. ``judge.py``            — Gemini Flash judge with rubric, writes ``judged.jsonl``.
4. ``report.py``           — aggregates + emits ``eval_review_<run_id>.md``.
5. Human spot-checks 10 flagged queries; verdicts recorded in the .md.

See ``evals/README.md`` for the operator workflow.
"""
