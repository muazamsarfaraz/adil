"""Tests for all conversion types, webhook retry, custom goals, and rate limiting."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignGoal, CampaignStatus
from app.models.contact import Contact, ContactStatus
from app.models.conversion import Conversion, ConversionType
from app.models.outreach_event import EventType, OutreachEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def signup_campaign(db_session: AsyncSession) -> Campaign:
    """Campaign with goal=signup and signup_fields config."""
    campaign = Campaign(
        name="Test Signup Campaign",
        slug="test-signup",
        goal=CampaignGoal.signup,
        status=CampaignStatus.active,
        sender_email="sender@test.com",
        sender_name="Test Sender",
        conversion_config={
            "signup_fields": [
                {"name": "company", "type": "text", "required": True},
                {"name": "interest", "type": "select", "required": True, "options": ["legal", "finance", "tech"]},
                {"name": "newsletter", "type": "boolean", "required": False},
                {"name": "topics", "type": "multi_select", "required": False, "options": ["ai", "cloud", "security"]},
            ],
            "confirmation_email": False,
        },
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def booking_campaign(db_session: AsyncSession) -> Campaign:
    """Campaign with goal=booking and cal_event_link config."""
    campaign = Campaign(
        name="Test Booking Campaign",
        slug="test-booking",
        goal=CampaignGoal.booking,
        status=CampaignStatus.active,
        conversion_config={
            "cal_event_link": "https://cal.com/test/meeting",
        },
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def payment_campaign(db_session: AsyncSession) -> Campaign:
    """Campaign with goal=payment and stripe_price_id config."""
    campaign = Campaign(
        name="Test Payment Campaign",
        slug="test-payment",
        goal=CampaignGoal.payment,
        status=CampaignStatus.active,
        conversion_config={
            "stripe_price_id": "price_test123",
            "payment_mode": "one_time",
        },
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def custom_campaign(db_session: AsyncSession) -> Campaign:
    """Campaign with goal=custom and success_criteria."""
    campaign = Campaign(
        name="Test Custom Campaign",
        slug="test-custom",
        goal=CampaignGoal.custom,
        status=CampaignStatus.active,
        success_criteria={
            "event_type": "reply_classified",
            "classification": "interested",
        },
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def contact_for_signup(db_session: AsyncSession, signup_campaign: Campaign) -> Contact:
    """Contact in emailed status with metadata for signup campaign."""
    contact = Contact(
        campaign_id=signup_campaign.id,
        name="John Doe",
        email="john@example.com",
        firm_name="Doe Legal",
        status=ContactStatus.emailed,
        metadata_={"company": "Doe Legal", "interest": "legal", "email": "john@example.com"},
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def contact_for_booking(db_session: AsyncSession, booking_campaign: Campaign) -> Contact:
    """Contact for booking campaign."""
    contact = Contact(
        campaign_id=booking_campaign.id,
        name="Jane Smith",
        email="jane@example.com",
        firm_name="Smith & Co",
        status=ContactStatus.emailed,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def contact_for_payment(db_session: AsyncSession, payment_campaign: Campaign) -> Contact:
    """Contact for payment campaign."""
    contact = Contact(
        campaign_id=payment_campaign.id,
        name="Bob Jones",
        email="bob@example.com",
        firm_name="Jones Law",
        status=ContactStatus.emailed,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def contact_for_custom(db_session: AsyncSession, custom_campaign: Campaign) -> Contact:
    """Contact for custom goal campaign."""
    contact = Contact(
        campaign_id=custom_campaign.id,
        name="Alice Brown",
        email="alice@example.com",
        status=ContactStatus.emailed,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


# ---------------------------------------------------------------------------
# Signup Tests
# ---------------------------------------------------------------------------


class TestSignupForm:
    async def test_get_signup_form_returns_field_config(self, client: AsyncClient, signup_campaign: Campaign):
        resp = await client.get(f"/api/v1/outreach/signup/{signup_campaign.slug}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_name"] == signup_campaign.name
        assert data["campaign_slug"] == signup_campaign.slug
        assert len(data["fields"]) == 4
        field_names = [f["name"] for f in data["fields"]]
        assert "company" in field_names
        assert "interest" in field_names
        assert "newsletter" in field_names
        assert "topics" in field_names

    async def test_get_signup_form_with_prepopulation(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        resp = await client.get(
            f"/api/v1/outreach/signup/{signup_campaign.slug}",
            params={"ref": str(contact_for_signup.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["contact_name"] == "John Doe"
        # company should be pre-populated from metadata
        company_field = next(f for f in data["fields"] if f["name"] == "company")
        assert company_field["value"] == "Doe Legal"
        # email should NOT be pre-populated (PII filtering)
        # email is not a signup field, so it won't appear; but if it were, value should be None

    async def test_get_signup_form_invalid_slug_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/outreach/signup/nonexistent-slug")
        assert resp.status_code == 404

    async def test_post_signup_success(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact, db_session: AsyncSession
    ):
        resp = await client.post(
            f"/api/v1/outreach/signup/{signup_campaign.slug}",
            json={
                "ref": str(contact_for_signup.id),
                "company": "Doe Legal",
                "interest": "legal",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "signup"
        assert data["message"] == "Signup completed successfully"

        # Verify contact status updated
        await db_session.refresh(contact_for_signup)
        assert contact_for_signup.status == ContactStatus.converted

    async def test_post_signup_missing_required_field_422(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        resp = await client.post(
            f"/api/v1/outreach/signup/{signup_campaign.slug}",
            json={
                "ref": str(contact_for_signup.id),
                # missing "company" and "interest" (both required)
            },
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "field_errors" in data["detail"]
        error_fields = [e["field"] for e in data["detail"]["field_errors"]]
        assert "company" in error_fields
        assert "interest" in error_fields

    async def test_post_signup_invalid_multi_select_422(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        resp = await client.post(
            f"/api/v1/outreach/signup/{signup_campaign.slug}",
            json={
                "ref": str(contact_for_signup.id),
                "company": "Test Co",
                "interest": "legal",
                "topics": ["invalid_option"],
            },
        )
        assert resp.status_code == 422

    async def test_post_signup_already_converted_409(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact, db_session: AsyncSession
    ):
        # Create existing conversion
        existing = Conversion(
            contact_id=contact_for_signup.id,
            type=ConversionType.signup,
            data={"company": "Test"},
        )
        db_session.add(existing)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/outreach/signup/{signup_campaign.slug}",
            json={
                "ref": str(contact_for_signup.id),
                "company": "Test Co",
                "interest": "legal",
            },
        )
        assert resp.status_code == 409

    async def test_post_signup_by_email_match(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        """When ref is not provided, match by email field."""
        resp = await client.post(
            f"/api/v1/outreach/signup/{signup_campaign.slug}",
            json={
                "email": contact_for_signup.email,
                "company": "Doe Legal",
                "interest": "legal",
            },
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Booking Tests
# ---------------------------------------------------------------------------


class TestBooking:
    async def test_initiate_booking_returns_url(
        self, client: AsyncClient, booking_campaign: Campaign, contact_for_booking: Contact
    ):
        resp = await client.post(
            f"/api/v1/outreach/book/{booking_campaign.slug}",
            params={"ref": str(contact_for_booking.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "booking_url" in data
        assert str(contact_for_booking.id) in data["booking_url"]
        assert "cal.com" in data["booking_url"]

    async def test_initiate_booking_wrong_goal_400(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        resp = await client.post(
            f"/api/v1/outreach/book/{signup_campaign.slug}",
            params={"ref": str(contact_for_signup.id)},
        )
        assert resp.status_code == 400
        assert "not booking" in resp.json()["detail"]

    async def test_cal_webhook_creates_conversion(
        self, client: AsyncClient, booking_campaign: Campaign, contact_for_booking: Contact, db_session: AsyncSession
    ):
        contact_id = contact_for_booking.id  # capture before session expires
        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "bookingId": "cal-booking-123",
            "eventTitle": "Consultation",
            "startTime": "2026-04-01T10:00:00Z",
            "endTime": "2026-04-01T11:00:00Z",
            "attendees": [{"email": "jane@example.com", "name": "Jane Smith"}],
            "meetingUrl": "https://meet.cal.com/test",
            "metadata": {"contact": str(contact_id)},
        }
        payload_bytes = json.dumps(payload).encode()

        # Compute valid HMAC signature
        with patch("app.services.cal.settings") as mock_settings:
            mock_settings.cal_webhook_secret = "test-secret"
            sig = hmac.new(b"test-secret", payload_bytes, hashlib.sha256).hexdigest()

        with patch("app.services.cal.settings") as mock_settings:
            mock_settings.cal_webhook_secret = "test-secret"
            resp = await client.post(
                "/api/v1/outreach/webhooks/cal",
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Cal-Signature-256": sig,
                },
            )

        assert resp.status_code == 200

        # Verify conversion was created
        result = await db_session.execute(select(Conversion).where(Conversion.contact_id == contact_id))
        conversion = result.scalar_one_or_none()
        assert conversion is not None
        assert conversion.type == ConversionType.booking

    async def test_cal_webhook_invalid_signature_400(self, client: AsyncClient):
        payload = json.dumps({"triggerEvent": "BOOKING_CREATED"}).encode()

        with patch("app.services.cal.settings") as mock_settings:
            mock_settings.cal_webhook_secret = "test-secret"
            resp = await client.post(
                "/api/v1/outreach/webhooks/cal",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Cal-Signature-256": "invalid-signature",
                },
            )

        assert resp.status_code == 400

    async def test_cal_webhook_missing_contact_id_logged(self, client: AsyncClient):
        """Missing contact in payload should return 200 but not create conversion."""
        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "bookingId": "cal-booking-no-contact",
            "metadata": {},
        }
        payload_bytes = json.dumps(payload).encode()

        with patch("app.services.cal.settings") as mock_settings:
            mock_settings.cal_webhook_secret = "test-secret"
            sig = hmac.new(b"test-secret", payload_bytes, hashlib.sha256).hexdigest()

            resp = await client.post(
                "/api/v1/outreach/webhooks/cal",
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Cal-Signature-256": sig,
                },
            )

        assert resp.status_code == 200

    async def test_cal_webhook_idempotent(
        self, client: AsyncClient, booking_campaign: Campaign, contact_for_booking: Contact, db_session: AsyncSession
    ):
        """Duplicate booking ID should not create duplicate conversion."""
        contact_id = contact_for_booking.id  # capture before session expires
        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "bookingId": "cal-booking-dup",
            "metadata": {"contact": str(contact_id)},
            "attendees": [{"email": "jane@example.com", "name": "Jane"}],
        }
        payload_bytes = json.dumps(payload).encode()

        with patch("app.services.cal.settings") as mock_settings:
            mock_settings.cal_webhook_secret = "test-secret"
            sig = hmac.new(b"test-secret", payload_bytes, hashlib.sha256).hexdigest()

            # First call
            resp1 = await client.post(
                "/api/v1/outreach/webhooks/cal",
                content=payload_bytes,
                headers={"Content-Type": "application/json", "X-Cal-Signature-256": sig},
            )
            assert resp1.status_code == 200

            # Second call (same booking ID) — should be idempotent
            resp2 = await client.post(
                "/api/v1/outreach/webhooks/cal",
                content=payload_bytes,
                headers={"Content-Type": "application/json", "X-Cal-Signature-256": sig},
            )
            assert resp2.status_code == 200

        # Only one conversion should exist
        result = await db_session.execute(select(Conversion).where(Conversion.contact_id == contact_id))
        conversions = result.scalars().all()
        assert len(conversions) == 1


# ---------------------------------------------------------------------------
# Payment Tests
# ---------------------------------------------------------------------------


class TestPayment:
    async def test_initiate_payment_returns_checkout_url(
        self, client: AsyncClient, payment_campaign: Campaign, contact_for_payment: Contact
    ):
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test-session"

        with patch("app.services.stripe.stripe.checkout.Session.create", return_value=mock_session):
            resp = await client.post(
                f"/api/v1/outreach/pay/{payment_campaign.slug}",
                params={"ref": str(contact_for_payment.id)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/test-session"

    async def test_initiate_payment_wrong_goal_400(
        self, client: AsyncClient, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        resp = await client.post(
            f"/api/v1/outreach/pay/{signup_campaign.slug}",
            params={"ref": str(contact_for_signup.id)},
        )
        assert resp.status_code == 400
        assert "not payment" in resp.json()["detail"]

    async def test_stripe_webhook_creates_conversion(
        self, client: AsyncClient, payment_campaign: Campaign, contact_for_payment: Contact, db_session: AsyncSession
    ):
        contact_id = contact_for_payment.id  # capture before session expires
        campaign_id = payment_campaign.id
        stripe_event = {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "client_reference_id": str(contact_id),
                    "payment_intent": "pi_test_123",
                    "amount_total": 5000,
                    "currency": "gbp",
                    "customer_details": {"email": "bob@example.com"},
                    "payment_status": "paid",
                    "metadata": {"campaign_id": str(campaign_id)},
                },
            },
        }

        with patch("app.services.stripe.stripe.Webhook.construct_event", return_value=stripe_event):
            resp = await client.post(
                "/api/v1/outreach/webhooks/stripe",
                content=json.dumps(stripe_event).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "test_sig",
                },
            )

        assert resp.status_code == 200

        # Verify conversion created
        result = await db_session.execute(select(Conversion).where(Conversion.contact_id == contact_id))
        conversion = result.scalar_one_or_none()
        assert conversion is not None
        assert conversion.type == ConversionType.payment

    async def test_stripe_webhook_invalid_signature_400(self, client: AsyncClient):
        with patch(
            "app.services.stripe.stripe.Webhook.construct_event",
            side_effect=__import__("stripe").error.SignatureVerificationError("bad sig", "header"),
        ):
            resp = await client.post(
                "/api/v1/outreach/webhooks/stripe",
                content=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "bad_sig",
                },
            )
        assert resp.status_code == 400

    async def test_stripe_webhook_idempotent(
        self, client: AsyncClient, payment_campaign: Campaign, contact_for_payment: Contact, db_session: AsyncSession
    ):
        contact_id = contact_for_payment.id  # capture before session expires
        stripe_event = {
            "id": "evt_idem_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_idem_123",
                    "client_reference_id": str(contact_id),
                    "payment_intent": "pi_idem_123",
                    "amount_total": 5000,
                    "currency": "gbp",
                    "customer_details": {"email": "bob@example.com"},
                    "payment_status": "paid",
                },
            },
        }

        with patch("app.services.stripe.stripe.Webhook.construct_event", return_value=stripe_event):
            # First call
            resp1 = await client.post(
                "/api/v1/outreach/webhooks/stripe",
                content=json.dumps(stripe_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "test_sig"},
            )
            assert resp1.status_code == 200

            # Second call (same event ID) — idempotent
            resp2 = await client.post(
                "/api/v1/outreach/webhooks/stripe",
                content=json.dumps(stripe_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "test_sig"},
            )
            assert resp2.status_code == 200

        # Only one conversion
        result = await db_session.execute(select(Conversion).where(Conversion.contact_id == contact_id))
        assert len(result.scalars().all()) == 1

    async def test_stripe_webhook_ignores_other_events(self, client: AsyncClient):
        stripe_event = {
            "id": "evt_other_123",
            "type": "payment_intent.succeeded",
            "data": {"object": {}},
        }

        with patch("app.services.stripe.stripe.Webhook.construct_event", return_value=stripe_event):
            resp = await client.post(
                "/api/v1/outreach/webhooks/stripe",
                content=json.dumps(stripe_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "test_sig"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Webhook Retry Tests
# ---------------------------------------------------------------------------


class TestWebhookRetry:
    async def test_conversion_webhook_fires_on_success(
        self, db_session: AsyncSession, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        """Successful webhook should log webhook_sent event."""
        from app.services.conversion import process_conversion

        # Create conversion first
        conversion = await process_conversion(str(contact_for_signup.id), "signup", {"company": "Test"}, db_session)

        from app.workers.tasks import _fire_webhook_impl

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("app.workers.tasks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _fire_webhook_impl({}, str(conversion.id), "https://webhook.test/callback", 1, db_session)

        # Verify webhook_sent event was logged
        result = await db_session.execute(
            select(OutreachEvent).where(
                OutreachEvent.contact_id == contact_for_signup.id,
                OutreachEvent.event_type == EventType.webhook_sent,
            )
        )
        webhook_event = result.scalar_one_or_none()
        assert webhook_event is not None

    async def test_conversion_webhook_retries_on_failure(
        self, db_session: AsyncSession, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        """Failed webhook should attempt to re-enqueue."""
        from app.services.conversion import process_conversion
        from app.workers.tasks import _fire_webhook_impl

        conversion = await process_conversion(str(contact_for_signup.id), "signup", {"company": "Test"}, db_session)

        import httpx

        mock_redis = AsyncMock()

        with patch("app.workers.tasks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _fire_webhook_impl(
                {"redis": mock_redis},
                str(conversion.id),
                "https://webhook.test/callback",
                1,
                db_session,
            )

        # Should have re-enqueued with attempt 2
        mock_redis.enqueue_job.assert_called_once()
        call_args = mock_redis.enqueue_job.call_args
        assert call_args[0][0] == "fire_conversion_webhook"
        assert call_args[0][2] == "https://webhook.test/callback"
        assert call_args[0][3] == 2  # attempt 2

    async def test_conversion_webhook_logs_failure_after_3_attempts(
        self, db_session: AsyncSession, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        """After 3 failed attempts, webhook_failed event should be logged."""
        from app.services.conversion import process_conversion
        from app.workers.tasks import _fire_webhook_impl

        conversion = await process_conversion(str(contact_for_signup.id), "signup", {"company": "Test"}, db_session)

        import httpx

        with patch("app.workers.tasks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _fire_webhook_impl({}, str(conversion.id), "https://webhook.test/callback", 3, db_session)

        # Verify webhook_failed event
        result = await db_session.execute(
            select(OutreachEvent).where(
                OutreachEvent.contact_id == contact_for_signup.id,
                OutreachEvent.event_type == EventType.webhook_failed,
            )
        )
        failed_event = result.scalar_one_or_none()
        assert failed_event is not None
        assert failed_event.metadata_["attempts"] == 3

    async def test_conversion_webhook_does_not_rollback_conversion(
        self, db_session: AsyncSession, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        """Conversion record persists even if webhook fails."""
        from app.services.conversion import process_conversion
        from app.workers.tasks import _fire_webhook_impl

        conversion = await process_conversion(str(contact_for_signup.id), "signup", {"company": "Test"}, db_session)
        conversion_id = conversion.id

        import httpx

        with patch("app.workers.tasks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _fire_webhook_impl({}, str(conversion_id), "https://webhook.test/callback", 3, db_session)

        # Conversion should still exist
        result = await db_session.execute(select(Conversion).where(Conversion.id == conversion_id))
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Custom Goal Tests
# ---------------------------------------------------------------------------


class TestCustomGoal:
    async def test_custom_goal_converts_on_matching_event(
        self, db_session: AsyncSession, custom_campaign: Campaign, contact_for_custom: Contact
    ):
        from app.services.goal_evaluator import evaluate_custom_goal

        result = await evaluate_custom_goal(
            str(contact_for_custom.id),
            "reply_classified",
            {"classification": "interested"},
            db_session,
        )
        assert result is True

        # Verify conversion was created
        conv_result = await db_session.execute(select(Conversion).where(Conversion.contact_id == contact_for_custom.id))
        conversion = conv_result.scalar_one_or_none()
        assert conversion is not None
        assert conversion.type == ConversionType.custom

    async def test_custom_goal_no_match_no_conversion(
        self, db_session: AsyncSession, custom_campaign: Campaign, contact_for_custom: Contact
    ):
        from app.services.goal_evaluator import evaluate_custom_goal

        result = await evaluate_custom_goal(
            str(contact_for_custom.id),
            "reply_classified",
            {"classification": "declined"},
            db_session,
        )
        assert result is False

        # No conversion should exist
        conv_result = await db_session.execute(select(Conversion).where(Conversion.contact_id == contact_for_custom.id))
        assert conv_result.scalar_one_or_none() is None

    async def test_custom_goal_ignored_for_signup_campaigns(
        self, db_session: AsyncSession, signup_campaign: Campaign, contact_for_signup: Contact
    ):
        from app.services.goal_evaluator import evaluate_custom_goal

        result = await evaluate_custom_goal(
            str(contact_for_signup.id),
            "reply_classified",
            {"classification": "interested"},
            db_session,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------


class TestRateLimiting:
    async def test_public_endpoint_rate_limited(self, client: AsyncClient, signup_campaign: Campaign):
        """11th request within 1 minute should return 429."""
        # Reset rate limiter storage to avoid cross-test contamination
        from app.rate_limit import limiter

        limiter.reset()

        # Make 10 requests (should all succeed or return 404, but NOT 429)
        for i in range(10):
            resp = await client.get(f"/api/v1/outreach/signup/{signup_campaign.slug}")
            assert resp.status_code != 429, f"Request {i+1} unexpectedly rate limited"

        # 11th request should be rate limited
        resp = await client.get(f"/api/v1/outreach/signup/{signup_campaign.slug}")
        assert resp.status_code == 429

    async def test_webhook_endpoint_not_rate_limited(self, client: AsyncClient):
        """Webhook endpoints should accept unlimited requests."""
        # Reset rate limiter storage to avoid cross-test contamination
        from app.rate_limit import limiter

        limiter.reset()

        for i in range(15):
            resp = await client.post(
                "/api/v1/outreach/webhooks/stripe",
                content=b"{}",
                headers={"Content-Type": "application/json"},
            )
            # Should get 400 (missing Stripe-Signature) but NOT 429
            assert resp.status_code == 400
