import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ContactStatus(str, enum.Enum):
    pending = "pending"
    researching = "researching"
    ready = "ready"
    draft_pending = "draft_pending"
    emailed = "emailed"
    replied = "replied"
    converted = "converted"
    declined = "declined"
    unresponsive = "unresponsive"
    bounced = "bounced"


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    firm_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    research_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, name="contact_status"), nullable=False, default=ContactStatus.pending
    )
    current_cadence_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow
    )

    # Relationships
    campaign = relationship("Campaign", back_populates="contacts")
    events = relationship("OutreachEvent", back_populates="contact", cascade="all, delete-orphan")
    conversion = relationship("Conversion", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    checkpoints = relationship("AgentCheckpoint", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_contacts_campaign_status", "campaign_id", "status"),)
