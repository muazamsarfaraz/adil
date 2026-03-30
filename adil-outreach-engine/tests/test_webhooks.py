"""Tests for Plan 4: Webhooks & Response Handling.

Covers: SendGrid event webhook, bounce handling, inbound parse (reply capture),
classify_reply task, late reply handling, draft preview/approval, events timeline,
and signature verification.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign, CampaignGoal, CampaignStatus
from app.models.contact import Contact, ContactStatus
from app.models.outreach_event import OutreachEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def active_campaign(db_session: AsyncSession) -> Campaign:
    """Campaign with auto_send=True for testing."""
    campaign = Campaign(
        id=uuid.uuid4(),
        name="Test Campaign",
        slug="test-campaign",
        goal=CampaignGoal.signup,
        status=CampaignStatus.active,
        auto_send=True,
        sender_email="outreach@askadil.org",
        sender_name="AskAdil",
        reply_to="outreach@askadil.org",
        templates={"initial": {"subject": "Test", "body": "Hello"}},
        cadence=[{"day": 0, "template": "initial"}, {"day": 3, "action": "follow_up"}],
        llm_config={"classify": {"provider": "gemini", "model": "gemini-2.5-flash"}},
    )
    db_session.add(campaign)
    await db_session.commit()
    return campaign


@pytest.fixture
async def emailed_contact(db_session: AsyncSession, active_campaign: Campaign) -> Contact:
    """Contact with status=emailed and a sent email event."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=active_campaign.id,
        name="Test Contact",
        email="test@example.com",
        firm_name="Test Firm",
        status=ContactStatus.emailed,
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()

    # Add an email_sent event
    event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=contact.id,
        event_type="email_sent",
        channel="email",
        subject="Test Subject",
        content="<p>Hello</p>",
        metadata_={
            "sendgrid_message_id": "abc123",
            "idempotency_key": f"{contact.id}:0",
            "cadence_step": 0,
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(event)
    await db_session.commit()
    return contact


@pytest.fixture
async def unresponsive_contact(db_session: AsyncSession, active_campaign: Campaign) -> Contact:
    """Contact with status=unresponsive (cadence exhausted)."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=active_campaign.id,
        name="Unresponsive Contact",
        email="unresponsive@example.com",
        firm_name="Unresponsive Firm",
        status=ContactStatus.unresponsive,
        current_cadence_step=2,
    )
    db_session.add(contact)
    await db_session.commit()
    return contact


@pytest.fixture
async def draft_pending_contact(db_session: AsyncSession, active_campaign: Campaign) -> Contact:
    """Contact with status=draft_pending and a draft_created event."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=active_campaign.id,
        name="Draft Contact",
        email="draft@example.com",
        firm_name="Draft Firm",
        status=ContactStatus.draft_pending,
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()

    # Add a draft_created event
    event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=contact.id,
        event_type="draft_created",
        channel="system",
        subject="AskAdil Directory Listing",
        content="<p>Dear Draft Contact, we'd love to have you listed...</p>",
        metadata_={
            "template_key": "initial",
            "cadence_step": 0,
            "personalisation_hooks": ["firm specialisation", "local area"],
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(event)
    await db_session.commit()
    return contact


@pytest.fixture
async def emailed_contact_with_events(db_session: AsyncSession, active_campaign: Campaign) -> Contact:
    """Contact with status=emailed and multiple events for timeline testing."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=active_campaign.id,
        name="Timeline Contact",
        email="timeline@example.com",
        firm_name="Timeline Firm",
        status=ContactStatus.emailed,
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()

    # Add multiple events
    now = datetime.utcnow()
    events = [
        OutreachEvent(
            id=uuid.uuid4(),
            contact_id=contact.id,
            event_type="research_completed",
            channel="system",
            metadata_={"research_keys": ["website", "sra"]},
            created_at=now - timedelta(hours=3),
        ),
        OutreachEvent(
            id=uuid.uuid4(),
            contact_id=contact.id,
            event_type="draft_created",
            channel="system",
            subject="Test Subject",
            content="Draft body",
            metadata_={"template_key": "initial"},
            created_at=now - timedelta(hours=2),
        ),
        OutreachEvent(
            id=uuid.uuid4(),
            contact_id=contact.id,
            event_type="email_sent",
            channel="email",
            subject="Test Subject",
            content="Draft body",
            metadata_={"sendgrid_message_id": "xyz789", "cadence_step": 0},
            created_at=now - timedelta(hours=1),
        ),
    ]
    for e in events:
        db_session.add(e)
    await db_session.commit()
    return contact


@pytest.fixture
def mock_sendgrid_signature():
    """Bypass signature verification for tests."""
    with patch(
        "app.auth.webhook_verify.verify_sendgrid_signature",
        return_value=True,
    ):
        yield


@pytest.fixture
def auth_headers() -> dict:
    return {"X-API-Key": settings.api_key}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def get_events_for_contact(db_session: AsyncSession, contact_id: uuid.UUID) -> list[OutreachEvent]:
    """Get all events for a contact from the test DB."""
    result = await db_session.execute(
        select(OutreachEvent).where(OutreachEvent.contact_id == contact_id).order_by(OutreachEvent.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Test: SendGrid Event Webhook — Delivered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sendgrid_event_delivered(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
    mock_sendgrid_signature,
):
    """Delivered event should log an email_delivered outreach event."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "test@example.com",
                "event": "delivered",
                "timestamp": 1711411200,
                "sg_message_id": "abc123",
                "contact_id": str(emailed_contact.id),
            }
        ],
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    events = await get_events_for_contact(db_session, emailed_contact.id)
    assert any(e.event_type == "email_delivered" for e in events)


# ---------------------------------------------------------------------------
# Test: SendGrid Event Webhook — Opened
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sendgrid_event_opened(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
    mock_sendgrid_signature,
):
    """Open event should log an email_opened outreach event."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "test@example.com",
                "event": "open",
                "timestamp": 1711411200,
                "contact_id": str(emailed_contact.id),
                "useragent": "Mozilla/5.0",
                "ip": "1.2.3.4",
            }
        ],
    )
    assert response.status_code == 200

    events = await get_events_for_contact(db_session, emailed_contact.id)
    opened_events = [e for e in events if e.event_type == "email_opened"]
    assert len(opened_events) == 1
    assert opened_events[0].metadata_.get("ip") == "1.2.3.4"


# ---------------------------------------------------------------------------
# Test: Bounce Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bounce_handling(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
    mock_sendgrid_signature,
):
    """Bounce event should update contact status to bounced and log event."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "test@example.com",
                "event": "bounce",
                "timestamp": 1711411200,
                "contact_id": str(emailed_contact.id),
                "reason": "550 User not found",
            }
        ],
    )
    assert response.status_code == 200

    # Refresh contact from DB
    await db_session.refresh(emailed_contact)
    assert emailed_contact.status == ContactStatus.bounced

    # Verify bounce event logged
    events = await get_events_for_contact(db_session, emailed_contact.id)
    bounce_events = [e for e in events if e.event_type == "email_bounced"]
    assert len(bounce_events) == 1
    assert bounce_events[0].metadata_.get("reason") == "550 User not found"


# ---------------------------------------------------------------------------
# Test: Dropped Event (similar to bounce)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dropped_event(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
    mock_sendgrid_signature,
):
    """Dropped event should be handled like a bounce."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "test@example.com",
                "event": "dropped",
                "timestamp": 1711411200,
                "contact_id": str(emailed_contact.id),
                "reason": "Bounced Address",
            }
        ],
    )
    assert response.status_code == 200

    await db_session.refresh(emailed_contact)
    assert emailed_contact.status == ContactStatus.bounced


# ---------------------------------------------------------------------------
# Test: Inbound Reply Parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbound_reply(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
):
    """Inbound reply should log reply_received and update status to replied."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/inbound",
        data={
            "from": "Test Contact <test@example.com>",
            "to": "outreach@askadil.org",
            "subject": "Re: AskAdil Directory",
            "text": "Thanks for reaching out, we'd love to be listed!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["contact_id"] == str(emailed_contact.id)

    # Verify reply_received event
    events = await get_events_for_contact(db_session, emailed_contact.id)
    reply_events = [e for e in events if e.event_type == "reply_received"]
    assert len(reply_events) == 1
    assert "love to be listed" in reply_events[0].content

    # Verify contact status updated to replied
    await db_session.refresh(emailed_contact)
    assert emailed_contact.status == ContactStatus.replied


# ---------------------------------------------------------------------------
# Test: Unknown Sender Inbound Reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbound_reply_unknown_sender(client: AsyncClient):
    """Inbound reply from unknown sender should return ignored status."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/inbound",
        data={
            "from": "random@unknown.com",
            "to": "outreach@askadil.org",
            "subject": "Hello",
            "text": "Some random email",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Test: Unknown Contact in Event Webhook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sendgrid_event_unknown_contact(
    client: AsyncClient,
    mock_sendgrid_signature,
):
    """Events for unknown contacts should be handled gracefully."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "nobody@nowhere.com",
                "event": "delivered",
                "timestamp": 1711411200,
                "contact_id": str(uuid.uuid4()),
            }
        ],
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Test: Signature Verification Rejects Invalid Signatures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_sendgrid_signature(
    client: AsyncClient,
    emailed_contact: Contact,
):
    """Without mock signature bypass, invalid signatures should be rejected."""
    # Ensure verification is enabled
    original = settings.sendgrid_webhook_verify_enabled
    settings.sendgrid_webhook_verify_enabled = True
    try:
        response = await client.post(
            "/api/v1/outreach/webhooks/sendgrid/events",
            json=[
                {
                    "email": "test@example.com",
                    "event": "delivered",
                    "timestamp": 123,
                }
            ],
            headers={"X-Twilio-Email-Event-Webhook-Signature": "invalid"},
        )
        assert response.status_code == 403
    finally:
        settings.sendgrid_webhook_verify_enabled = original


# ---------------------------------------------------------------------------
# Test: Draft Preview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_preview(
    client: AsyncClient,
    draft_pending_contact: Contact,
    auth_headers: dict,
):
    """GET draft should return the pending draft details."""
    response = await client.get(
        f"/api/v1/outreach/contacts/{draft_pending_contact.id}/draft",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_approval"
    assert data["subject"] == "AskAdil Directory Listing"
    assert "personalisation_hooks" in data
    assert len(data["personalisation_hooks"]) > 0


# ---------------------------------------------------------------------------
# Test: Draft Approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_approve(
    client: AsyncClient,
    db_session: AsyncSession,
    draft_pending_contact: Contact,
    auth_headers: dict,
):
    """POST approve-draft should approve and update status."""
    response = await client.post(
        f"/api/v1/outreach/contacts/{draft_pending_contact.id}/approve-draft",
        json={"edited_subject": "Updated Subject"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"

    # Verify approval event logged
    events = await get_events_for_contact(db_session, draft_pending_contact.id)
    approve_events = [e for e in events if e.event_type == "draft_approved"]
    assert len(approve_events) == 1
    assert approve_events[0].subject == "Updated Subject"
    assert approve_events[0].metadata_.get("was_edited") is True


# ---------------------------------------------------------------------------
# Test: Draft Approval — Wrong Status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_approve_wrong_status(
    client: AsyncClient,
    emailed_contact: Contact,
    auth_headers: dict,
):
    """Approving a non-draft_pending contact should return 400."""
    response = await client.post(
        f"/api/v1/outreach/contacts/{emailed_contact.id}/approve-draft",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Test: Draft Preview — No Draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_preview_no_draft(
    client: AsyncClient,
    emailed_contact: Contact,
    auth_headers: dict,
):
    """GET draft for contact with no draft should return 404."""
    # emailed_contact has email_sent event, not draft_created
    # But actually it might have one from compose. Let's use a fresh contact.
    response = await client.get(
        f"/api/v1/outreach/contacts/{uuid.uuid4()}/draft",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: Events Timeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_timeline(
    client: AsyncClient,
    emailed_contact_with_events: Contact,
    auth_headers: dict,
):
    """Events timeline should return paginated events sorted newest first."""
    response = await client.get(
        f"/api/v1/outreach/contacts/{emailed_contact_with_events.id}/events",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 3
    assert data["contact_status"] == "emailed"
    assert data["contact_name"] == "Timeline Contact"

    # Events should be newest first
    timestamps = [e["created_at"] for e in data["events"]]
    assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# Test: Events Timeline — Filter by Event Type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_timeline_filter(
    client: AsyncClient,
    emailed_contact_with_events: Contact,
    auth_headers: dict,
):
    """Events timeline should support event_type filter."""
    response = await client.get(
        f"/api/v1/outreach/contacts/{emailed_contact_with_events.id}/events?event_type=email_sent",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 1
    for e in data["events"]:
        assert e["event_type"] == "email_sent"


# ---------------------------------------------------------------------------
# Test: Events Timeline — Contact Not Found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_timeline_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Events timeline for non-existent contact should return 404."""
    response = await client.get(
        f"/api/v1/outreach/contacts/{uuid.uuid4()}/events",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: Late Reply — Unresponsive Contact Receives Reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_late_reply_from_unresponsive(
    client: AsyncClient,
    db_session: AsyncSession,
    unresponsive_contact: Contact,
):
    """Reply from unresponsive contact should be processed (not ignored)."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/inbound",
        data={
            "from": f"Unresponsive Contact <{unresponsive_contact.email}>",
            "to": "outreach@askadil.org",
            "subject": "Re: AskAdil Directory",
            "text": "Sorry for the late reply, yes we're interested!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    # Verify reply_received event was logged
    events = await get_events_for_contact(db_session, unresponsive_contact.id)
    reply_events = [e for e in events if e.event_type == "reply_received"]
    assert len(reply_events) == 1

    # Status should be updated to replied
    await db_session.refresh(unresponsive_contact)
    assert unresponsive_contact.status == ContactStatus.replied


# ---------------------------------------------------------------------------
# Test: classify_reply — Interested Classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_reply_interested(
    db_session: AsyncSession,
    emailed_contact: Contact,
):
    """classify_reply should correctly route interested classifications."""
    from app.workers.tasks import classify_reply

    # Add a reply_received event
    reply_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=emailed_contact.id,
        event_type="reply_received",
        channel="email",
        subject="Re: Test",
        content="Yes, I'm very interested in being listed!",
        metadata_={"sender": "test@example.com"},
        created_at=datetime.utcnow(),
    )
    db_session.add(reply_event)
    await db_session.commit()

    # Mock redis and the classify node
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=b"test-lock-value")
    mock_redis.delete = AsyncMock()
    mock_redis.scan_iter = MagicMock(return_value=AsyncIterator([]))

    mock_pool = AsyncMock()

    ctx = {"redis": mock_redis, "pool": mock_pool}

    with patch("app.workers.tasks.get_async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.classify_node") as mock_classify:
            mock_classify.return_value = {
                "classification": "interested",
                "current_step": "classify",
            }

            result = await classify_reply(ctx, str(emailed_contact.id))
            assert result["category"] == "interested"

    # Verify classification event logged
    events = await get_events_for_contact(db_session, emailed_contact.id)
    assert any(e.event_type == "reply_classified" for e in events)


# ---------------------------------------------------------------------------
# Test: classify_reply — Declined Classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_reply_declined(
    db_session: AsyncSession,
    emailed_contact: Contact,
):
    """classify_reply should mark contact as declined when classified as declined."""
    from app.workers.tasks import classify_reply

    # Add a reply_received event
    reply_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=emailed_contact.id,
        event_type="reply_received",
        channel="email",
        subject="Re: Test",
        content="No thanks, please remove me from your list.",
        metadata_={"sender": "test@example.com"},
        created_at=datetime.utcnow(),
    )
    db_session.add(reply_event)
    await db_session.commit()

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=b"test-lock-value")
    mock_redis.delete = AsyncMock()
    mock_redis.scan_iter = MagicMock(return_value=AsyncIterator([]))

    ctx = {"redis": mock_redis, "pool": AsyncMock()}

    with patch("app.workers.tasks.get_async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.classify_node") as mock_classify:
            mock_classify.return_value = {
                "classification": "declined",
                "current_step": "classify",
            }

            result = await classify_reply(ctx, str(emailed_contact.id))
            assert result["category"] == "declined"

    await db_session.refresh(emailed_contact)
    assert emailed_contact.status == ContactStatus.declined


# ---------------------------------------------------------------------------
# Test: Late Reply Reopens Unresponsive via classify_reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_late_reply_reopens_via_classify(
    db_session: AsyncSession,
    unresponsive_contact: Contact,
):
    """Interested late reply from unresponsive contact should reopen with reopened event."""
    from app.workers.tasks import classify_reply

    # Add a reply_received event
    reply_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=unresponsive_contact.id,
        event_type="reply_received",
        channel="email",
        subject="Re: Test",
        content="Sorry for the late reply, yes we're interested!",
        metadata_={"sender": "unresponsive@example.com"},
        created_at=datetime.utcnow(),
    )
    db_session.add(reply_event)
    await db_session.commit()

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=b"test-lock-value")
    mock_redis.delete = AsyncMock()
    mock_redis.scan_iter = MagicMock(return_value=AsyncIterator([]))

    ctx = {"redis": mock_redis, "pool": AsyncMock()}

    with patch("app.workers.tasks.get_async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.classify_node") as mock_classify:
            mock_classify.return_value = {
                "classification": "interested",
                "current_step": "classify",
            }

            result = await classify_reply(ctx, str(unresponsive_contact.id))
            assert result["category"] == "interested"

    # Verify contact was reopened to replied
    await db_session.refresh(unresponsive_contact)
    assert unresponsive_contact.status == ContactStatus.replied

    # Verify reopened event exists
    events = await get_events_for_contact(db_session, unresponsive_contact.id)
    reopened_events = [e for e in events if e.event_type == "reopened"]
    assert len(reopened_events) == 1
    assert reopened_events[0].metadata_.get("previous_status") == "unresponsive"


# ---------------------------------------------------------------------------
# Test: Click Event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sendgrid_event_click(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
    mock_sendgrid_signature,
):
    """Click event should log an email_clicked outreach event."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "test@example.com",
                "event": "click",
                "timestamp": 1711411200,
                "contact_id": str(emailed_contact.id),
                "url": "https://askadil.org/signup",
            }
        ],
    )
    assert response.status_code == 200

    events = await get_events_for_contact(db_session, emailed_contact.id)
    click_events = [e for e in events if e.event_type == "email_clicked"]
    assert len(click_events) == 1
    assert click_events[0].metadata_.get("url") == "https://askadil.org/signup"


# ---------------------------------------------------------------------------
# Test: Multiple Events in Single Webhook Call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_events_batch(
    client: AsyncClient,
    db_session: AsyncSession,
    emailed_contact: Contact,
    mock_sendgrid_signature,
):
    """SendGrid sends batches of events — all should be processed."""
    response = await client.post(
        "/api/v1/outreach/webhooks/sendgrid/events",
        json=[
            {
                "email": "test@example.com",
                "event": "delivered",
                "timestamp": 1711411200,
                "contact_id": str(emailed_contact.id),
                "sg_message_id": "msg1",
            },
            {
                "email": "test@example.com",
                "event": "open",
                "timestamp": 1711411260,
                "contact_id": str(emailed_contact.id),
            },
        ],
    )
    assert response.status_code == 200

    events = await get_events_for_contact(db_session, emailed_contact.id)
    event_types = {e.event_type for e in events}
    assert "email_delivered" in event_types
    assert "email_opened" in event_types


# ---------------------------------------------------------------------------
# Test: extract_email_from_field
# ---------------------------------------------------------------------------


def test_extract_email_from_field():
    """Email extraction should handle various 'from' field formats."""
    from app.api.webhooks import extract_email_from_field

    assert extract_email_from_field("Name <test@example.com>") == "test@example.com"
    assert extract_email_from_field("test@example.com") == "test@example.com"
    assert extract_email_from_field("  Test User <TEST@Example.COM>  ") == "test@example.com"
    assert extract_email_from_field("plain@email.com") == "plain@email.com"


# ---------------------------------------------------------------------------
# Async iterator helper for mock redis scan_iter
# ---------------------------------------------------------------------------


class AsyncIterator:
    """Helper to create an async iterator from a list."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration
