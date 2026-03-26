import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversionType(str, enum.Enum):
    signup = "signup"
    booking = "booking"
    payment = "payment"


class Conversion(Base):
    __tablename__ = "conversions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    type: Mapped[ConversionType] = mapped_column(Enum(ConversionType, name="conversion_type"), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Relationships
    contact = relationship("Contact", back_populates="conversion")
