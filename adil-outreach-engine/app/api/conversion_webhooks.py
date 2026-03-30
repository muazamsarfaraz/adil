"""Inbound webhook endpoints for Stripe and Cal.com.

These endpoints handle conversion-related webhooks and are NOT rate-limited
since they come from trusted external services.
"""

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cal import handle_cal_webhook, verify_cal_signature
from app.services.stripe import handle_stripe_webhook

logger = logging.getLogger(__name__)

conversion_webhooks_router = APIRouter(
    prefix="/api/v1/outreach/webhooks",
    tags=["conversion-webhooks"],
)


@conversion_webhooks_router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events (checkout.session.completed)."""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        await handle_stripe_webhook(payload, sig_header, db)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception:
        # Log the error but return 200 to prevent Stripe infinite retries
        logger.exception("Error processing Stripe webhook")

    return {"status": "ok"}


@conversion_webhooks_router.post("/cal")
async def cal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Cal.com webhook events (BOOKING_CREATED)."""
    payload_bytes = await request.body()
    signature = request.headers.get("X-Cal-Signature-256", "")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing X-Cal-Signature-256 header")

    if not verify_cal_signature(payload_bytes, signature):
        raise HTTPException(status_code=400, detail="Invalid Cal.com signature")

    import json

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        await handle_cal_webhook(payload, db)
    except Exception:
        # Log the error but return 200 to prevent Cal.com infinite retries
        logger.exception("Error processing Cal.com webhook")

    return {"status": "ok"}
