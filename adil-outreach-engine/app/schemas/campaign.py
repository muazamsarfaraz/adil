import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.campaign import CampaignGoal, CampaignStatus


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(..., min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    goal: CampaignGoal
    templates: dict | None = None
    cadence: list | None = None
    llm_config: dict | None = None
    research_instructions: str | None = None
    compose_instructions: str | None = None
    classify_instructions: str | None = None
    conversion_config: dict | None = None
    auto_send: bool = False
    sender_name: str | None = None
    sender_email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    reply_to: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    success_criteria: dict | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    slug: str | None = Field(None, min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    goal: CampaignGoal | None = None
    templates: dict | None = None
    cadence: list | None = None
    llm_config: dict | None = None
    research_instructions: str | None = None
    compose_instructions: str | None = None
    classify_instructions: str | None = None
    conversion_config: dict | None = None
    auto_send: bool | None = None
    sender_name: str | None = None
    sender_email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    reply_to: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    success_criteria: dict | None = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    goal: CampaignGoal
    status: CampaignStatus
    templates: dict | None
    cadence: list | None
    llm_config: dict | None
    research_instructions: str | None
    compose_instructions: str | None
    classify_instructions: str | None
    conversion_config: dict | None
    auto_send: bool
    sender_name: str | None
    sender_email: str | None
    reply_to: str | None
    success_criteria: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignWithStats(CampaignResponse):
    stats: "CampaignStats"


# Import here to avoid circular imports
from app.schemas.stats import CampaignStats  # noqa: E402

CampaignWithStats.model_rebuild()


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    limit: int
    offset: int
