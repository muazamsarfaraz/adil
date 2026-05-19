"""Tests for the OG-RAG backfill orchestrator.

These use the same SQLite-backed Base.metadata setup as the other worker
tests; we never hit a real Postgres or rag-api DB here. The cross-DB write
(``write_case_extraction``) is monkey-patched to a no-op so we exercise the
orchestrator's status transitions, spend accounting, kill switch, and
idempotency logic without coupling to the schema of the rag-api side.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.judgment import Base, ExtractionSpend, Judgment, JudgmentStatus, OgragStatus
from app.services.ograg_backfill import BackfillConfig, run_backfill

TEST_DB_URL = "sqlite+aiosqlite:///test_backfill.db"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_judgment(citation: str, status: JudgmentStatus = JudgmentStatus.UPLOADED) -> Judgment:
    return Judgment(
        id=uuid.uuid4(),
        neutral_citation=citation,
        tna_uri=f"test/{citation}",
        tna_url=f"https://example.test/{citation}",
        court="eat",
        case_name=f"Case for {citation}",
        judgment_date=date(2023, 1, 1),
        search_domain="test_domain",
        search_query="test",
        raw_xml="<doc/>",
        # A non-trivial clean_text so pass1 actually produces paragraphs.
        clean_text=(
            "1. The claimant brought a religious discrimination claim under "
            "the Equality Act 2010 section 13.\n\n"
            "2. The tribunal held that section 19 indirect discrimination "
            "was also engaged.\n\n"
            "3. Reference is made to Public Order Act 1986 section 4A."
        ),
        status=status,
        ograg_status=OgragStatus.PENDING.value,
    )


@pytest.mark.asyncio
async def test_backfill_extracts_uploaded_judgments(db, monkeypatch):
    """A clean run: 2 UPLOADED judgments → both EXTRACTED, spend rows recorded."""
    import app.services.ograg_backfill as bf

    monkeypatch.setattr(bf, "write_case_extraction", _stub_write(returns=(5, 7)))
    monkeypatch.setattr(bf, "case_has_ontology_rows", _stub_async(False))

    async with _session() as s:
        s.add(_make_judgment("[2023] EAT 1"))
        s.add(_make_judgment("[2023] EAT 2"))
        await s.commit()

    stats = await run_backfill(
        session_factory=_session,
        rag_database_url="postgres://stub",
        notifier=None,
        config=BackfillConfig(),
    )

    assert stats.selected == 2
    assert stats.extracted == 2
    assert stats.failed == 0
    assert stats.nodes_written == 10
    assert stats.edges_written == 14

    async with _session() as s:
        rows = (await s.execute(select(Judgment))).scalars().all()
        assert all(j.ograg_status == OgragStatus.EXTRACTED.value for j in rows)
        spend_rows = (await s.execute(select(ExtractionSpend))).scalars().all()
        # pass1_structural is recorded once per judgment.
        assert len(spend_rows) == 2
        assert all(row.pass_name == "pass1_structural" for row in spend_rows)
        assert all(row.usd_cost == Decimal("0.000000") for row in spend_rows)


@pytest.mark.asyncio
async def test_backfill_skips_already_extracted(db, monkeypatch):
    """A row that is EXTRACTED and has ontology rows on the rag-api side is skipped."""
    import app.services.ograg_backfill as bf

    monkeypatch.setattr(bf, "write_case_extraction", _stub_write(returns=(0, 0)))
    # case_has_ontology_rows returns True → orchestrator must skip.
    monkeypatch.setattr(bf, "case_has_ontology_rows", _stub_async(True))

    async with _session() as s:
        j = _make_judgment("[2023] EAT 7")
        j.ograg_status = OgragStatus.EXTRACTED.value
        s.add(j)
        await s.commit()

    stats = await run_backfill(
        session_factory=_session,
        rag_database_url="postgres://stub",
        notifier=None,
        config=BackfillConfig(),
    )
    # Already-extracted rows aren't even selected (they fail the WHERE on ograg_status).
    assert stats.selected == 0
    assert stats.skipped_already_done == 0


@pytest.mark.asyncio
async def test_backfill_retries_extracted_failed(db, monkeypatch):
    """EXTRACTION_FAILED is in-scope for a re-run."""
    import app.services.ograg_backfill as bf

    monkeypatch.setattr(bf, "write_case_extraction", _stub_write(returns=(3, 4)))
    monkeypatch.setattr(bf, "case_has_ontology_rows", _stub_async(False))

    async with _session() as s:
        j = _make_judgment("[2023] EAT 8")
        j.ograg_status = OgragStatus.EXTRACTION_FAILED.value
        s.add(j)
        await s.commit()

    stats = await run_backfill(
        session_factory=_session,
        rag_database_url="postgres://stub",
        notifier=None,
        config=BackfillConfig(),
    )
    assert stats.selected == 1
    assert stats.extracted == 1
    assert stats.failed == 0


@pytest.mark.asyncio
async def test_kill_switch_trips_on_cumulative_spend(db, monkeypatch):
    """Four judgments × $20 pass2 cost, threshold $50 → switch must trip before #4."""
    import app.services.ograg_backfill as bf

    monkeypatch.setattr(bf, "write_case_extraction", _stub_write(returns=(1, 0)))
    monkeypatch.setattr(bf, "case_has_ontology_rows", _stub_async(False))

    async def expensive_pass2(_judgment, _result):
        return (20.0, "claude-haiku-4.5", 1000, 200, "stub")

    async with _session() as s:
        for n in range(4):
            s.add(_make_judgment(f"[2023] EAT {100 + n}"))
        await s.commit()

    stats = await run_backfill(
        session_factory=_session,
        rag_database_url="postgres://stub",
        notifier=None,
        config=BackfillConfig(kill_switch_usd=50.0, pass2_runner=expensive_pass2),
    )

    # Switch is checked at the top of the loop, so #1+#2+#3 run (spend $60),
    # then before #4 we trip. extracted=3, kill_switch_tripped=True.
    assert stats.kill_switch_tripped is True
    assert stats.extracted == 3
    assert stats.spend_usd == 60.0


@pytest.mark.asyncio
async def test_pass2_failure_marks_judgment_failed(db, monkeypatch):
    """If pass2_runner raises, that judgment is marked EXTRACTION_FAILED and the loop continues."""
    import app.services.ograg_backfill as bf

    monkeypatch.setattr(bf, "write_case_extraction", _stub_write(returns=(0, 0)))
    monkeypatch.setattr(bf, "case_has_ontology_rows", _stub_async(False))

    async def failing_pass2(_j, _r):
        raise RuntimeError("anthropic api 500")

    async with _session() as s:
        s.add(_make_judgment("[2023] EAT 200"))
        s.add(_make_judgment("[2023] EAT 201"))
        await s.commit()

    stats = await run_backfill(
        session_factory=_session,
        rag_database_url="postgres://stub",
        notifier=None,
        config=BackfillConfig(pass2_runner=failing_pass2),
    )

    assert stats.failed == 2
    assert stats.extracted == 0
    async with _session() as s:
        rows = (await s.execute(select(Judgment))).scalars().all()
        assert all(j.ograg_status == OgragStatus.EXTRACTION_FAILED.value for j in rows)
        assert all("anthropic api 500" in (j.error_message or "") for j in rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_write(returns: tuple[int, int]):
    async def _fn(_rag_db_url, _result):
        return returns

    return _fn


def _stub_async(value):
    async def _fn(*_args, **_kwargs):
        return value

    return _fn
