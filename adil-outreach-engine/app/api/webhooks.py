"""SendGrid webhook endpoints — event tracking and inbound parse.

Separate from conversion_webhooks.py which handles Stripe/Cal.com.
"""

import logging
import re
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.webhook_verify import require_sendgrid_inbound_token, require_sendgrid_signature
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact, ContactStatus
from app.schemas.webhook import SendGridEvent
from app.services.bounce import handle_bounce
from app.services.events import log_outreach_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/outreach/webhooks",
    tags=["sendgrid-webhooks"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def match_event_to_contact(
    db: AsyncSession,
    event: SendGridEvent,
) -> Contact | None:
    """Match a SendGrid event to a contact record.

    Primary match: contact_id from custom_args (set during send_email).
    Fallback: match by email + campaign_id.
    """
    # Primary: direct contact_id lookup
    if event.contact_id:
        try:
            contact = await db.get(Contact, uuid.UUID(event.contact_id))
            if contact:
                return contact
        except (ValueError, TypeError):
            pass

    # Fallback: match by email + campaign
    stmt = select(Contact).join(Campaign, Contact.campaign_id == Campaign.id)

    if event.campaign_id:
        try:
            stmt = stmt.where(Campaign.id == uuid.UUID(event.campaign_id))
        except (ValueError, TypeError):
            pass

    stmt = stmt.where(Contact.email == event.email).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def extract_email_from_field(from_field: str) -> str:
    """Extract email address from 'Name <email@example.com>' format."""
    match = re.search(r"<([^>]+)>", from_field)
    if match:
        return match.group(1).lower()
    return from_field.strip().lower()


async def match_inbound_to_contact(
    db: AsyncSession,
    sender_email: str,
) -> Contact | None:
    """Match an inbound reply to a contact by sender email.

    Returns the most recently updated contact if there are multiple matches.
    Searches contacts in active campaigns with relevant statuses.
    """
    result = await db.execute(
        select(Contact)
        .join(Campaign, Contact.campaign_id == Campaign.id)
        .where(Campaign.status == CampaignStatus.active)
        .where(
            Contact.status.in_(
                [
                    ContactStatus.emailed,
                    ContactStatus.replied,
                    ContactStatus.unresponsive,
                    ContactStatus.declined,
                ]
            )
        )
        .order_by(Contact.updated_at.desc())
    )
    contacts = result.scalars().all()

    # Compare emails (contacts may store encrypted email, or plain text in tests)
    for contact in contacts:
        contact_email = contact.email
        if contact_email.lower() == sender_email.lower():
            return contact

    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/sendgrid/events",
    dependencies=[Depends(require_sendgrid_signature)],
)
async def handle_sendgrid_events(
    request: Request,
    events: list[SendGridEvent],
    db: AsyncSession = Depends(get_db),
):
    """Handle SendGrid event webhook (delivered, open, click, bounce, dropped)."""
    for event in events:
        contact = await match_event_to_contact(db, event)
        if not contact:
            logger.warning("No contact found for SendGrid event: %s", event.email)
            continue

        match event.event:
            case "delivered":
                await log_outreach_event(
                    db,
                    contact.id,
                    "email_delivered",
                    metadata={"sg_message_id": event.sg_message_id},
                )

            case "open":
                await log_outreach_event(
                    db,
                    contact.id,
                    "email_opened",
                    metadata={
                        "ip": event.ip,
                        "useragent": event.useragent,
                    },
                )

            case "click":
                await log_outreach_event(
                    db,
                    contact.id,
                    "email_clicked",
                    metadata={"url": event.url},
                )

            case "bounce" | "dropped":
                await handle_bounce(db, contact, event)

    return {"status": "ok"}


@router.post(
    "/sendgrid/inbound",
    dependencies=[Depends(require_sendgrid_inbound_token)],
)
async def handle_sendgrid_inbound(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle SendGrid inbound parse webhook (reply capture).

    SendGrid Inbound Parse sends multipart/form-data and does NOT offer
    ECDSA-style signing (that is Event Webhook only). We instead require a
    shared bearer token sent via `?token=` query param (configured in the
    Parse settings) or `Authorization: Bearer ...` header. Validated by
    `require_sendgrid_inbound_token` — constant-time compare; rejects with
    403 on mismatch.
    """
    form = await request.form()

    sender_email = extract_email_from_field(form.get("from", ""))
    to_email = form.get("to", "")
    subject = form.get("subject", "")
    text_body = form.get("text", "")
    html_body = form.get("html", "")

    # Match sender to a contact
    contact = await match_inbound_to_contact(db, sender_email)
    if not contact:
        logger.warning("Inbound email from unknown sender: %s", sender_email)
        return {"status": "ignored", "reason": "unknown_sender"}

    # Log reply_received event
    await log_outreach_event(
        db,
        contact.id,
        event_type="reply_received",
        channel="email",
        subject=subject,
        content=text_body or html_body,
        metadata={"sender": sender_email, "to": to_email},
    )

    # Update contact status to replied (unless already converted)
    if contact.status not in (ContactStatus.converted,):
        contact.status = ContactStatus.replied
        await db.commit()

    return {"status": "ok", "contact_id": str(contact.id)}
