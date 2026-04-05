from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.judgment import JudgmentStatus


class JudgmentResponse(BaseModel):
    id: uuid.UUID
    neutral_citation: str
    tna_uri: str
    tna_url: str
    court: str
    case_name: str
    judgment_date: date | None
    search_domain: str
    status: JudgmentStatus
    gemini_file_id: str | None
    error_message: str | None
    fetched_at: datetime
    uploaded_at: datetime | None

    model_config = {"from_attributes": True}


class JudgmentDetail(JudgmentResponse):
    """Full detail including clean_text (excludes raw_xml for payload size)."""

    clean_text: str
    search_query: str
    created_at: datetime
    updated_at: datetime


class JudgmentListResponse(BaseModel):
    items: list[JudgmentResponse]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_domain: dict[str, int]
    by_court: dict[str, int]


class FetchResponse(BaseModel):
    message: str
    new_judgments: int
    skipped_duplicates: int


class UploadResponse(BaseModel):
    message: str
    uploaded: int
    failed: int
