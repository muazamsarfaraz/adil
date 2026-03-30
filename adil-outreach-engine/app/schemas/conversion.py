import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.conversion import ConversionType


class ConversionResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    type: ConversionType
    data: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Signup schemas ---


class SignupFieldConfig(BaseModel):
    name: str
    type: str  # "text", "boolean", "multi_select", "select"
    required: bool
    options: list[str] | None = None  # for select/multi_select


class SignupFieldWithValue(SignupFieldConfig):
    value: Any | None = None  # pre-populated from contact.metadata


class SignupFormResponse(BaseModel):
    campaign_name: str
    campaign_slug: str
    fields: list[SignupFieldWithValue]
    contact_name: str | None = None  # for personalising the form


class SignupSubmission(BaseModel):
    ref: str | None = None  # contact UUID from email link
    # remaining fields are dynamic — use model_extra
    model_config = ConfigDict(extra="allow")


class ConversionConfirmation(BaseModel):
    id: uuid.UUID
    type: str
    contact_id: uuid.UUID
    message: str
    created_at: datetime


# --- Payment schemas ---


class PaymentInitResponse(BaseModel):
    checkout_url: str
    message: str = "Redirecting to payment..."


# --- Booking schemas ---


class BookingInitResponse(BaseModel):
    booking_url: str
    message: str = "Redirecting to booking..."
