import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EventType(str, enum.Enum):
    email_sent = "email_sent"
    email_opened = "email_opened"
    email_clicked = "email_clicked"
    email_failed = "email_failed"
    reply_received = "reply_received"
    reply_classified = "reply_classified"
    follow_up_sent = "follow_up_sent"
    draft_created = "draft_created"
    draft_approved = "draft_approved"
    research_completed = "research_completed"
    research_failed = "research_failed"
    compose_failed = "compose_failed"
    evaluate_result = "evaluate_result"
    marked_unresponsive = "marked_unresponsive"
    signup_completed = "signup_completed"
    booking_made = "booking_made"
    payment_received = "payment_received"
    webhook_sent = "webhook_sent"
    webhook_failed = "webhook_failed"
    manually_updated = "manually_updated"
    email_delivered = "email_delivered"
    email_bounced = "email_bounced"
    reopened = "reopened"
    email_dry_run = "email_dry_run"


class EventChannel(str, enum.Enum):
    email = "email"
    webhook = "webhook"
    manual = "manual"
    system = "system"


class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"), nullable=False)
    channel: Mapped[EventChannel] = mapped_column(Enum(EventChannel, name="event_channel"), nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Relationships
    contact = relationship("Contact", back_populates="events")

    __table_args__ = (Index("ix_outreach_events_contact_created", "contact_id", "created_at"),)
