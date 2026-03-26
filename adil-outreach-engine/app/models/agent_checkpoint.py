import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    graph_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    current_node: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow
    )

    # Relationships
    contact = relationship("Contact", back_populates="checkpoints")

    __table_args__ = (
        Index(
            "ix_agent_checkpoints_contact_active",
            "contact_id",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )
