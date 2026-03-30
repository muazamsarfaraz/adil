"""Draft preview, approval, and contact events timeline endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_api_key
from app.database import get_db
from app.models.contact import Contact, ContactStatus
from app.models.outreach_event import OutreachEvent
from app.schemas.event import EventResponse, EventTimelineResponse
from app.models.campaign import Campaign
from app.schemas.outreach import DraftApprovalRequest, DraftResponse, EmailPreviewResponse
from app.services.events import get_latest_event, log_outreach_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/outreach",
    tags=["outreach"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_contact_or_404(db: AsyncSession, contact_id: uuid.UUID) -> Contact:
    """Fetch a contact by ID or raise 404."""
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


# ---------------------------------------------------------------------------
# Draft preview and approval
# ---------------------------------------------------------------------------


@router.get("/contacts/{contact_id}/draft", response_model=DraftResponse)
async def get_draft(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Get the latest pending draft for a contact."""
    contact = await get_contact_or_404(db, contact_id)

    # Find the most recent draft_created event
    draft_event = await get_latest_event(db, contact_id, event_type="draft_created")
    if not draft_event:
        raise HTTPException(status_code=404, detail="No draft found for this contact")

    return DraftResponse(
        contact_id=contact.id,
        subject=draft_event.subject,
        body=draft_event.content,
        personalisation_hooks=(draft_event.metadata_ or {}).get("personalisation_hooks", []),
        status="pending_approval" if contact.status == ContactStatus.draft_pending else "approved",
        created_at=draft_event.created_at,
    )


@router.get("/contacts/{contact_id}/email-preview", response_model=EmailPreviewResponse)
async def get_email_preview(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Preview the EXACT email that would be sent for a contact.

    Returns subject, body (text + HTML), from, reply_to, and to fields
    based on the latest draft and campaign sender settings.
    """
    contact = await get_contact_or_404(db, contact_id)

    # Load campaign for sender info
    campaign = await db.get(Campaign, contact.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Find the most recent draft_created event
    draft_event = await get_latest_event(db, contact_id, event_type="draft_created")
    if not draft_event:
        raise HTTPException(status_code=404, detail="No draft found for this contact")

    body_text = draft_event.content or ""
    # Basic HTML wrapping of the plain text body
    escaped_body = body_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>\n")
    body_html = (
        f"<!DOCTYPE html><html><body>"
        f'<div style="font-family: Arial, sans-serif; font-size: 14px; '
        f'line-height: 1.6; color: #333;">'
        f"{escaped_body}"
        f"</div></body></html>"
    )

    return EmailPreviewResponse(
        contact_id=contact.id,
        to=contact.email,
        from_email=campaign.sender_email,
        from_name=campaign.sender_name or campaign.name,
        reply_to=campaign.reply_to,
        subject=draft_event.subject,
        body_text=body_text,
        body_html=body_html,
        draft_created_at=draft_event.created_at,
    )


@router.post("/contacts/{contact_id}/approve-draft")
async def approve_draft(
    contact_id: uuid.UUID,
    approval: DraftApprovalRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Approve a pending draft, optionally with edits, and enqueue sending."""
    contact = await get_contact_or_404(db, contact_id)

    if contact.status != ContactStatus.draft_pending:
        raise HTTPException(
            status_code=400,
            detail=f"Contact status is {contact.status}, expected draft_pending",
        )

    # Get draft event
    draft_event = await get_latest_event(db, contact_id, event_type="draft_created")
    if not draft_event:
        raise HTTPException(status_code=404, detail="No draft found for this contact")

    # Apply edits if provided
    subject = approval.edited_subject if (approval and approval.edited_subject) else draft_event.subject
    body = approval.edited_body if (approval and approval.edited_body) else draft_event.content

    # Log approval event
    await log_outreach_event(
        db,
        contact.id,
        event_type="draft_approved",
        channel="manual",
        subject=subject,
        content=body,
        metadata={
            "was_edited": bool(approval and (approval.edited_subject or approval.edited_body)),
        },
    )

    # Enqueue the actual send via arq worker
    from app.workers.settings import get_arq_pool

    contact.status = ContactStatus.ready  # send_email_task will set to emailed
    await db.commit()

    try:
        pool = await get_arq_pool()
        await pool.enqueue_job("send_email_task", str(contact.id), contact.current_cadence_step or 0)
    except Exception:
        pass  # Worker will pick it up on retry

    return {"status": "approved", "contact_id": str(contact.id)}


# ---------------------------------------------------------------------------
# Contact events timeline
# ---------------------------------------------------------------------------


@router.get("/contacts/{contact_id}/events", response_model=EventTimelineResponse)
async def get_contact_events_timeline(
    contact_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Get paginated event timeline for a contact, newest first."""
    contact = await get_contact_or_404(db, contact_id)

    query = (
        select(OutreachEvent).where(OutreachEvent.contact_id == contact_id).order_by(OutreachEvent.created_at.desc())
    )

    if event_type:
        query = query.where(OutreachEvent.event_type == event_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Get paginated results
    result = await db.execute(query.offset(offset).limit(limit))
    events = result.scalars().all()

    return EventTimelineResponse(
        contact_id=contact.id,
        contact_name=contact.name,
        contact_status=contact.status.value if isinstance(contact.status, ContactStatus) else contact.status,
        events=[
            EventResponse(
                id=e.id,
                contact_id=e.contact_id,
                event_type=e.event_type,
                channel=e.channel,
                subject=e.subject,
                content=e.content,
                metadata=e.metadata_,
                created_at=e.created_at,
            )
            for e in events
        ],
        total_events=total or 0,
    )
