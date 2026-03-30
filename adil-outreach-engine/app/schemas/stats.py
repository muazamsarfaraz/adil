import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class CampaignStats(BaseModel):
    """Funnel metrics for a campaign.

    Counts represent the number of contacts in each status stage.
    Rates are floats between 0.0 and 1.0 (rounded to 4 decimal places).
    """

    campaign_id: uuid.UUID
    campaign_name: str
    campaign_status: str
    total_contacts: int = 0
    pending: int = 0
    researching: int = 0
    ready: int = 0
    draft_pending: int = 0
    emailed: int = 0
    opened: int = 0
    replied: int = 0
    converted: int = 0
    declined: int = 0
    unresponsive: int = 0
    bounced: int = 0
    open_rate: float = 0.0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0
    last_activity: datetime | None = None  # most recent outreach_event timestamp

    model_config = ConfigDict(from_attributes=True)

    @field_validator("open_rate", "reply_rate", "conversion_rate")
    @classmethod
    def rate_must_be_between_zero_and_one(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("Rate must be between 0.0 and 1.0")
        return round(v, 4)

    @field_validator(
        "total_contacts",
        "pending",
        "researching",
        "ready",
        "draft_pending",
        "emailed",
        "opened",
        "replied",
        "converted",
        "declined",
        "unresponsive",
        "bounced",
    )
    @classmethod
    def count_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Count must be >= 0")
        return v
