"""Pydantic models for the report bridge service."""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class DOB(BaseModel):
    day: str = Field(..., min_length=1, max_length=2)
    month: str = Field(..., min_length=1, max_length=2)
    year: str = Field(..., min_length=4, max_length=4)


class SubmitRequest(BaseModel):
    """Request to submit a report to a target form."""
    target: str = Field(..., description="Target form identifier, e.g. 'police-uk'.")
    data: Dict[str, Any] = Field(..., description="Flat dict of form field values.")


class SubmitResponse(BaseModel):
    """Response from a report submission attempt."""
    success: bool
    target: str
    reference_number: Optional[str] = None
    confirmation_screenshot: Optional[str] = None
    confirmation_text: Optional[str] = None
    submitted_at: Optional[datetime] = None
    error: Optional[str] = None
    fallback_report: Optional[str] = None
    target_url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str


class TargetInfo(BaseModel):
    name: str
    url: str
    required_fields: List[str]
    optional_fields: List[str]
    coverage: str


class TargetHealthInfo(BaseModel):
    reachable: bool
    last_checked: Optional[datetime] = None
