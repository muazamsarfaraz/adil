from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_admin_key
from app.database import get_db
from app.models.judgment import Judgment
from app.schemas.judgment import StatsResponse

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
