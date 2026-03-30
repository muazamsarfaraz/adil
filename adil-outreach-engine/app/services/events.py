"""Shared helper for logging outreach events."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outreach_event import EventChannel, EventType, OutreachEvent


async def log_outreach_event(
    db: AsyncSession,
    contact_id: uuid.UUID,
    event_type: str | EventType,
    channel: str | EventChannel = "email",
    subject: str | None = None,
    content: str | None = None,
    metadata: dict | None = None,
) -> OutreachEvent:
    """Create and persist an OutreachEvent record."""
    # Coerce strings to enums for SQLAlchemy enum columns
    if isinstance(event_type, str):
        event_type = EventType(event_type)
    if isinstance(channel, str):
        channel = EventChannel(channel)

    event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=contact_id,
        event_type=event_type,
        channel=channel,
        subject=subject,
        content=content,
        metadata_=metadata or {},
        created_at=datetime.utcnow(),
    )
    db.add(event)
    await db.commit()
    return event


async def get_latest_event(
    db: AsyncSession,
    contact_id: uuid.UUID | str,
    event_type: str | EventType,
) -> OutreachEvent | None:
    """Get the most recent event of a given type for a contact."""
    cid = uuid.UUID(str(contact_id)) if isinstance(contact_id, str) else contact_id
    if isinstance(event_type, str):
        event_type = EventType(event_type)
    stmt = (
        select(OutreachEvent)
        .where(
            OutreachEvent.contact_id == cid,
            OutreachEvent.event_type == event_type,
        )
        .order_by(OutreachEvent.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_contact_events(
    db: AsyncSession,
    contact_id: uuid.UUID | str,
) -> list[OutreachEvent]:
    """Get all outreach events for a contact, newest first."""
    cid = uuid.UUID(str(contact_id)) if isinstance(contact_id, str) else contact_id
    stmt = select(OutreachEvent).where(OutreachEvent.contact_id == cid).order_by(OutreachEvent.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())
