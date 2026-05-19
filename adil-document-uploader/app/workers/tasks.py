from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import httpx

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import SEARCH_DOMAINS, SearchDomain, get_settings
from app.models.act import Act, ActSection, ActSubsection
from app.models.judgment import Judgment, JudgmentStatus
from app.models.solicitor_firm import SolicitorFirm
from app.services.acts_seed import UK_ACTS_SEED
from app.services.gemini_uploader import GeminiUploader
from app.services.legislation_client import LegislationClient, ParsedAct
from app.services.ontology_writer import write_act_to_ontology
from app.services.sra_scraper import run_scrape
from app.services.telegram import TelegramNotifier
from app.services.tna_client import TNAClient
from app.services.xml_parser import build_upload_text, parse_judgment_xml

logger = logging.getLogger(__name__)


async def _fetch_for_domain(
    tna_client: TNAClient,
    domain: SearchDomain,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    """Fetch case law for a single search domain. Returns (new_count, skip_count)."""
    new_count = 0
    skip_count = 0

    for query in domain.queries:
        for court in domain.courts:
            entries = await tna_client.search(query=query, court=court)

            for entry in entries:
                async with session_factory() as session:
                    exists = await session.execute(
                        select(Judgment.id).where(Judgment.neutral_citation == entry.neutral_citation)
                    )
                    if exists.scalar_one_or_none() is not None:
                        skip_count += 1
                        continue

                try:
                    raw_xml = await tna_client.download_judgment(entry.tna_uri)
                    parsed = parse_judgment_xml(raw_xml)

                    judgment = Judgment(
                        neutral_citation=entry.neutral_citation,
                        tna_uri=entry.tna_uri,
                        tna_url=entry.tna_url,
                        court=court,
                        case_name=entry.case_name,
                        judgment_date=date.fromisoformat(parsed.judgment_date) if parsed.judgment_date else None,
                        search_domain=domain.name,
                        search_query=query,
                        raw_xml=raw_xml,
                        clean_text=parsed.clean_text,
                        status=JudgmentStatus.PENDING,
                    )

                    async with session_factory() as session:
                        session.add(judgment)
                        await session.commit()
                    new_count += 1

                except Exception:
                    logger.exception("Failed to fetch/parse %s", entry.neutral_citation)

    return new_count, skip_count


async def fetch_case_law(ctx: dict) -> dict:
    """arq task: fetch case law from TNA for all search domains."""
    settings = get_settings()
    tna_client = TNAClient(base_url=settings.tna_base_url, max_rpm=settings.tna_max_requests_per_minute)

    from app.database import async_session

    total_new = 0
    total_skip = 0

    try:
        for domain in SEARCH_DOMAINS:
            new, skip = await _fetch_for_domain(tna_client, domain, async_session)
            total_new += new
            total_skip += skip
            logger.info("Domain %s: %d new, %d skipped", domain.name, new, skip)
    finally:
        await tna_client.close()

    logger.info("Fetch complete: %d new judgments, %d duplicates skipped", total_new, total_skip)
    return {"new": total_new, "skipped": total_skip}


async def upload_pending(ctx: dict) -> dict:
    """arq task: upload pending judgments to Gemini FST store."""
    settings = get_settings()

    from google import genai
    from app.database import async_session

    client = genai.Client(api_key=settings.gemini_api_key)
    uploader = GeminiUploader(client=client, store_id=settings.file_search_store_id)

    uploaded = 0
    failed = 0

    async with async_session() as session:
        result = await session.execute(select(Judgment).where(Judgment.status == JudgmentStatus.PENDING))
        judgments = result.scalars().all()

    for judgment in judgments:
        try:
            text = build_upload_text(
                neutral_citation=judgment.neutral_citation,
                case_name=judgment.case_name,
                court=judgment.court,
                judgment_date=str(judgment.judgment_date) if judgment.judgment_date else None,
                tna_url=judgment.tna_url,
                clean_text=judgment.clean_text,
            )
            display_name = f"{judgment.neutral_citation} - {judgment.case_name}"
            file_id = uploader.upload_document(text=text, display_name=display_name)

            async with async_session() as session:
                judgment.gemini_file_id = file_id
                judgment.status = JudgmentStatus.UPLOADED
                judgment.uploaded_at = datetime.now(timezone.utc)
                judgment.error_message = None
                await session.merge(judgment)
                await session.commit()
            uploaded += 1

        except Exception as exc:
            logger.exception("Failed to upload %s", judgment.neutral_citation)
            async with async_session() as session:
                judgment.status = JudgmentStatus.FAILED
                judgment.error_message = str(exc)
                await session.merge(judgment)
                await session.commit()
            failed += 1

    logger.info("Upload complete: %d uploaded, %d failed", uploaded, failed)
    return {"uploaded": uploaded, "failed": failed}


def _parse_targets(spec: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if "=" in pair:
            name, url = pair.split("=", 1)
            out[name.strip()] = url.strip()
    return out


async def _check_service_health(targets: dict[str, str]) -> dict[str, tuple[bool, str]]:
    """Check each target URL. Returns {name: (ok, status_str)}."""
    results: dict[str, tuple[bool, str]] = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for name, url in targets.items():
            try:
                resp = await client.get(url)
                ok = 200 <= resp.status_code < 400
                results[name] = (ok, f"HTTP {resp.status_code}")
            except Exception as exc:
                results[name] = (False, f"{type(exc).__name__}")
    return results


async def _keep_alive_fst() -> tuple[bool, str]:
    """End-to-end keep-alive query through the RAG API.

    Sends a real legal question to adil-rag-api which exercises the full
    pipeline: FastAPI endpoint -> RAGService -> Gemini FST store retrieval.
    This both keeps the FST store active AND verifies the RAG service works.
    Returns (ok, detail).
    """
    settings = get_settings()
    if not settings.rag_api_key:
        return False, "RAG_API_KEY not configured"

    payload = {
        "query": "Briefly: what is indirect religious discrimination under the Equality Act 2010?",
        "max_sources": 1,
        "include_viability_score": False,
    }
    headers = {"X-API-Key": settings.rag_api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{settings.rag_api_url}/api/v1/query", json=payload, headers=headers)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text[:80]}"
        data = resp.json()
        answer_len = len(data.get("answer", ""))
        sources = len(data.get("sources") or [])
        return True, f"{answer_len} chars, {sources} sources"
    except Exception as exc:
        logger.exception("RAG API keep-alive failed")
        return False, f"{type(exc).__name__}: {str(exc)[:80]}"


async def _get_judgment_stats(session_factory) -> dict[str, int]:
    """Get judgment counts by status."""
    from sqlalchemy import func

    try:
        async with session_factory() as session:
            rows = await session.execute(select(Judgment.status, func.count(Judgment.id)).group_by(Judgment.status))
            return {row[0].value: row[1] for row in rows}
    except Exception as exc:
        logger.exception("Failed to get judgment stats")
        return {"error": str(exc)[:80]}


def _format_heartbeat(
    service_results: dict[str, tuple[bool, str]],
    fst_ok: bool,
    fst_detail: str,
    judgment_stats: dict[str, int],
) -> tuple[str, bool]:
    """Format Telegram message. Returns (text, all_healthy)."""
    lines = ["*AskAdil Heartbeat*", ""]

    all_healthy = True
    lines.append("*Services:*")
    for name, (ok, detail) in service_results.items():
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} `{name}` — {detail}")
        if not ok:
            all_healthy = False

    lines.append("")
    icon = "✅" if fst_ok else "❌"
    lines.append(f"*RAG pipeline (end-to-end):* {icon} {fst_detail}")
    if not fst_ok:
        all_healthy = False

    lines.append("")
    lines.append("*Case law judgments:*")
    if judgment_stats:
        for status, count in sorted(judgment_stats.items()):
            lines.append(f"  {status}: {count}")
    else:
        lines.append("  _no data_")

    lines.append("")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"_Checked {timestamp}_")

    return "\n".join(lines), all_healthy


async def heartbeat(ctx: dict) -> dict:
    """arq task: check service health, keep FST alive, send Telegram heartbeat."""
    settings = get_settings()

    from app.database import async_session

    targets = _parse_targets(settings.heartbeat_targets)
    service_results = await _check_service_health(targets)
    fst_ok, fst_detail = await _keep_alive_fst()
    stats = await _get_judgment_stats(async_session)

    msg, all_healthy = _format_heartbeat(service_results, fst_ok, fst_detail, stats)

    sent = False
    if settings.telegram_bot_token and settings.telegram_chat_id:
        # Only send on failure OR every scheduled run. Use context flag to distinguish.
        alert_only = ctx.get("alert_only", False)
        if all_healthy and alert_only:
            logger.info("All healthy; alert_only=True, skipping Telegram send")
        else:
            notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
            sent = await notifier.send(msg)
    else:
        logger.info("Telegram not configured; skipping send")

    logger.info("Heartbeat: all_healthy=%s sent=%s", all_healthy, sent)
    return {"all_healthy": all_healthy, "sent": sent, "services": {k: v[0] for k, v in service_results.items()}}


async def heartbeat_alert_only(ctx: dict) -> dict:
    """Hourly alert-only check (only sends on failure)."""
    ctx = dict(ctx)
    ctx["alert_only"] = True
    return await heartbeat(ctx)


# --- Fast synthetic prober (every 2 min) -----------------------------------
# Tracks consecutive failures per target in-process. An alert fires only when
# a target fails twice in a row, avoiding pager noise from a single flaky
# request. TelegramNotifier's underlying dedup (if any) is orthogonal.

_FAST_PROBE_TARGETS_DEFAULT = (
    "rag-api=https://adil-rag-api-production.up.railway.app/health,"
    # Use the canonical user-facing host so we also catch DNS / TLS / CDN problems.
    "askadil-org=https://askadil.org/api/health,"
    # report-bridge has no public domain; rag-api proxies its /health.
    "report-bridge=https://adil-rag-api-production.up.railway.app/health/report-bridge"
)
_FAST_PROBE_FAIL_THRESHOLD = 2
_fast_probe_failures: dict[str, int] = {}


def _parse_fast_targets() -> dict[str, str]:
    """Read FAST_PROBE_TARGETS env override or fall back to the default."""
    spec = os.getenv("FAST_PROBE_TARGETS", _FAST_PROBE_TARGETS_DEFAULT)
    return _parse_targets(spec)


async def fast_probe(ctx: dict) -> dict:
    """Probe critical user-facing endpoints every 2 minutes.

    Alerts on the 2nd consecutive failure per target so a single 502 blip
    doesn't page anyone. Success clears the counter.
    """
    settings = get_settings()
    targets = _parse_fast_targets()
    results = await _check_service_health(targets)

    newly_failing: list[str] = []
    recovered: list[str] = []
    for name, (ok, detail) in results.items():
        prev = _fast_probe_failures.get(name, 0)
        if ok:
            if prev >= _FAST_PROBE_FAIL_THRESHOLD:
                recovered.append(f"{name} ({detail})")
            _fast_probe_failures[name] = 0
        else:
            _fast_probe_failures[name] = prev + 1
            if _fast_probe_failures[name] == _FAST_PROBE_FAIL_THRESHOLD:
                newly_failing.append(f"{name} — {detail}")

    if settings.telegram_bot_token and settings.telegram_chat_id and (newly_failing or recovered):
        notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
        lines = []
        if newly_failing:
            lines.append("🚨 *AskAdil fast probe — DOWN*")
            lines.extend(f"❌ {item}" for item in newly_failing)
        if recovered:
            if lines:
                lines.append("")
            lines.append("✅ *Recovered*")
            lines.extend(f"✅ {item}" for item in recovered)
        lines.append("")
        lines.append(f"_Checked {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
        await notifier.send("\n".join(lines))

    return {
        "targets": {
            k: {"ok": v[0], "detail": v[1], "streak": _fast_probe_failures.get(k, 0)} for k, v in results.items()
        },
        "alerted_down": newly_failing,
        "alerted_recovered": recovered,
    }


async def rate_limit_cleanup(ctx: dict) -> dict:
    """Remove rate-limit counter rows older than 48 hours and expired upload rows.

    Runs against the adil-rag-api Postgres database. Uses RAG_API_DATABASE_URL
    (new env var) so production can point at the backend's DB even when the
    document-uploader has its own DB for case law storage. Falls back to
    DATABASE_URL if the new var is unset (single-DB local dev).
    """
    import asyncpg

    rag_db_url = os.getenv("RAG_API_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not rag_db_url:
        logger.warning("No DB URL for rate_limit_cleanup; skipping")
        return {"deleted_counters": 0, "deleted_uploads": 0}

    conn = await asyncpg.connect(rag_db_url)
    try:
        deleted_c = await conn.fetchval(
            """
            WITH d AS (
              DELETE FROM rate_limit_counters
              WHERE bucket_start < now() - interval '48 hours'
              RETURNING 1
            )
            SELECT count(*) FROM d
            """
        )
        deleted_u = await conn.fetchval(
            """
            WITH d AS (
              DELETE FROM uploads WHERE expires_at < now() RETURNING 1
            )
            SELECT count(*) FROM d
            """
        )
    finally:
        await conn.close()

    logger.info(
        "rate_limit_cleanup: removed %s counters, %s uploads",
        deleted_c,
        deleted_u,
    )
    return {"deleted_counters": int(deleted_c or 0), "deleted_uploads": int(deleted_u or 0)}


async def _upsert_act(session: AsyncSession, parsed: ParsedAct) -> Act:
    """Upsert a ParsedAct + its Sections + Subsections into the local DB.

    Replaces the previous Sections/Subsections wholesale on re-fetch — Acts
    are amended occasionally and we want the current text, not diff history.
    """
    existing = await session.execute(
        select(Act).where(
            Act.leg_type == parsed.leg_type,
            Act.year == parsed.year,
            Act.leg_number == parsed.leg_number,
        )
    )
    act = existing.scalar_one_or_none()
    if act is None:
        act = Act(
            name=parsed.name,
            year=parsed.year,
            leg_type=parsed.leg_type,
            leg_number=parsed.leg_number,
            url=parsed.url,
            raw_xml=parsed.raw_xml,
        )
        session.add(act)
        await session.flush()
    else:
        act.name = parsed.name
        act.url = parsed.url
        act.raw_xml = parsed.raw_xml
        # cascade="all, delete-orphan" on Act.sections wipes existing rows.
        act.sections = []
        await session.flush()

    for section in parsed.sections:
        section_row = ActSection(
            act_id=act.id,
            number=section.number,
            title=section.title,
            text=section.text,
            ordering=section.ordering,
        )
        session.add(section_row)
        await session.flush()
        for sub in section.subsections:
            session.add(
                ActSubsection(
                    section_id=section_row.id,
                    number=sub.number,
                    text=sub.text,
                    ordering=sub.ordering,
                )
            )
    return act


async def fetch_acts(ctx: dict) -> dict:
    """arq task: fetch UK Acts from legislation.gov.uk, persist locally,
    and (when the rag-api ontology schema is in place) mirror into
    ``ontology_node`` so Case→Statute edges can be built downstream.

    Idempotent — re-running refreshes Sections/Subsections to the current
    legislation.gov.uk text. v1 captures only the current Act version;
    time-bounded ``StatuteVersion`` is deferred.
    """
    from app.database import async_session

    rag_db_url = os.getenv("RAG_API_DATABASE_URL")
    fetched = 0
    failed: list[str] = []
    ontology_nodes_written = 0

    async with LegislationClient() as client:
        for seed in UK_ACTS_SEED:
            try:
                parsed = await client.fetch_act(name=seed.name, act_url=seed.url)
            except Exception:
                logger.exception("fetch_acts: failed to fetch %s", seed.name)
                failed.append(seed.name)
                continue

            try:
                async with async_session() as session:
                    await _upsert_act(session, parsed)
                    await session.commit()
            except Exception:
                logger.exception("fetch_acts: failed to persist %s", seed.name)
                failed.append(seed.name)
                continue

            try:
                ontology_nodes_written += await write_act_to_ontology(rag_db_url, parsed)
            except Exception:
                # Ontology writes are best-effort — local persistence is the
                # source of truth and downstream extraction tasks can re-read.
                logger.exception("fetch_acts: ontology mirror failed for %s", seed.name)

            fetched += 1
            logger.info(
                "fetch_acts: %s — %d sections, %d subsections",
                seed.name,
                len(parsed.sections),
                sum(len(s.subsections) for s in parsed.sections),
            )

    logger.info(
        "fetch_acts complete: %d acts fetched, %d failed, %d ontology nodes",
        fetched,
        len(failed),
        ontology_nodes_written,
    )
    return {
        "fetched": fetched,
        "failed": failed,
        "ontology_nodes_written": ontology_nodes_written,
    }


async def scrape_solicitors(ctx: dict) -> dict:
    """arq task: scrape SRA register and upsert results into solicitor_firms table.

    Runs monthly (1st of each month, 04:00 UTC).
    Scrapes ~167 employment/discrimination/human-rights/mental-capacity law firms.
    Attribution: data supplied by the Solicitors Regulation Authority.
    """
    from app.database import async_session

    settings = get_settings()
    notifier = (
        TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
        if settings.telegram_bot_token and settings.telegram_chat_id
        else None
    )

    logger.info("scrape_solicitors: starting SRA register scrape")
    try:
        firms = await run_scrape(delay=0.3)
    except Exception:
        logger.exception("scrape_solicitors: scrape failed")
        if notifier:
            await notifier.send("❌ *SRA solicitor scrape FAILED* — check logs")
        return {"error": "scrape failed", "firms": 0}

    if not firms:
        logger.warning("scrape_solicitors: no firms returned")
        return {"firms": 0}

    # Upsert into Postgres
    upserted = 0
    async with async_session() as session:
        for firm in firms:
            stmt = (
                pg_insert(SolicitorFirm)
                .values(**firm)
                .on_conflict_do_update(
                    index_elements=["sra_number"],
                    set_={k: v for k, v in firm.items() if k != "sra_number"},
                )
            )
            await session.execute(stmt)
            upserted += 1
        await session.commit()

    logger.info("scrape_solicitors: upserted %d firms", upserted)
    if notifier:
        await notifier.send(
            f"✅ *SRA solicitor directory refreshed*\n" f"{upserted} firms upserted into solicitor_firms table."
        )
    return {"firms": upserted}
