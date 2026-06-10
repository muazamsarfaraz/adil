"""SponsorshipInterest — surfaces a contact's affirmative answer to Wave-1 Q2.

The classifier (see app/agents/nodes/classify.py) returns a boolean
`sponsorship_interest` flag alongside the main category. When True, the
classify_reply worker inserts a row here. Idempotent on
(contact_id, raw_reply_event_id) so re-processing the same reply event
does not duplicate.

A row in this table is a signal that the operator should follow up with
sponsorship/donation details — it does NOT imply a payment intent or
commitment, only that the contact has indicated willingness.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SponsorshipInterestStatus(str, enum.Enum):
    """Lifecycle of a sponsorship lead.

    new → contacted (operator emailed back) → sponsoring (donation confirmed)
                                            ↘ declined (changed mind / didn't follow through)
    """

    new = "new"
    contacted = "contacted"
    sponsoring = "sponsoring"
    declined = "declined"


class SponsorshipInterest(Base):
    __tablename__ = "sponsorship_interests"

    __table_args__ = (
        # Idempotency: re-running classify_reply on the same reply event
        # must not create a duplicate row.
        UniqueConstraint("contact_id", "raw_reply_event_id", name="uq_sponsorship_contact_reply"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The reply_received event that triggered detection. Allows audit / replay.
    raw_reply_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outreach_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[SponsorshipInterestStatus] = mapped_column(
        Enum(SponsorshipInterestStatus, name="sponsorship_interest_status"),
        nullable=False,
        server_default=SponsorshipInterestStatus.new.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    contact = relationship("Contact")
