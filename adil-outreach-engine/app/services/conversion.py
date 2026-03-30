"""Core conversion service — single entry point for signup, booking, and payment conversions."""

import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contact import Contact, ContactStatus
from app.models.conversion import Conversion, ConversionType
from app.models.outreach_event import EventChannel, EventType, OutreachEvent

logger = logging.getLogger(__name__)

# Map conversion types to the outreach event type they produce
_CONVERSION_EVENT_MAP: dict[str, EventType] = {
    "signup": EventType.signup_completed,
    "booking": EventType.booking_made,
    "payment": EventType.payment_received,
    "custom": EventType.signup_completed,  # custom goals log as signup_completed
}


async def process_conversion(
    contact_id: str,
    conversion_type: str,
    data: dict,
    db: AsyncSession,
) -> Conversion:
    """Create a conversion record, update contact status, send confirmation, fire webhook.

    This is the single entry point — signup, booking, and payment endpoints all call it.
    """
    contact_uuid = uuid.UUID(contact_id) if isinstance(contact_id, str) else contact_id

    # 1. Fetch contact and campaign
    contact = await db.get(Contact, contact_uuid)
    if not contact:
        raise ValueError(f"Contact {contact_id} not found")

    campaign = await db.get(Campaign, contact.campaign_id)
    if not campaign:
        raise ValueError(f"Campaign for contact {contact_id} not found")

    logger.info(
        "Processing conversion",
        extra={
            "contact_id": str(contact_id),
            "campaign_id": str(campaign.id),
            "conversion_type": conversion_type,
        },
    )

    # 2. Create conversion record
    conversion = Conversion(
        contact_id=contact_uuid,
        type=ConversionType(conversion_type),
        data=data,
    )
    db.add(conversion)

    # 3. Update contact status
    contact.status = ContactStatus.converted

    # 4. Log outreach event
    event_type = _CONVERSION_EVENT_MAP.get(conversion_type, EventType.signup_completed)
    event = OutreachEvent(
        contact_id=contact_uuid,
        event_type=event_type,
        channel=EventChannel.system,
        subject=f"Conversion: {conversion_type}",
        metadata_={"conversion_type": conversion_type, "data": data},
    )
    db.add(event)

    try:
        await db.commit()
        await db.refresh(conversion)
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"Contact {contact_id} already has a conversion")

    # 5. Fire confirmation email (fire-and-forget)
    conversion_config = campaign.conversion_config or {}
    if conversion_config.get("confirmation_email"):
        try:
            await send_confirmation_email(contact, campaign, conversion, db)
        except Exception:
            logger.exception("Failed to send confirmation email for contact %s", contact_id)

    # 6. Fire outbound webhook if configured (fire-and-forget via task enqueue)
    webhook_url = conversion_config.get("webhook_on_conversion")
    if webhook_url:
        try:
            # Import here to avoid circular imports; in production this would enqueue an arq task
            from app.workers.tasks import fire_conversion_webhook_sync

            await fire_conversion_webhook_sync(str(conversion.id), webhook_url, db)
        except Exception:
            logger.exception("Failed to fire conversion webhook for contact %s", contact_id)

    return conversion


async def send_confirmation_email(
    contact: Contact,
    campaign: Campaign,
    conversion: Conversion,
    db: AsyncSession,
) -> None:
    """Send a simple confirmation email via SendGrid (placeholder implementation).

    The actual SendGrid integration is assumed from Plan 1 or created as a thin wrapper.
    For now, we log the event as if the email was sent.
    """
    logger.info(
        "Sending confirmation email to %s for campaign %s",
        contact.email,
        campaign.name,
    )

    # Log outreach event for the confirmation email
    event = OutreachEvent(
        contact_id=contact.id,
        event_type=EventType.email_sent,
        channel=EventChannel.email,
        subject=f"Confirmation: {campaign.name}",
        metadata_={
            "purpose": "confirmation",
            "conversion_type": conversion.type.value,
            "campaign_name": campaign.name,
            "to": contact.email,
            "from_email": campaign.sender_email,
            "from_name": campaign.sender_name,
        },
    )
    db.add(event)
    await db.commit()


class ConflictError(Exception):
    """Raised when a conversion already exists for a contact."""

    pass
