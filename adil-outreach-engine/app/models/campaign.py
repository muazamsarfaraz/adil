import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CampaignGoal(str, enum.Enum):
    signup = "signup"
    booking = "booking"
    payment = "payment"
    custom = "custom"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    goal: Mapped[CampaignGoal] = mapped_column(Enum(CampaignGoal, name="campaign_goal"), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"), nullable=False, default=CampaignStatus.draft
    )
    templates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cadence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    llm_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    research_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    compose_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    classify_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auto_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sender_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow
    )

    # Relationships
    contacts = relationship("Contact", back_populates="campaign", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """Serialize to dict for use in OutreachState."""
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "goal": self.goal.value if isinstance(self.goal, CampaignGoal) else self.goal,
            "status": self.status.value if isinstance(self.status, CampaignStatus) else self.status,
            "templates": self.templates,
            "cadence": self.cadence,
            "llm_config": self.llm_config,
            "research_instructions": self.research_instructions,
            "compose_instructions": self.compose_instructions,
            "classify_instructions": self.classify_instructions,
            "conversion_config": self.conversion_config,
            "auto_send": self.auto_send,
            "dry_run": self.dry_run,
            "sender_name": self.sender_name,
            "sender_email": self.sender_email,
            "reply_to": self.reply_to,
            "success_criteria": self.success_criteria,
        }
