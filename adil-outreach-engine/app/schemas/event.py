import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.outreach_event import EventChannel, EventType


class EventResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    event_type: EventType
    channel: EventChannel
    subject: str | None
    content: str | None
    metadata: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
