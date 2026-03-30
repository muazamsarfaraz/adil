"""Pydantic schemas for SendGrid webhook events."""

from pydantic import BaseModel


class SendGridEvent(BaseModel):
    """A single SendGrid event webhook payload item."""

    email: str
    timestamp: int
    event: str  # delivered, open, click, bounce, dropped, etc.
    sg_message_id: str | None = None
    reason: str | None = None  # bounce reason
    url: str | None = None  # clicked URL
    useragent: str | None = None
    ip: str | None = None
    category: list[str] | None = None
    # custom_args from send — used to match contact
    contact_id: str | None = None
    campaign_id: str | None = None
