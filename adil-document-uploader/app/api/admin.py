from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_admin_key
from app.database import get_db
from app.models.judgment import Judgment
from app.schemas.judgment import FetchResponse, StatsResponse, UploadResponse
from app.workers.tasks import fetch_case_law, upload_pending

router = APIRouter(prefix="/api/v1", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(Judgment.id)))).scalar() or 0

    status_rows = await db.execute(select(Judgment.status, func.count(Judgment.id)).group_by(Judgment.status))
    by_status = {row[0].value: row[1] for row in status_rows}

    domain_rows = await db.execute(
        select(Judgment.search_domain, func.count(Judgment.id)).group_by(Judgment.search_domain)
    )
    by_domain = {row[0]: row[1] for row in domain_rows}

    court_rows = await db.execute(select(Judgment.court, func.count(Judgment.id)).group_by(Judgment.court))
    by_court = {row[0]: row[1] for row in court_rows}

    return StatsResponse(total=total, by_status=by_status, by_domain=by_domain, by_court=by_court)


@router.post("/fetch", response_model=FetchResponse)
async def trigger_fetch():
    """Manually trigger a fetch cycle (runs synchronously in request)."""
    result = await fetch_case_law(ctx={})
    return FetchResponse(
        message="Fetch cycle complete",
        new_judgments=result["new"],
        skipped_duplicates=result["skipped"],
    )


@router.post("/upload", response_model=UploadResponse)
async def trigger_upload():
    """Manually trigger upload of pending judgments."""
    result = await upload_pending(ctx={})
    return UploadResponse(
        message="Upload cycle complete",
        uploaded=result["uploaded"],
        failed=result["failed"],
    )
