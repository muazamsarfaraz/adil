from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_admin_key
from app.database import get_db
from app.models.judgment import Judgment, JudgmentStatus
from app.schemas.judgment import JudgmentDetail, JudgmentListResponse, JudgmentResponse

router = APIRouter(prefix="/api/v1/judgments", tags=["judgments"], dependencies=[Depends(require_admin_key)])


@router.get("", response_model=JudgmentListResponse)
async def list_judgments(
    status: JudgmentStatus | None = None,
    domain: str | None = None,
    court: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Judgment)
    count_query = select(func.count(Judgment.id))

    if status:
        query = query.where(Judgment.status == status)
        count_query = count_query.where(Judgment.status == status)
    if domain:
        query = query.where(Judgment.search_domain == domain)
        count_query = count_query.where(Judgment.search_domain == domain)
    if court:
        query = query.where(Judgment.court == court)
        count_query = count_query.where(Judgment.court == court)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Judgment.fetched_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [JudgmentResponse.model_validate(j) for j in result.scalars().all()]

    return JudgmentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{judgment_id}", response_model=JudgmentDetail)
async def get_judgment(judgment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Judgment).where(Judgment.id == judgment_id))
    judgment = result.scalar_one_or_none()
    if not judgment:
        raise HTTPException(status_code=404, detail="Judgment not found")
    return JudgmentDetail.model_validate(judgment)
