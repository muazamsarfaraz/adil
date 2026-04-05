from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JudgmentStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    SKIPPED = "skipped"
    FAILED = "failed"


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
    )
