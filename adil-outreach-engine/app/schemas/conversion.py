import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.conversion import ConversionType


class ConversionResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    type: ConversionType
    data: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
