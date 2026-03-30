"""Cal.com webhook handling for booking confirmations."""

import hashlib
import hmac
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.outreach_event import EventType, OutreachEvent
from app.services.conversion import ConflictError, process_conversion

logger = logging.getLogger(__name__)


def verify_cal_signature(payload: bytes, signature: str) -> bool:
    """Verify Cal.com webhook HMAC-SHA256 signature."""
    expected = hmac.new(
        settings.cal_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def handle_cal_webhook(payload: dict, db: AsyncSession) -> None:
    """Process a Cal.com webhook event.

    Only handles BOOKING_CREATED events.
    """
    trigger_event = payload.get("triggerEvent") or payload.get("type", "")
    if trigger_event != "BOOKING_CREATED":
        logger.info("Ignoring Cal.com event type: %s", trigger_event)
        return

    # Extract contact_id from booking metadata
    # Cal.com booking URL includes ?contact={contact_id}
    contact_id = None
    metadata = payload.get("metadata") or {}
    if isinstance(metadata, dict):
        contact_id = metadata.get("contact")
    if not contact_id:
        responses = payload.get("responses") or {}
        if isinstance(responses, dict):
            contact_id = responses.get("contact")

    if not contact_id:
        logger.warning("Cal.com webhook missing contact_id in metadata/responses")
        return

    cal_booking_id = str(payload.get("bookingId") or payload.get("uid") or "")

    # Idempotency: check if we already processed this booking
    if cal_booking_id:
        result = await db.execute(
            select(OutreachEvent).where(
                OutreachEvent.event_type == EventType.booking_made,
            )
        )
        for evt in result.scalars().all():
            meta = evt.metadata_ or {}
            if meta.get("cal_booking_id") == cal_booking_id:
                logger.info("Cal.com booking %s already processed, skipping", cal_booking_id)
                return

    # Build conversion data
    attendees = payload.get("attendees") or [{}]
    first_attendee = attendees[0] if attendees else {}

    data = {
        "cal_booking_id": cal_booking_id,
        "event_type": payload.get("eventTitle") or payload.get("title"),
        "start_time": payload.get("startTime"),
        "end_time": payload.get("endTime"),
        "attendee_email": first_attendee.get("email"),
        "attendee_name": first_attendee.get("name"),
        "meeting_url": payload.get("meetingUrl"),
    }

    try:
        await process_conversion(contact_id, "booking", data, db)
    except ConflictError:
        logger.info("Contact %s already converted (Cal.com duplicate)", contact_id)
    except ValueError as e:
        logger.error("Cal.com webhook error: %s", e)
