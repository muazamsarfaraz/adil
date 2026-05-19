"""OG-RAG backfill orchestrator.

Iterates over judgments that have been UPLOADED to FST (or previously failed
extraction) and runs the ontology extraction pipeline:

  Pass 1 — structural (regex + spaCy)  → ``extract_pass1``           [zero $]
  Pass 2 — Claude Haiku 4.5            → topics, parties, relations  [$ tracked]
  Pass 3 — Gemini Flash 2.5            → cross-references            [$ tracked]

Pass 1 is wired today. Pass 2 and Pass 3 are registered via the
``pass2_runner`` / ``pass3_runner`` callables — they ship as ``None`` until
the sibling P3 / P4 ClickUp tasks land their implementations, at which point
the backfill picks them up without further code changes here.

Design notes:

* The orchestrator owns the cumulative-USD kill switch. As soon as cumulative
  spend exceeds ``kill_switch_usd`` it sends a Telegram alert (best-effort)
  and returns; no judgments past that point are touched.
* Spend rows are written per-pass via ``ExtractionSpend``; they are the
  authoritative cost ledger queried by the Op dashboard. Pass 1 always
  records ``$0`` so re-runs can be priced reliably.
* Idempotency: a judgment is skipped when it is already ``EXTRACTED`` AND
  the rag-api side already has Paragraph rows for the Case. ``EXTRACTION_FAILED``
  rows are retried — that's the whole point of the status.
* The orchestrator never writes to FST. ``upload_pending`` continues running
  on its existing cron to keep the FST store warm for rollback (P11).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.judgment import ExtractionSpend, Judgment, JudgmentStatus, OgragStatus
from app.services.ograg_extract import ExtractionResult, extract_pass1
from app.services.ontology_writer import case_has_ontology_rows, write_case_extraction
from app.services.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class CostCeilingTripped(Exception):
    """Raised when cumulative LLM spend since the start of this backfill
    exceeds ``BackfillConfig.kill_switch_usd``. Caught by ``run_backfill`` to
    fire the kill-switch alert and stop the loop without flipping the
    current judgment to EXTRACTION_FAILED."""

    def __init__(self, spend_usd: float, ceiling_usd: float) -> None:
        self.spend_usd = spend_usd
        self.ceiling_usd = ceiling_usd
        super().__init__(f"OG-RAG cost ceiling tripped: cumulative spend ${spend_usd:.4f} " f"≥ ${ceiling_usd:.2f}")


# A pass runner takes a judgment ORM row + the running ExtractionResult and
# returns (usd_cost, model_name, input_tokens, output_tokens, note). It may
# mutate ``result`` to attach extra nodes/edges; the orchestrator writes the
# union to rag-api after all passes run.
PassRunner = Callable[
    [Judgment, ExtractionResult],
    Awaitable[tuple[float, str | None, int | None, int | None, str | None]],
]


@dataclass
class BackfillConfig:
    kill_switch_usd: float = 50.0
    limit: int | None = None
    since_id: str | None = None  # UUID string; orchestrator selects id > since_id
    # Optional runners — wired in by P3/P4. None = pass skipped.
    pass2_runner: PassRunner | None = None
    pass3_runner: PassRunner | None = None


@dataclass
class BackfillStats:
    selected: int = 0
    extracted: int = 0
    failed: int = 0
    skipped_already_done: int = 0
    spend_usd: float = 0.0
    kill_switch_tripped: bool = False
    nodes_written: int = 0
    edges_written: int = 0
    per_pass_spend: dict[str, float] = field(default_factory=dict)
    # Wall-clock timestamp the backfill started; used by the DB-backed
    # cost-ceiling check so concurrent retries / crashed runs can't double-spend.
    start_ts: datetime | None = None


async def _current_spend_usd(
    session_factory: async_sessionmaker[AsyncSession],
    since: datetime,
) -> float:
    """Sum ``extraction_spend_usd.usd_cost`` for rows created since ``since``.

    This is the authoritative cost ledger query used by the kill switch
    before every paid pass. Querying the DB (vs the in-memory tally on
    ``BackfillStats``) means a re-run that crashed mid-flight, or a
    concurrent retry attempt, still trips the ceiling correctly.
    """
    async with session_factory() as session:
        # SQLite stores DateTime(timezone=True) as a naive string and the
        # driver compares text — a tz-aware ``since`` would not be flagged
        # as such by the column type, so normalize both sides to naive UTC.
        bind = session_factory.kw.get("bind") or session_factory.kw.get("engine")  # type: ignore[attr-defined]
        dialect = getattr(bind, "dialect", None)
        if dialect is not None and dialect.name == "sqlite" and since.tzinfo is not None:
            since = since.astimezone(timezone.utc).replace(tzinfo=None)
        result = await session.execute(
            select(func.coalesce(func.sum(ExtractionSpend.usd_cost), 0)).where(ExtractionSpend.created_at >= since)
        )
        value = result.scalar_one()
        return float(value or 0)


async def _enforce_cost_ceiling(
    session_factory: async_sessionmaker[AsyncSession],
    config: "BackfillConfig",
    stats: "BackfillStats",
    pass_name: str,
) -> None:
    """Raise ``CostCeilingTripped`` if cumulative spend ≥ kill switch.

    Called immediately before every paid pass (Haiku/Flash) so we never
    spend past the configured ceiling. Updates ``stats.spend_usd`` to the
    DB-sourced number so callers see the authoritative cumulative figure.
    """
    if stats.start_ts is None:
        return  # paranoid — set by run_backfill before the first call.
    db_spend = await _current_spend_usd(session_factory, stats.start_ts)
    # Keep stats in sync with the DB so the final summary is accurate even
    # if multiple processes recorded rows concurrently.
    stats.spend_usd = max(stats.spend_usd, db_spend)
    if db_spend >= config.kill_switch_usd:
        logger.warning(
            "OG-RAG cost ceiling tripped before %s: $%.4f ≥ $%.2f",
            pass_name,
            db_spend,
            config.kill_switch_usd,
        )
        raise CostCeilingTripped(db_spend, config.kill_switch_usd)


async def _record_spend(
    session_factory: async_sessionmaker[AsyncSession],
    judgment_id,
    pass_name: str,
    usd_cost: float,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    note: str | None,
) -> None:
    async with session_factory() as session:
        session.add(
            ExtractionSpend(
                judgment_id=judgment_id,
                pass_name=pass_name,
                usd_cost=Decimal(str(round(usd_cost, 6))),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                note=note,
                # Set Python-side so the timestamp has microsecond precision
                # and the kill-switch comparison vs ``BackfillStats.start_ts``
                # is reliable on SQLite (whose CURRENT_TIMESTAMP truncates to
                # whole seconds and silently drops sub-second start ledgers).
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _update_judgment_status(
    session_factory: async_sessionmaker[AsyncSession],
    judgment_id,
    status: OgragStatus,
    error: str | None = None,
) -> None:
    async with session_factory() as session:
        result = await session.execute(select(Judgment).where(Judgment.id == judgment_id))
        judgment = result.scalar_one_or_none()
        if judgment is None:
            return
        judgment.ograg_status = status.value
        if error is not None:
            judgment.error_message = error
        await session.commit()


async def _select_candidates(
    session_factory: async_sessionmaker[AsyncSession],
    config: BackfillConfig,
) -> list[Judgment]:
    async with session_factory() as session:
        stmt = (
            select(Judgment)
            .where(
                Judgment.status.in_([JudgmentStatus.UPLOADED, JudgmentStatus.FAILED]),
                Judgment.ograg_status.in_([OgragStatus.PENDING.value, OgragStatus.EXTRACTION_FAILED.value]),
            )
            .order_by(Judgment.id)
        )
        if config.since_id:
            stmt = stmt.where(Judgment.id > config.since_id)
        if config.limit:
            stmt = stmt.limit(config.limit)
        rows = (await session.execute(stmt)).scalars().all()
        # Detach from session — orchestrator passes ORM rows around freely.
        for row in rows:
            session.expunge(row)
        return list(rows)


async def run_backfill(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    rag_database_url: str | None,
    notifier: TelegramNotifier | None,
    config: BackfillConfig,
) -> BackfillStats:
    """Drive the OG-RAG backfill end-to-end.

    Returns ``BackfillStats``. Errors on a single judgment are isolated:
    the orchestrator marks that row ``EXTRACTION_FAILED`` and moves on. Only
    the kill switch halts the loop early.
    """
    stats = BackfillStats(start_ts=datetime.now(timezone.utc))

    candidates = await _select_candidates(session_factory, config)
    stats.selected = len(candidates)
    logger.info("backfill_ograg: %d judgments selected", stats.selected)

    async def _trip_kill_switch(spend_usd: float) -> None:
        stats.kill_switch_tripped = True
        stats.spend_usd = spend_usd
        msg = (
            f"🛑 *OG-RAG backfill — KILL SWITCH*\n"
            f"Cumulative spend ${spend_usd:.2f} ≥ ${config.kill_switch_usd:.2f}\n"
            f"Extracted: {stats.extracted}  Failed: {stats.failed}  "
            f"Remaining (skipped): {stats.selected - stats.extracted - stats.failed}"
        )
        logger.warning("backfill_ograg kill switch tripped at $%.2f", spend_usd)
        if notifier:
            try:
                await notifier.send(msg)
            except Exception:
                logger.exception("Failed to send kill-switch alert")

    for judgment in candidates:
        # Pre-judgment guard. The authoritative per-call check lives inside
        # _process_one, but we also gate at the loop level so a fully-spent
        # ceiling doesn't even mark the next judgment EXTRACTING.
        try:
            await _enforce_cost_ceiling(session_factory, config, stats, "pre_judgment")
        except CostCeilingTripped as exc:
            await _trip_kill_switch(exc.spend_usd)
            break

        try:
            await _process_one(
                judgment=judgment,
                session_factory=session_factory,
                rag_database_url=rag_database_url,
                config=config,
                stats=stats,
            )
        except CostCeilingTripped as exc:
            # Roll the in-flight judgment back to PENDING so a future run
            # (with the threshold lifted) picks it up instead of leaving it
            # stuck in EXTRACTING.
            await _update_judgment_status(session_factory, judgment.id, OgragStatus.PENDING)
            await _trip_kill_switch(exc.spend_usd)
            break
        except Exception as exc:  # noqa: BLE001 — orchestrator must keep going
            logger.exception("backfill_ograg: judgment %s failed", judgment.neutral_citation)
            await _update_judgment_status(
                session_factory, judgment.id, OgragStatus.EXTRACTION_FAILED, error=str(exc)[:1000]
            )
            stats.failed += 1

    logger.info(
        "backfill_ograg complete: extracted=%d failed=%d skipped=%d spend=$%.4f kill_switch=%s",
        stats.extracted,
        stats.failed,
        stats.skipped_already_done,
        stats.spend_usd,
        stats.kill_switch_tripped,
    )
    return stats


async def _process_one(
    *,
    judgment: Judgment,
    session_factory: async_sessionmaker[AsyncSession],
    rag_database_url: str | None,
    config: BackfillConfig,
    stats: BackfillStats,
) -> None:
    """Run all configured passes for one judgment and write to ontology."""

    # ---- Pass 1 — structural (always runs) -----------------------------
    result: ExtractionResult = extract_pass1(judgment)

    # Idempotency probe: skip when this Case already has Paragraph rows
    # written on the rag-api side AND the judgment is currently EXTRACTED.
    # We only probe when both conditions could realistically hold so we
    # don't pay round-trip latency on every PENDING row.
    if judgment.ograg_status == OgragStatus.EXTRACTED.value:
        already = await case_has_ontology_rows(rag_database_url, result.case.node_id)
        if already:
            stats.skipped_already_done += 1
            logger.debug("backfill_ograg: skipping %s — already extracted", judgment.neutral_citation)
            return

    await _update_judgment_status(session_factory, judgment.id, OgragStatus.EXTRACTING)
    judgment.ograg_status = OgragStatus.EXTRACTING.value

    # Record pass 1 spend ($0) so the ledger has a row per (judgment, pass).
    await _record_spend(
        session_factory,
        judgment.id,
        "pass1_structural",
        0.0,
        model="regex+spacy",
        input_tokens=None,
        output_tokens=None,
        note=f"paragraphs={len(result.paragraphs)} statute_refs={len(result.statute_refs)} section_refs={len(result.section_refs)}",
    )
    stats.per_pass_spend["pass1_structural"] = stats.per_pass_spend.get("pass1_structural", 0.0) + 0.0

    # ---- Pass 2 — Claude Haiku (optional) ------------------------------
    if config.pass2_runner is not None:
        # DB-backed ceiling check immediately before the paid call.
        await _enforce_cost_ceiling(session_factory, config, stats, "pass2_claude")
        cost, model, in_tok, out_tok, note = await config.pass2_runner(judgment, result)
        await _record_spend(session_factory, judgment.id, "pass2_claude", cost, model, in_tok, out_tok, note)
        stats.spend_usd += cost
        stats.per_pass_spend["pass2_claude"] = stats.per_pass_spend.get("pass2_claude", 0.0) + cost

    # ---- Pass 3 — Gemini Flash (optional) ------------------------------
    if config.pass3_runner is not None:
        await _enforce_cost_ceiling(session_factory, config, stats, "pass3_gemini")
        cost, model, in_tok, out_tok, note = await config.pass3_runner(judgment, result)
        await _record_spend(session_factory, judgment.id, "pass3_gemini", cost, model, in_tok, out_tok, note)
        stats.spend_usd += cost
        stats.per_pass_spend["pass3_gemini"] = stats.per_pass_spend.get("pass3_gemini", 0.0) + cost

    # ---- Write to rag-api ontology -------------------------------------
    nodes, edges = await write_case_extraction(rag_database_url, result)
    stats.nodes_written += nodes
    stats.edges_written += edges

    await _update_judgment_status(session_factory, judgment.id, OgragStatus.EXTRACTED, error=None)
    stats.extracted += 1
