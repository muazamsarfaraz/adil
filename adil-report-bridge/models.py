"""Pydantic models for the report bridge service."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DOB(BaseModel):
    day: str = Field(..., min_length=1, max_length=2)
    month: str = Field(..., min_length=1, max_length=2)
    year: str = Field(..., min_length=4, max_length=4)


class SubmitRequest(BaseModel):
    """Request to submit a report to a target form."""

    target: str = Field(..., description="Target form identifier, e.g. 'police-uk'.")
    data: dict[str, Any] = Field(..., description="Flat dict of form field values.")


class SubmitResponse(BaseModel):
    """Response from a report submission attempt."""

    success: bool
    target: str
    reference_number: str | None = None
    confirmation_screenshot: str | None = None
    confirmation_text: str | None = None
    submitted_at: datetime | None = None
    error: str | None = None
    fallback_report: str | None = None
    target_url: str | None = None
    # Dry-run safety: when BRIDGE_DRY_RUN=true the agent walks the form but
    # never clicks Submit. The client should NOT treat dry_run=true as a
    # filed report.
    dry_run: bool = False
    message: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str


class TargetInfo(BaseModel):
    name: str
    url: str
    required_fields: list[str]
    optional_fields: list[str]
    coverage: str


class TargetHealthInfo(BaseModel):
    reachable: bool
    last_checked: datetime | None = None
