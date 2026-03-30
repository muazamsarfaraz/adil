"""Pydantic schemas for draft preview and approval endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class DraftResponse(BaseModel):
    """Response schema for draft preview."""

    contact_id: uuid.UUID
    subject: str | None
    body: str | None
    personalisation_hooks: list[str]
    status: str  # "pending_approval" or "approved"
    created_at: datetime


class DraftApprovalRequest(BaseModel):
    """Request schema for draft approval with optional edits."""

    edited_subject: str | None = None
    edited_body: str | None = None


class EmailPreviewResponse(BaseModel):
    """Response schema for email preview — shows EXACT email that would be sent."""

    contact_id: uuid.UUID
    to: str
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    subject: str | None
    body_text: str | None
    body_html: str | None
    draft_created_at: datetime
