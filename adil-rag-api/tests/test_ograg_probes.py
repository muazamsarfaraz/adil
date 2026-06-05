"""Unit tests for ograg.probes — MSentry probes for OG-RAG failure modes.

Pure unit tests: no real DB, no real Gemini API. We patch the heavy deps
and verify the probe wiring: regex extraction, hallucination detection,
empty-retrieval alerting, stall threshold, scheduler cancellation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from ograg import probes

pytestmark = pytest.mark.asyncio


def _fake_pool(conn):
    """Build an AsyncMock pool whose acquire() yields `conn` and release() is
    a no-op — mirrors the shared bounded pool check_citations now acquires from."""
    pool = AsyncMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock()
    return pool


# ── Citation regex ─────────────────────────────────────────────────────────
async def test_citation_regex_matches_common_forms():
    text = "See [2021] UKSC 12, also [2024] EWCA Civ 345 and [2020] UKUT 100 (AAC). " "And [2023] EWHC 1234 (QB)."
    found = [probes._normalize_citation(m.group(0)) for m in probes.CITATION_REGEX.finditer(text)]
    assert "[2021] UKSC 12" in found
    assert "[2024] EWCA CIV 345" in found
    assert "[2023] EWHC 1234 (QB)".upper() in found


async def test_citation_regex_ignores_non_citations():
    text = "We saw [2023] in the calendar but not citing anything."
    assert list(probes.CITATION_REGEX.finditer(text)) == []


# ── check_citations ────────────────────────────────────────────────────────
async def test_check_citations_no_citations_no_db_call():
    with patch("ograg.probes.get_pool", new=AsyncMock()) as m:
        result = await probes.check_citations("answer with no citations")
    assert result == []
    m.assert_not_called()


async def test_check_citations_skipped_when_no_db_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with patch("ograg.probes.get_pool", new=AsyncMock()) as m:
        result = await probes.check_citations("Look at [2021] UKSC 12 for guidance")
    assert result == []
    m.assert_not_called()


async def test_check_citations_flags_unknown_cases(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://fake")

    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(return_value=True)  # ontology_node exists
    # Only [2021] UKSC 12 is known; [2024] EWCA Civ 999 is not
    fake_conn.fetch = AsyncMock(return_value=[{"nc": "[2021] UKSC 12"}])
    fake_conn.close = AsyncMock()

    notified: list[tuple] = []

    def fake_notify(severity, kind, message, **ctx):
        notified.append((severity, kind, message, ctx))

    with (
        patch("ograg.probes.get_pool", new=AsyncMock(return_value=_fake_pool(fake_conn))),
        patch("ograg.probes.notify", side_effect=fake_notify),
    ):
        unknown = await probes.check_citations(
            "Consider [2021] UKSC 12 and also [2024] EWCA Civ 999.",
            db_url="postgres://fake",
        )

    assert unknown == ["[2024] EWCA CIV 999"]
    assert len(notified) == 1
    sev, kind, msg, ctx = notified[0]
    assert sev == "warn"
    assert kind == "ograg.hallucinated_citation"
    # Citation must appear in the message itself so operators can triage from
    # the alert title without expanding extras.
    assert "[2024] EWCA CIV 999" in msg
    assert ctx["total"] == 1


async def test_check_citations_message_truncates_long_lists(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://fake")

    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(return_value=True)
    fake_conn.fetch = AsyncMock(return_value=[])  # nothing known — all hallucinated
    fake_conn.close = AsyncMock()

    notified: list = []
    text = "See [2024] UKSC 1, [2024] UKSC 2, [2024] UKSC 3, " "[2024] UKSC 4 and [2024] UKSC 5."

    with (
        patch("ograg.probes.get_pool", new=AsyncMock(return_value=_fake_pool(fake_conn))),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append((a, k))),
    ):
        await probes.check_citations(text, db_url="postgres://fake")

    assert len(notified) == 1
    (_sev, _kind, msg), _ctx = notified[0]
    assert "+2 more" in msg  # shows first 3, indicates 2 more
    assert msg.count("[2024]") == 3


async def test_check_citations_passes_whitespace_collapsed_cites_to_db(monkeypatch):
    """The DB query is the side that normalizes stored whitespace; the
    Python side guarantees the parameters we pass are already collapsed.
    Verify the params list never contains a citation with double spaces."""
    monkeypatch.setenv("DATABASE_URL", "postgres://fake")

    captured: dict = {}

    async def fake_fetch(query, params):
        captured["params"] = params
        return [{"nc": p} for p in params]  # pretend all known

    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(return_value=True)
    fake_conn.fetch = fake_fetch
    fake_conn.close = AsyncMock()

    with (
        patch("ograg.probes.get_pool", new=AsyncMock(return_value=_fake_pool(fake_conn))),
        patch("ograg.probes.notify"),
    ):
        await probes.check_citations("Cite [ 2021 ]  UKSC  12 here.", db_url="postgres://fake")

    assert captured["params"] == ["[2021] UKSC 12"]


async def test_check_citations_silent_when_ontology_table_missing(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://fake")

    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(return_value=False)  # ontology_node does NOT exist
    fake_conn.close = AsyncMock()

    notified: list = []

    with (
        patch("ograg.probes.get_pool", new=AsyncMock(return_value=_fake_pool(fake_conn))),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        result = await probes.check_citations("[2021] UKSC 12", db_url="postgres://fake")

    assert result == []
    assert notified == []


async def test_check_citations_uses_bounded_pool_not_raw_connect(monkeypatch):
    """Regression for ograg.retrieval_probe 'too many clients already': every
    served answer runs check_citations, so it MUST acquire from the shared
    bounded pool and release the connection — never open an unbounded
    asyncpg.connect() that re-exhausts Postgres max_connections."""
    monkeypatch.setenv("DATABASE_URL", "postgres://fake")

    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(return_value=True)
    fake_conn.fetch = AsyncMock(return_value=[{"nc": "[2021] UKSC 12"}])
    pool = _fake_pool(fake_conn)

    with (
        patch("ograg.probes.get_pool", new=AsyncMock(return_value=pool)) as gp,
        patch("ograg.probes.asyncpg.connect", new=AsyncMock()) as raw_connect,
        patch("ograg.probes.notify"),
    ):
        await probes.check_citations("Consider [2021] UKSC 12.", db_url="postgres://fake")

    gp.assert_awaited_once()
    pool.acquire.assert_awaited_once()
    pool.release.assert_awaited_once_with(fake_conn)
    raw_connect.assert_not_called()


# ── Empty retrieval probe ──────────────────────────────────────────────────
async def test_empty_retrieval_probe_alerts_on_zero_hits():
    notified: list = []

    with (
        patch("ograg.probes.retrieve", new=AsyncMock(return_value=[])),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append((a, k))),
    ):
        await probes._empty_retrieval_probe()

    assert len(notified) == 1
    args, _ = notified[0]
    assert args[0] == "error"
    assert args[1] == "ograg.retrieval_empty"


async def test_empty_retrieval_probe_silent_when_hits():
    notified: list = []

    with (
        patch("ograg.probes.retrieve", new=AsyncMock(return_value=[{"id": "a"}])),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        await probes._empty_retrieval_probe()

    assert notified == []


async def test_empty_retrieval_probe_reports_raised_exception():
    notified: list = []

    with (
        patch("ograg.probes.retrieve", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        await probes._empty_retrieval_probe()

    assert len(notified) == 1
    assert notified[0][1] == "ograg.retrieval_probe"


# ── Embedding probe ────────────────────────────────────────────────────────
async def test_embedding_probe_classifies_5xx_separately():
    notified: list = []

    with (
        patch("ograg.probes.embed_one", new=AsyncMock(side_effect=RuntimeError("503 UNAVAILABLE"))),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        await probes._embedding_health_probe()

    assert notified[0][1] == "ograg.embedding_5xx"
    assert notified[0][0] == "error"


async def test_embedding_probe_non_5xx_is_warn():
    notified: list = []

    with (
        patch("ograg.probes.embed_one", new=AsyncMock(side_effect=ValueError("bad input"))),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        await probes._embedding_health_probe()

    assert notified[0][1] == "ograg.embedding_error"
    assert notified[0][0] == "warn"


async def test_embedding_probe_silent_when_healthy():
    notified: list = []

    with (
        patch("ograg.probes.embed_one", new=AsyncMock(return_value=[0.1] * 768)),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        await probes._embedding_health_probe()

    assert notified == []


# ── Extraction stall probe ─────────────────────────────────────────────────
async def test_stall_probe_skipped_when_no_uploader_url(monkeypatch):
    monkeypatch.delenv("UPLOADER_DATABASE_URL", raising=False)
    with patch("ograg.probes.asyncpg.connect", new=AsyncMock()) as m:
        await probes._extraction_stall_probe()
    m.assert_not_called()


async def test_stall_probe_alerts_when_threshold_exceeded(monkeypatch):
    monkeypatch.setenv("UPLOADER_DATABASE_URL", "postgres://fake")
    monkeypatch.setattr(probes, "STALL_THRESHOLD_ROWS", 50)

    fake_conn = AsyncMock()
    # First fetchval: table exists. Second: stalled count.
    fake_conn.fetchval = AsyncMock(side_effect=[True, 75])
    fake_conn.close = AsyncMock()

    notified: list = []
    with (
        patch("ograg.probes.asyncpg.connect", new=AsyncMock(return_value=fake_conn)),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append((a, k))),
    ):
        await probes._extraction_stall_probe()

    assert len(notified) == 1
    args, kw = notified[0]
    assert args[0] == "warn"
    assert args[1] == "ograg.extraction_stalled"
    assert kw["stalled"] == 75


async def test_stall_probe_silent_below_threshold(monkeypatch):
    monkeypatch.setenv("UPLOADER_DATABASE_URL", "postgres://fake")
    monkeypatch.setattr(probes, "STALL_THRESHOLD_ROWS", 50)

    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(side_effect=[True, 12])
    fake_conn.close = AsyncMock()

    notified: list = []
    with (
        patch("ograg.probes.asyncpg.connect", new=AsyncMock(return_value=fake_conn)),
        patch("ograg.probes.notify", side_effect=lambda *a, **k: notified.append(a)),
    ):
        await probes._extraction_stall_probe()

    assert notified == []


# ── Scheduler ──────────────────────────────────────────────────────────────
async def test_run_forever_is_cancellable():
    runs = 0

    async def fake_run_once():
        nonlocal runs
        runs += 1

    with patch("ograg.probes._run_once", side_effect=fake_run_once):
        task = asyncio.create_task(probes.run_forever(interval_secs=0, jitter_first=False))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert runs >= 1


async def test_run_once_swallows_probe_crashes():
    async def boom():
        raise RuntimeError("explode")

    async def fine():
        return None

    with patch.object(probes, "PROBES", (("boom", boom), ("fine", fine))):
        await probes._run_once()  # must not raise
