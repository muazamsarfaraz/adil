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


def _extract_inbound_token(request: Request) -> str:
    """Pull the bearer token from `?token=` query or `Authorization` header.

    Either source is accepted because SendGrid Inbound Parse settings can be
    configured with the token in the URL (simpler) OR a forwarder/proxy can
    inject an Authorization header.
    """
    q = request.query_params.get("token")
    if q:
        return q
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def verify_sendgrid_inbound_token(request: Request) -> bool:
    """Verify the SendGrid Inbound Parse bearer token (shared-secret).

    SendGrid Inbound Parse does NOT use ECDSA signing (that's only on the
    Event Webhook), so this is a constant-time compare of a configured
    shared secret. Disable via `sendgrid_inbound_verify_enabled=False` for
    dev only.
    """
    import hmac

    if not settings.sendgrid_inbound_verify_enabled:
        return True
    if not settings.sendgrid_inbound_token:
        logger.error(
            "sendgrid_inbound_token is empty but verification is enabled — "
            "refusing all inbound webhooks until configured"
        )
        return False
    presented = _extract_inbound_token(request)
    if not presented:
        logger.warning("Missing SendGrid inbound bearer token")
        return False
    return hmac.compare_digest(presented, settings.sendgrid_inbound_token)


async def require_sendgrid_inbound_token(request: Request) -> None:
    """FastAPI dependency that enforces inbound webhook token verification.

    Raises HTTPException(403) on mismatch / missing token.
    """
    if not await verify_sendgrid_inbound_token(request):
        raise HTTPException(status_code=403, detail="Invalid inbound webhook token")
