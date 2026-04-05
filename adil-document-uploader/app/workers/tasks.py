from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import SEARCH_DOMAINS, SearchDomain, get_settings
from app.models.judgment import Judgment, JudgmentStatus
from app.services.gemini_uploader import GeminiUploader
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
