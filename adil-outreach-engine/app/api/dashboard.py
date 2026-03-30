import csv
import io
import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_api_key
from app.config import settings
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact, ContactStatus
from app.models.outreach_event import EventType, OutreachEvent
from app.schemas.stats import CampaignStats

router = APIRouter(prefix="/api/v1/outreach", tags=["dashboard"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    checks = {}

    # Check PostgreSQL
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"

    overall_status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall_status,
        "version": settings.app_version,
        "service": settings.app_name,
        "checks": checks,
    }


@router.get(
    "/campaigns/{campaign_id}/stats",
    response_model=CampaignStats,
    dependencies=[Depends(require_api_key)],
)
async def get_campaign_stats(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return funnel metrics for a campaign by aggregating contact statuses and outreach events."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Count contacts grouped by status
    result = await db.execute(
        select(Contact.status, func.count(Contact.id))
        .where(Contact.campaign_id == campaign_id)
        .group_by(Contact.status)
    )
    status_counts = dict(result.all())
    total = sum(status_counts.values()) if status_counts else 0

    # Count contacts with at least one email_opened event
    open_count_result = await db.execute(
        select(func.count(func.distinct(OutreachEvent.contact_id)))
        .join(Contact, OutreachEvent.contact_id == Contact.id)
        .where(Contact.campaign_id == campaign_id)
        .where(OutreachEvent.event_type == EventType.email_opened)
    )
    open_count = open_count_result.scalar() or 0

    # Last activity timestamp
    last_activity_result = await db.execute(
        select(func.max(OutreachEvent.created_at))
        .join(Contact, OutreachEvent.contact_id == Contact.id)
        .where(Contact.campaign_id == campaign_id)
    )
    last_activity = last_activity_result.scalar()

    emailed = status_counts.get(ContactStatus.emailed, 0)
    replied = status_counts.get(ContactStatus.replied, 0)
    converted = status_counts.get(ContactStatus.converted, 0)

    # Denominator for open/reply rates: contacts that have been emailed or beyond
    sent_total = (
        emailed
        + replied
        + converted
        + status_counts.get(ContactStatus.declined, 0)
        + status_counts.get(ContactStatus.unresponsive, 0)
    )

    return CampaignStats(
        campaign_id=campaign_id,
        campaign_name=campaign.name,
        campaign_status=campaign.status.value,
        total_contacts=total,
        pending=status_counts.get(ContactStatus.pending, 0),
        researching=status_counts.get(ContactStatus.researching, 0),
        ready=status_counts.get(ContactStatus.ready, 0),
        draft_pending=status_counts.get(ContactStatus.draft_pending, 0),
        emailed=emailed,
        opened=open_count,
        replied=replied,
        converted=converted,
        declined=status_counts.get(ContactStatus.declined, 0),
        unresponsive=status_counts.get(ContactStatus.unresponsive, 0),
        bounced=status_counts.get(ContactStatus.bounced, 0),
        open_rate=round(open_count / sent_total, 4) if sent_total > 0 else 0.0,
        reply_rate=round(replied / sent_total, 4) if sent_total > 0 else 0.0,
        conversion_rate=round(converted / total, 4) if total > 0 else 0.0,
        last_activity=last_activity,
    )


@router.get(
    "/campaigns/{campaign_id}/export",
    dependencies=[Depends(require_api_key)],
)
async def export_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Export all contacts for a campaign as a CSV download."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Query contacts with their latest event and event count
    # Subquery for latest event per contact
    latest_event_sq = (
        select(
            OutreachEvent.contact_id,
            func.max(OutreachEvent.created_at).label("last_event_date"),
        )
        .group_by(OutreachEvent.contact_id)
        .subquery()
    )

    # Subquery for event count per contact
    event_count_sq = (
        select(
            OutreachEvent.contact_id,
            func.count(OutreachEvent.id).label("total_events"),
        )
        .group_by(OutreachEvent.contact_id)
        .subquery()
    )

    # Main query joining contacts with event subqueries
    query = (
        select(
            Contact,
            latest_event_sq.c.last_event_date,
            event_count_sq.c.total_events,
        )
        .outerjoin(latest_event_sq, Contact.id == latest_event_sq.c.contact_id)
        .outerjoin(event_count_sq, Contact.id == event_count_sq.c.contact_id)
        .where(Contact.campaign_id == campaign_id)
        .order_by(Contact.created_at)
    )

    result = await db.execute(query)
    rows = result.all()

    # For each row that has a last_event_date, fetch the event type
    # Build a dict of contact_id -> last event type
    last_event_types: dict[uuid.UUID, str] = {}
    contact_ids_with_events = [row[0].id for row in rows if row[1] is not None]
    if contact_ids_with_events:
        # Get the latest event type for each contact
        for contact_id in contact_ids_with_events:
            evt_result = await db.execute(
                select(OutreachEvent.event_type)
                .where(OutreachEvent.contact_id == contact_id)
                .order_by(OutreachEvent.created_at.desc())
                .limit(1)
            )
            evt_type = evt_result.scalar()
            if evt_type:
                last_event_types[contact_id] = evt_type.value if hasattr(evt_type, "value") else str(evt_type)

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "contact_id",
        "name",
        "email",
        "firm_name",
        "phone",
        "website",
        "status",
        "metadata",
        "research_data",
        "last_event_type",
        "last_event_date",
        "total_events",
        "created_at",
        "updated_at",
    ]
    writer.writerow(headers)

    for contact, last_event_date, total_events in rows:
        writer.writerow(
            [
                str(contact.id),
                contact.name,
                contact.email,
                contact.firm_name or "",
                contact.phone or "",
                contact.website or "",
                contact.status.value if hasattr(contact.status, "value") else str(contact.status),
                json.dumps(contact.metadata_) if contact.metadata_ else "",
                json.dumps(contact.research_data) if contact.research_data else "",
                last_event_types.get(contact.id, ""),
                last_event_date.isoformat() if last_event_date else "",
                total_events or 0,
                contact.created_at.isoformat() if contact.created_at else "",
                contact.updated_at.isoformat() if contact.updated_at else "",
            ]
        )

    output.seek(0)
    export_date = date.today().isoformat()
    filename = f"campaign-{campaign.slug}-export-{export_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
