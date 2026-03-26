import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.contact import ContactStatus


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str | None = None
    firm_name: str | None = None
    website: str | None = None
    metadata: dict | None = None


class ContactBulkCreate(BaseModel):
    contacts: list[ContactCreate] = Field(..., min_length=1, max_length=1000)


class ContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str | None = None
    firm_name: str | None = None
    website: str | None = None
    metadata: dict | None = None
    status: ContactStatus | None = None
    consent: bool | None = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    email: str
    phone: str | None
    firm_name: str | None
    website: str | None
    metadata: dict | None
    research_data: dict | None
    status: ContactStatus
    current_cadence_step: int
    consent: bool | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactDetailResponse(ContactResponse):
    events: list["EventResponse"] = []

    model_config = {"from_attributes": True}


# Import here to avoid circular imports
from app.schemas.event import EventResponse  # noqa: E402

ContactDetailResponse.model_rebuild()


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    limit: int
    offset: int


class BulkCreateResponse(BaseModel):
    created: int
    errors: list[dict] = []
