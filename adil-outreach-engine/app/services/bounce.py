"""Bounce handling — update contact status and cancel deferred jobs."""

import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact, ContactStatus
from app.schemas.webhook import SendGridEvent
from app.services.events import log_outreach_event

logger = logging.getLogger(__name__)


async def handle_bounce(
    db: AsyncSession,
    contact: Contact,
    event: SendGridEvent,
    redis: Redis | None = None,
) -> None:
    """Handle a bounce or dropped event from SendGrid.

    1. Update contact status to bounced
    2. Log the bounce event
    3. Cancel deferred evaluate_contact jobs (if redis available)
    """
    # 1. Update contact status to bounced
    contact.status = ContactStatus.bounced
    await db.commit()

    # 2. Log the bounce event
    await log_outreach_event(
        db,
        contact.id,
        event_type="email_bounced",
        channel="email",
        metadata={
            "reason": event.reason,
            "original_event": event.event,  # "bounce" or "dropped"
            "sg_message_id": event.sg_message_id,
        },
    )

    # 3. Cancel deferred evaluate_contact jobs
    if redis:
        cancelled = await cancel_deferred_jobs(redis, contact.id)
        if cancelled:
            logger.info(
                "Cancelled %d deferred jobs for bounced contact %s",
                cancelled,
                contact.id,
            )


async def handle_bounce_from_reply(
    db: AsyncSession,
    contact: Contact,
    redis: Redis | None = None,
) -> None:
    """Handle a bounce detected via LLM classification of a reply."""
    contact.status = ContactStatus.bounced
    await db.commit()

    await log_outreach_event(
        db,
        contact.id,
        event_type="email_bounced",
        channel="system",
        metadata={"source": "llm_classification"},
    )

    if redis:
        await cancel_deferred_jobs(redis, contact.id)


async def cancel_deferred_jobs(redis: Redis, contact_id: uuid.UUID) -> int:
    """Cancel all deferred arq jobs for a given contact.

    Scans the arq deferred job set and aborts jobs matching this contact_id.
    Returns count of cancelled jobs.
    """
    cancelled = 0
    try:
        # arq stores jobs in a sorted set; scan for matching contact_id
        # We look through the arq:queue:default:* keys for pending jobs
        keys = []
        async for key in redis.scan_iter("arq:job:*"):
            keys.append(key)

        for key in keys:
            try:
                job_data = await redis.get(key)
                if job_data and str(contact_id).encode() in job_data:
                    # Found a job referencing this contact — attempt to abort
                    await redis.delete(key)
                    cancelled += 1
                    logger.info(
                        "Cancelled deferred job %s for contact %s",
                        key,
                        contact_id,
                    )
            except Exception:
                continue  # Best effort
    except Exception:
        logger.exception("Error cancelling deferred jobs for contact %s", contact_id)

    return cancelled
