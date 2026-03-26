import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_api_key
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact, ContactStatus
from app.models.outreach_event import EventType, OutreachEvent
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdate,
    CampaignWithStats,
)
from app.schemas.stats import CampaignStats

router = APIRouter(prefix="/api/v1/outreach/campaigns", tags=["campaigns"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(payload: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(**payload.model_dump())
    db.add(campaign)
    try:
        await db.commit()
        await db.refresh(campaign)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Campaign with slug '{payload.slug}' already exists")
    return campaign


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    status: CampaignStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign)
    count_query = select(func.count(Campaign.id))

    if status:
        query = query.where(Campaign.status == status)
        count_query = count_query.where(Campaign.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Campaign.created_at.desc()).limit(limit).offset(offset))
    campaigns = result.scalars().all()

    return CampaignListResponse(items=campaigns, total=total, limit=limit, offset=offset)


@router.get("/{campaign_id}", response_model=CampaignWithStats)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    stats = await _compute_campaign_stats(campaign_id, db)

    campaign_data = CampaignResponse.model_validate(campaign).model_dump()
    campaign_data["stats"] = stats
    return CampaignWithStats(**campaign_data)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(campaign_id: uuid.UUID, payload: CampaignUpdate, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    try:
        await db.commit()
        await db.refresh(campaign)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Campaign with slug '{payload.slug}' already exists")

    return campaign


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    await db.execute(delete(Campaign).where(Campaign.id == campaign_id))
    await db.commit()


@router.post("/{campaign_id}/launch", response_model=CampaignResponse)
async def launch_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status == CampaignStatus.active:
        raise HTTPException(status_code=409, detail="Campaign is already active")
    if campaign.status not in (CampaignStatus.draft, CampaignStatus.paused):
        raise HTTPException(status_code=409, detail=f"Cannot launch campaign with status '{campaign.status.value}'")

    campaign.status = CampaignStatus.active
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != CampaignStatus.active:
        raise HTTPException(status_code=409, detail="Can only pause an active campaign")

    campaign.status = CampaignStatus.paused
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def _compute_campaign_stats(campaign_id: uuid.UUID, db: AsyncSession) -> CampaignStats:
    """Compute aggregate stats for a campaign by counting contact statuses."""
    result = await db.execute(
        select(Contact.status, func.count(Contact.id))
        .where(Contact.campaign_id == campaign_id)
        .group_by(Contact.status)
    )
    status_counts = dict(result.all())

    total = sum(status_counts.values()) if status_counts else 0

    # Count opens from outreach_events
    open_count_result = await db.execute(
        select(func.count(func.distinct(OutreachEvent.contact_id)))
        .join(Contact, OutreachEvent.contact_id == Contact.id)
        .where(Contact.campaign_id == campaign_id)
        .where(OutreachEvent.event_type == EventType.email_opened)
    )
    open_count = open_count_result.scalar() or 0

    emailed = status_counts.get(ContactStatus.emailed, 0)
    replied = status_counts.get(ContactStatus.replied, 0)
    converted = status_counts.get(ContactStatus.converted, 0)

    # Denominator for rates: contacts that have been emailed or beyond
    sent_total = (
        emailed
        + replied
        + converted
        + status_counts.get(ContactStatus.declined, 0)
        + status_counts.get(ContactStatus.unresponsive, 0)
    )

    return CampaignStats(
        total_contacts=total,
        pending=status_counts.get(ContactStatus.pending, 0),
        researching=status_counts.get(ContactStatus.researching, 0),
        ready=status_counts.get(ContactStatus.ready, 0),
        draft_pending=status_counts.get(ContactStatus.draft_pending, 0),
        emailed=emailed,
        replied=replied,
        converted=converted,
        declined=status_counts.get(ContactStatus.declined, 0),
        unresponsive=status_counts.get(ContactStatus.unresponsive, 0),
        bounced=status_counts.get(ContactStatus.bounced, 0),
        open_rate=round(open_count / sent_total, 2) if sent_total > 0 else 0.0,
        reply_rate=round(replied / sent_total, 2) if sent_total > 0 else 0.0,
        conversion_rate=round(converted / sent_total, 2) if sent_total > 0 else 0.0,
    )
