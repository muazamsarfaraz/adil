from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JudgmentStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    SKIPPED = "skipped"
    FAILED = "failed"


class OgragStatus(str, enum.Enum):
    """OG-RAG ontology extraction state per judgment.

    Independent of ``JudgmentStatus`` (which tracks the FST upload pipeline) —
    a judgment can be UPLOADED in FST and still be PENDING in OG-RAG, or vice
    versa. The backfill task drives this state machine.
    """

    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EXTRACTION_FAILED = "extraction_failed"


class Judgment(Base):
    __tablename__ = "judgments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    neutral_citation: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    tna_uri: Mapped[str] = mapped_column(String(200), nullable=False)
    tna_url: Mapped[str] = mapped_column(String(500), nullable=False)
    court: Mapped[str] = mapped_column(String(50), nullable=False)
    case_name: Mapped[str] = mapped_column(String(500), nullable=False)
    judgment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    search_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    search_query: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_xml: Mapped[str] = mapped_column(Text, nullable=False)
    clean_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JudgmentStatus] = mapped_column(
        Enum(JudgmentStatus, native_enum=False), nullable=False, default=JudgmentStatus.PENDING
    )
    # OG-RAG ontology extraction state — stored as plain string (not enum) so
    # Postgres doesn't gain a server-side ENUM type that's expensive to extend
    # later. App code uses ``OgragStatus`` for the canonical values.
    ograg_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OgragStatus.PENDING.value, server_default=OgragStatus.PENDING.value
    )
    gemini_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_judgments_status", "status"),
        Index("ix_judgments_search_domain", "search_domain"),
        Index("ix_judgments_court", "court"),
        Index("ix_judgments_ograg_status", "ograg_status"),
    )


class ExtractionSpend(Base):
    """One row per (judgment, pass) execution recording USD cost.

    Aggregated by the backfill kill-switch and queried by Op dashboards.
    ``judgment_id`` is nullable so the orchestrator can record process-level
    spend rows (e.g. a startup probe) without a judgment FK.
    """

    __tablename__ = "extraction_spend_usd"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    judgment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pass_name: Mapped[str] = mapped_column(String(32), nullable=False)
    usd_cost: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_extraction_spend_judgment_id", "judgment_id"),
        Index("ix_extraction_spend_created_at", "created_at"),
    )
