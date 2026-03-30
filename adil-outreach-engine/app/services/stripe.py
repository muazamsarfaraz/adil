"""Stripe Checkout session creation and webhook processing."""

import logging

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.outreach_event import EventType, OutreachEvent
from app.services.conversion import ConflictError, process_conversion

logger = logging.getLogger(__name__)


async def create_checkout_session(contact: Contact, campaign: Campaign) -> str:
    """Create a Stripe Checkout Session and return the session URL."""
    stripe.api_key = settings.stripe_secret_key

    conversion_config = campaign.conversion_config or {}
    price_id = conversion_config["stripe_price_id"]
    payment_mode = conversion_config.get("payment_mode", "one_time")

    # Map payment_mode to Stripe mode
    stripe_mode = "payment" if payment_mode == "one_time" else "subscription"

    session = stripe.checkout.Session.create(
        mode=stripe_mode,
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=str(contact.id),
        customer_email=contact.email,
        success_url=f"{settings.public_base_url}/conversion/success?type=payment",
        cancel_url=f"{settings.public_base_url}/conversion/cancelled",
        metadata={
            "campaign_id": str(campaign.id),
            "contact_id": str(contact.id),
        },
    )

    return session.url


async def handle_stripe_webhook(
    payload: bytes,
    sig_header: str,
    db: AsyncSession,
) -> None:
    """Process a Stripe webhook event.

    Only handles checkout.session.completed events.
    """
    stripe.api_key = settings.stripe_secret_key

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise

    # Only handle checkout.session.completed
    if event["type"] != "checkout.session.completed":
        logger.info("Ignoring Stripe event type: %s", event["type"])
        return

    session = event["data"]["object"]
    stripe_event_id = event["id"]

    # Idempotency: check if we already processed this event
    result = await db.execute(
        select(OutreachEvent).where(
            OutreachEvent.event_type == EventType.payment_received,
        )
    )
    for evt in result.scalars().all():
        meta = evt.metadata_ or {}
        if meta.get("stripe_event_id") == stripe_event_id:
            logger.info("Stripe event %s already processed, skipping", stripe_event_id)
            return

    contact_id = session.get("client_reference_id")
    if not contact_id:
        logger.warning("Stripe webhook missing client_reference_id")
        return

    # Build conversion data
    data = {
        "stripe_session_id": session.get("id"),
        "stripe_event_id": stripe_event_id,
        "payment_intent": session.get("payment_intent"),
        "amount_total": session.get("amount_total"),
        "currency": session.get("currency"),
        "customer_email": (session.get("customer_details") or {}).get("email"),
        "payment_status": session.get("payment_status"),
    }

    try:
        await process_conversion(contact_id, "payment", data, db)
    except ConflictError:
        logger.info("Contact %s already converted (Stripe duplicate)", contact_id)
    except ValueError as e:
        logger.error("Stripe webhook error: %s", e)
        raise
