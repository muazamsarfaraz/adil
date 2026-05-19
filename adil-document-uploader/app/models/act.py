from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.judgment import Base


class Act(Base):
    """A UK statute fetched from legislation.gov.uk (Acts table)."""

    __tablename__ = "acts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    # e.g. "ukpga", "asp", "nisi" — legislation.gov.uk URL segment
    leg_type: Mapped[str] = mapped_column(String(20), nullable=False)
    leg_number: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_xml: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list[ActSection]] = relationship(
        "ActSection",
        back_populates="act",
        cascade="all, delete-orphan",
        order_by="ActSection.ordering",
    )

    __table_args__ = (UniqueConstraint("leg_type", "year", "leg_number", name="uq_acts_legref"),)


class ActSection(Base):
    """A Section of an Act (e.g. Equality Act 2010 s.13)."""

    __tablename__ = "act_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    act_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("acts.id", ondelete="CASCADE"), nullable=False
    )
    # Section "number" as printed (e.g. "13", "26", "4A") — keep as text to allow letter suffixes
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    act: Mapped[Act] = relationship("Act", back_populates="sections")
    subsections: Mapped[list[ActSubsection]] = relationship(
        "ActSubsection",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="ActSubsection.ordering",
    )

    __table_args__ = (
        UniqueConstraint("act_id", "number", name="uq_act_sections_number"),
        Index("ix_act_sections_act_id", "act_id"),
    )


class ActSubsection(Base):
    """A Subsection of an Act Section (e.g. Equality Act 2010 s.13(1))."""

    __tablename__ = "act_subsections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("act_sections.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    section: Mapped[ActSection] = relationship("ActSection", back_populates="subsections")

    __table_args__ = (
        UniqueConstraint("section_id", "number", name="uq_act_subsections_number"),
        Index("ix_act_subsections_section_id", "section_id"),
    )
