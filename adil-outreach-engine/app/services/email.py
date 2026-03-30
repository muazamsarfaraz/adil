"""Email service wrapping SendGrid v6 SDK with idempotency and threading support."""

from __future__ import annotations

import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Content,
    CustomArg,
    Email,
    Header,
    Mail,
    ReplyTo,
    To,
)
from sqlalchemy import select

from app.config import settings
from app.models.outreach_event import OutreachEvent

logger = logging.getLogger(__name__)


class SendGridError(Exception):
    """Base SendGrid error."""

    pass


class SendGridTransientError(SendGridError):
    """Retryable error (5xx, rate limit 429)."""

    pass


class SendGridPermanentError(SendGridError):
    """Non-retryable error (4xx except 429)."""

    pass


class EmailService:
    """SendGrid email service with idempotency and In-Reply-To threading."""

    def __init__(self):
        self.client = SendGridAPIClient(api_key=settings.sendgrid_api_key)

    async def check_idempotency(self, db_session, idempotency_key: str) -> OutreachEvent | None:
        """Check if an email with this idempotency key was already sent."""
        stmt = select(OutreachEvent).where(
            OutreachEvent.event_type == "email_sent",
            OutreachEvent.metadata_["idempotency_key"].as_string() == idempotency_key,
        )
        result = await db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def send_email(
        self,
        *,
        to_email: str,
        from_email: str,
        from_name: str,
        subject: str,
        html_body: str,
        reply_to: str | None = None,
        initial_message_id: str | None = None,
        custom_args: dict | None = None,
        idempotency_key: str | None = None,
        db_session=None,
    ) -> dict:
        """
        Send an email via SendGrid with idempotency and threading support.

        Returns dict with status, sendgrid_message_id, etc.
        """
        # 1. Idempotency guard
        if idempotency_key and db_session:
            existing = await self.check_idempotency(db_session, idempotency_key)
            if existing:
                return {
                    "status": "already_sent",
                    "event_id": str(existing.id),
                    "message_id": existing.metadata_.get("sendgrid_message_id") if existing.metadata_ else None,
                }

        # 2. Build message
        message = Mail(
            from_email=Email(from_email, from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_body),
        )

        if reply_to:
            message.reply_to = ReplyTo(reply_to)

        # 3. Threading headers (Spec 14.7)
        if initial_message_id:
            message.header = Header("In-Reply-To", f"<{initial_message_id}>")
            message.header = Header("References", f"<{initial_message_id}>")

        # 4. Custom args for SendGrid metadata / deduplication
        if custom_args:
            for key, value in custom_args.items():
                message.custom_arg = CustomArg(key, str(value))

        # 5. Send via SendGrid
        try:
            response = self.client.send(message)
        except Exception as e:
            status_code = getattr(e, "status_code", None)
            if status_code and 400 <= status_code < 500 and status_code != 429:
                raise SendGridPermanentError(f"SendGrid {status_code}: {e}") from e
            raise SendGridTransientError(f"SendGrid error: {e}") from e

        # 6. Extract message ID from response headers
        sendgrid_message_id = response.headers.get("X-Message-Id", "")

        return {
            "status": "sent",
            "sendgrid_message_id": sendgrid_message_id,
            "status_code": response.status_code,
        }
