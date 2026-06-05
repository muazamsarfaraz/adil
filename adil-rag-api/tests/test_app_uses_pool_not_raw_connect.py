"""Regression guard for ograg.retrieval_probe 'sorry, too many clients already'.

The retrieval probe surfaced Postgres connection exhaustion. The root cause was
request-path code opening a fresh ``asyncpg.connect()`` per request instead of
acquiring from the shared bounded pool (``_get_pool()``). check_citations and the
OG-RAG retrieval/shadow paths were pooled in earlier commits; the upload-ownership
check (``_load_uploads_from_r2``) and ``record_upload`` were the last two raw
connects in app.py and have now been routed through the pool too.

This guard fails if any raw ``asyncpg.connect(`` call reappears in app.py, so the
whole request path stays bounded by the pool and can't re-exhaust
``max_connections``.
"""

from __future__ import annotations

import pathlib
import re

APP_PY = pathlib.Path(__file__).resolve().parent.parent / "app.py"


def test_app_has_no_raw_asyncpg_connect():
    src = APP_PY.read_text(encoding="utf-8")
    # Strip comments so the explanatory note mentioning asyncpg.connect() in
    # prose doesn't trip the guard — we only care about real call sites.
    code_only = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    offenders = re.findall(r"asyncpg\.connect\s*\(", code_only)
    assert offenders == [], (
        "app.py must acquire from the shared bounded pool via _get_pool(); "
        f"found {len(offenders)} raw asyncpg.connect() call(s) that can re-exhaust "
        "Postgres max_connections (surfaces as ograg.retrieval_probe "
        "'sorry, too many clients already')."
    )
