"""Public-facing endpoints for signup, booking, and payment conversions.

These endpoints are rate-limited and do NOT require API key authentication.
"""

import logging
import uuid
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign, CampaignGoal, CampaignStatus
from app.models.contact import Contact
from app.models.conversion import Conversion
from app.schemas.conversion import (
    BookingInitResponse,
    ConversionConfirmation,
    PaymentInitResponse,
    SignupFieldWithValue,
    SignupFormResponse,
    SignupSubmission,
)
from app.rate_limit import limiter
from app.services.conversion import ConflictError, process_conversion

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/api/v1/outreach", tags=["public"])

# PII fields that should NOT be returned in pre-populated form responses
_PII_FIELDS = {"email", "phone"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_active_campaign_by_slug(slug: str, db: AsyncSession) -> Campaign:
    result = await db.execute(select(Campaign).where(Campaign.slug == slug, Campaign.status == CampaignStatus.active))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not active")
    return campaign


async def _get_contact_for_campaign(ref: str, campaign_id: uuid.UUID, db: AsyncSession) -> Contact | None:
    """Fetch a contact by UUID and validate it belongs to the campaign."""
    try:
        contact_uuid = uuid.UUID(ref)
    except ValueError:
        return None
    contact = await db.get(Contact, contact_uuid)
    if contact and contact.campaign_id == campaign_id:
        return contact
    return None


async def _find_contact_by_email(email: str, campaign_id: uuid.UUID, db: AsyncSession) -> Contact | None:
    """Try to find a contact by email within a campaign."""
    result = await db.execute(select(Contact).where(Contact.email == email, Contact.campaign_id == campaign_id))
    return result.scalar_one_or_none()


async def validate_signup_fields(
    submission: dict,
    field_configs: list[dict],
) -> tuple[dict, list[dict]]:
    """Validate dynamic signup fields. Returns (validated_data, errors)."""
    validated: dict = {}
    errors: list[dict] = []
    for field in field_configs:
        value = submission.get(field["name"])
        if field.get("required") and value is None:
            errors.append({"field": field["name"], "error": "required"})
            continue
        if value is None:
            continue
        field_type = field.get("type", "text")
        if field_type == "text":
            if not isinstance(value, str) or len(value) > 1000:
                errors.append({"field": field["name"], "error": "invalid text"})
            else:
                validated[field["name"]] = value
        elif field_type == "boolean":
            if not isinstance(value, bool):
                errors.append({"field": field["name"], "error": "must be boolean"})
            else:
                validated[field["name"]] = value
        elif field_type == "select":
            options = field.get("options", [])
            if value not in options:
                errors.append({"field": field["name"], "error": f"must be one of {options}"})
            else:
                validated[field["name"]] = value
        elif field_type == "multi_select":
            options = field.get("options", [])
            if not isinstance(value, list) or not all(v in options for v in value):
                errors.append({"field": field["name"], "error": f"must be list from {options}"})
            else:
                validated[field["name"]] = value
    return validated, errors


# ---------------------------------------------------------------------------
# Signup Endpoints (Tasks 2 & 3)
# ---------------------------------------------------------------------------


@public_router.get("/signup/{campaign_slug}", response_model=SignupFormResponse)
@limiter.limit("10/minute")
async def get_signup_form(
    request: Request,
    campaign_slug: str,
    ref: str | None = Query(None, description="Contact UUID for form pre-population"),
    db: AsyncSession = Depends(get_db),
):
    """Return signup form field configuration, optionally pre-populated from contact metadata."""
    campaign = await _get_active_campaign_by_slug(campaign_slug, db)
    conversion_config = campaign.conversion_config or {}
    signup_fields = conversion_config.get("signup_fields", [])

    # Build field list
    fields: list[SignupFieldWithValue] = []
    contact_name: str | None = None
    contact_metadata: dict = {}

    # Task 3: Pre-population from contact.metadata
    if ref:
        contact = await _get_contact_for_campaign(ref, campaign.id, db)
        if contact:
            contact_name = contact.name
            contact_metadata = contact.metadata_ or {}

    for field_def in signup_fields:
        field = SignupFieldWithValue(
            name=field_def["name"],
            type=field_def.get("type", "text"),
            required=field_def.get("required", False),
            options=field_def.get("options"),
            value=None,
        )
        # Pre-populate if we have contact metadata (but filter PII)
        if contact_metadata and field.name not in _PII_FIELDS:
            field.value = contact_metadata.get(field.name)
        fields.append(field)

    return SignupFormResponse(
        campaign_name=campaign.name,
        campaign_slug=campaign.slug,
        fields=fields,
        contact_name=contact_name,
    )


@public_router.post("/signup/{campaign_slug}", response_model=ConversionConfirmation, status_code=201)
@limiter.limit("10/minute")
async def submit_signup(
    request: Request,
    campaign_slug: str,
    body: SignupSubmission,
    db: AsyncSession = Depends(get_db),
):
    """Submit a signup form with dynamic field validation."""
    campaign = await _get_active_campaign_by_slug(campaign_slug, db)
    conversion_config = campaign.conversion_config or {}
    signup_fields = conversion_config.get("signup_fields", [])

    # Extract ref and dynamic fields
    ref = body.ref
    submission_data = body.model_extra or {}

    # Resolve contact
    contact: Contact | None = None
    if ref:
        contact = await _get_contact_for_campaign(ref, campaign.id, db)

    # If no contact from ref, try to match by email
    if not contact and "email" in submission_data:
        contact = await _find_contact_by_email(submission_data["email"], campaign.id, db)

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found for this campaign")

    # Check not already converted
    existing = await db.execute(select(Conversion).where(Conversion.contact_id == contact.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Contact already converted")

    # Validate dynamic fields
    validated_data, errors = await validate_signup_fields(submission_data, signup_fields)
    if errors:
        raise HTTPException(status_code=422, detail={"field_errors": errors})

    # Process conversion
    try:
        conversion = await process_conversion(str(contact.id), "signup", validated_data, db)
    except ConflictError:
        raise HTTPException(status_code=409, detail="Contact already converted")

    return ConversionConfirmation(
        id=conversion.id,
        type=conversion.type.value,
        contact_id=conversion.contact_id,
        message="Signup completed successfully",
        created_at=conversion.created_at,
    )


# ---------------------------------------------------------------------------
# Payment Endpoint (Task 6)
# ---------------------------------------------------------------------------


@public_router.post("/pay/{campaign_slug}", response_model=PaymentInitResponse)
@limiter.limit("10/minute")
async def initiate_payment(
    request: Request,
    campaign_slug: str,
    ref: str = Query(..., description="Contact UUID from email link"),
    db: AsyncSession = Depends(get_db),
):
    """Initiate a Stripe Checkout session for payment conversion."""
    campaign = await _get_active_campaign_by_slug(campaign_slug, db)

    if campaign.goal != CampaignGoal.payment:
        raise HTTPException(status_code=400, detail="Campaign goal is not payment")

    conversion_config = campaign.conversion_config or {}
    if not conversion_config.get("stripe_price_id"):
        raise HTTPException(status_code=500, detail="Campaign payment not configured: missing stripe_price_id")

    contact = await _get_contact_for_campaign(ref, campaign.id, db)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found for this campaign")

    # Check not already converted
    existing = await db.execute(select(Conversion).where(Conversion.contact_id == contact.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Contact already converted")

    from app.services.stripe import create_checkout_session

    session_url = await create_checkout_session(contact, campaign)

    return PaymentInitResponse(checkout_url=session_url)


# ---------------------------------------------------------------------------
# Booking Endpoint (Task 9)
# ---------------------------------------------------------------------------


@public_router.post("/book/{campaign_slug}", response_model=BookingInitResponse)
@limiter.limit("10/minute")
async def initiate_booking(
    request: Request,
    campaign_slug: str,
    ref: str = Query(..., description="Contact UUID from email link"),
    db: AsyncSession = Depends(get_db),
):
    """Generate a Cal.com booking link with contact tracking."""
    campaign = await _get_active_campaign_by_slug(campaign_slug, db)

    if campaign.goal != CampaignGoal.booking:
        raise HTTPException(status_code=400, detail="Campaign goal is not booking")

    conversion_config = campaign.conversion_config or {}
    cal_event_link = conversion_config.get("cal_event_link")
    if not cal_event_link:
        raise HTTPException(status_code=500, detail="Campaign booking not configured: missing cal_event_link")

    contact = await _get_contact_for_campaign(ref, campaign.id, db)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found for this campaign")

    # Check not already converted
    existing = await db.execute(select(Conversion).where(Conversion.contact_id == contact.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Contact already converted")

    # Construct booking URL with contact tracking and pre-fill
    parsed = urlparse(cal_event_link)
    existing_params = parse_qs(parsed.query)
    new_params = {
        "contact": str(contact.id),
        "name": contact.name or "",
        "email": contact.email or "",
    }
    # Merge existing params with new ones
    for k, v in new_params.items():
        existing_params[k] = [v]

    # Rebuild query string
    flat_params = {k: v[0] if len(v) == 1 else v for k, v in existing_params.items()}
    new_query = urlencode(flat_params)
    booking_url = urlunparse(parsed._replace(query=new_query))

    return BookingInitResponse(booking_url=booking_url)
