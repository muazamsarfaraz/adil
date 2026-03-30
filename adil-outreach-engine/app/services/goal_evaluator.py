"""Custom goal type evaluation — matches events against campaign success_criteria."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignGoal
from app.models.contact import Contact
from app.models.outreach_event import EventType, OutreachEvent
from app.services.conversion import ConflictError, process_conversion

logger = logging.getLogger(__name__)


async def evaluate_custom_goal(
    contact_id: str,
    event_type: str,
    event_metadata: dict,
    db: AsyncSession,
) -> bool:
    """Evaluate whether an event matches a campaign's custom success_criteria.

    Returns True if the contact was converted, False otherwise.
    """
    import uuid

    contact_uuid = uuid.UUID(contact_id) if isinstance(contact_id, str) else contact_id
    contact = await db.get(Contact, contact_uuid)
    if not contact:
        return False

    campaign = await db.get(Campaign, contact.campaign_id)
    if not campaign:
        return False

    # Only evaluate for custom goal campaigns
    if campaign.goal != CampaignGoal.custom:
        return False

    success_criteria = campaign.success_criteria
    if not success_criteria:
        return False

    # Match rules:
    # 1. success_criteria.event_type must match the incoming event_type
    # 2. All other keys are matched against event_metadata (AND logic)
    criteria_event_type = success_criteria.get("event_type")
    if criteria_event_type != event_type:
        return False

    # Check all other criteria keys against event_metadata
    for key, expected_value in success_criteria.items():
        if key == "event_type":
            continue
        actual_value = event_metadata.get(key)
        if actual_value != expected_value:
            return False

    # All criteria matched — trigger conversion
    logger.info(
        "Custom goal matched for contact %s: criteria=%s",
        contact_id,
        success_criteria,
    )

    try:
        await process_conversion(
            str(contact_id),
            "custom",
            {
                "matched_criteria": success_criteria,
                "trigger_event": event_type,
                "trigger_metadata": event_metadata,
            },
            db,
        )
        return True
    except ConflictError:
        logger.info("Contact %s already converted (custom goal duplicate)", contact_id)
        return False


async def log_event_and_evaluate(
    contact_id: str,
    event_type_str: str,
    event_metadata: dict,
    db: AsyncSession,
    channel: str = "system",
    subject: str | None = None,
    content: str | None = None,
) -> OutreachEvent:
    """Create an outreach event and check if it triggers a custom goal conversion.

    This is a convenience wrapper that combines event logging with goal evaluation.
    """
    import uuid

    from app.models.outreach_event import EventChannel as EC

    contact_uuid = uuid.UUID(contact_id) if isinstance(contact_id, str) else contact_id

    channel_enum = EC(channel) if isinstance(channel, str) else channel
    event_type_enum = EventType(event_type_str)

    event = OutreachEvent(
        contact_id=contact_uuid,
        event_type=event_type_enum,
        channel=channel_enum,
        subject=subject,
        content=content,
        metadata_=event_metadata,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # Evaluate custom goal
    await evaluate_custom_goal(contact_id, event_type_str, event_metadata, db)

    return event
