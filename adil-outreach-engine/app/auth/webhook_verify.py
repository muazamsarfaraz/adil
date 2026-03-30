"""SendGrid webhook signature verification (ECDSA)."""

import logging

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_sendgrid_signature(request: Request) -> bool:
    """Verify SendGrid event webhook signature (ECDSA).

    Uses the X-Twilio-Email-Event-Webhook-Signature and
    X-Twilio-Email-Event-Webhook-Timestamp headers with ECDSA verification.
    """
    if not settings.sendgrid_webhook_verify_enabled:
        return True

    try:
        from sendgrid.helpers.eventwebhook import EventWebhook, EventWebhookHeader

        body = (await request.body()).decode("utf-8")
        signature = request.headers.get(EventWebhookHeader.SIGNATURE, "")
        timestamp = request.headers.get(EventWebhookHeader.TIMESTAMP, "")

        if not signature or not timestamp:
            logger.warning("Missing SendGrid webhook signature or timestamp headers")
            return False

        ew = EventWebhook()
        key = ew.convert_public_key_to_ecdsa(settings.sendgrid_webhook_verification_key)
        return ew.verify_signature(body, signature, timestamp, key)
    except Exception:
        logger.exception("SendGrid signature verification failed")
        return False


async def require_sendgrid_signature(request: Request) -> None:
    """FastAPI dependency that enforces SendGrid signature verification.

    Raises HTTPException(403) if the signature is invalid.
    """
    if not await verify_sendgrid_signature(request):
        raise HTTPException(status_code=403, detail="Invalid SendGrid signature")
