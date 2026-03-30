import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator

from app.models.outreach_event import EventChannel, EventType


class EventResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    event_type: EventType | str
    channel: EventChannel | str
    subject: str | None
    content: str | None
    metadata: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _map_metadata(cls, data: Any) -> Any:
        """Map ORM metadata_ attribute to metadata for serialization.

        SQLAlchemy models use ``metadata_`` as the Python attribute to avoid
        shadowing the declarative ``metadata`` class attribute.  When Pydantic
        reads the ORM object with ``from_attributes=True`` it resolves
        ``metadata`` to the SQLAlchemy ``MetaData()`` descriptor rather than
        the column value.  This validator corrects that.
        """
        if hasattr(data, "metadata_"):
            obj_dict = {}
            for field_name in cls.model_fields:
                if field_name == "metadata":
                    obj_dict["metadata"] = data.metadata_
                else:
                    obj_dict[field_name] = getattr(data, field_name, None)
            return obj_dict
        return data


class EventTimelineResponse(BaseModel):
    """Paginated event timeline for a contact."""

    contact_id: uuid.UUID
    contact_name: str
    contact_status: str
    events: list[EventResponse]
    total_events: int
