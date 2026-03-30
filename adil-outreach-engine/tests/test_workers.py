"""Tests for arq worker tasks, rate limiter, idempotency, and campaign launch."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.outreach_event import OutreachEvent
from app.workers.rate_limiter import RateLimiter, sendgrid_limiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def fake_redis():
    """Provide a fakeredis async client."""
    redis = fakeredis.aioredis.FakeRedis()
    yield redis
    await redis.aclose()


@pytest.fixture
def arq_ctx(fake_redis):
    """Mock arq worker context."""
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()

    # Mock redis.lock() so evaluate_contact works with fakeredis
    mock_lock = AsyncMock()
    mock_lock.acquire = AsyncMock(return_value=True)
    mock_lock.release = AsyncMock(return_value=None)
    fake_redis.lock = MagicMock(return_value=mock_lock)

    return {"redis": fake_redis, "pool": pool}


@pytest.fixture
async def sample_campaign(db_session):
    """Create a sample campaign for testing."""
    campaign = Campaign(
        id=uuid.uuid4(),
        name="Test Campaign",
        slug=f"test-campaign-{uuid.uuid4().hex[:8]}",
        goal="signup",
        status="draft",
        templates={
            "initial": {
                "subject": "Hello {{contact_name}}",
                "body": "Hi there, {{personalised_intro}}",
            },
            "follow_up_1": {
                "subject": "Following up",
                "body": "Just checking in...",
            },
        },
        cadence=[
            {"day": 0, "action": "send_initial", "template": "initial"},
            {"day": 3, "action": "follow_up", "template": "follow_up_1"},
            {"day": 7, "action": "close"},
        ],
        llm_config={
            "research": {"provider": "gemini", "model": "gemini-pro"},
            "compose": {"provider": "anthropic", "model": "claude-3-haiku"},
        },
        sender_name="Test Sender",
        sender_email="test@example.com",
        reply_to="reply@example.com",
        auto_send=True,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def sample_contact(db_session, sample_campaign):
    """Create a sample contact linked to sample_campaign."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=sample_campaign.id,
        name="John Solicitor",
        email="john@example-law.com",
        firm_name="Example Law LLP",
        website="https://example-law.com",
        status="pending",
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def sample_contacts_pending(db_session, sample_campaign):
    """Create 3 pending contacts for launch testing."""
    contacts = []
    for i in range(3):
        contact = Contact(
            id=uuid.uuid4(),
            campaign_id=sample_campaign.id,
            name=f"Contact {i}",
            email=f"contact{i}@example.com",
            status="pending",
            current_cadence_step=0,
        )
        db_session.add(contact)
        contacts.append(contact)
    await db_session.commit()
    for c in contacts:
        await db_session.refresh(c)
    return contacts


# ---------------------------------------------------------------------------
# Rate Limiter Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit(fake_redis):
    """acquire() returns True when under the limit."""
    limiter = RateLimiter(fake_redis, "test", max_requests=5, window_seconds=60)
    for _ in range(5):
        assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit(fake_redis):
    """acquire() returns False when limit exceeded."""
    limiter = RateLimiter(fake_redis, "test_block", max_requests=2, window_seconds=60)
    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is False


@pytest.mark.asyncio
async def test_rate_limiter_different_resources(fake_redis):
    """Different resource names use separate counters."""
    limiter_a = RateLimiter(fake_redis, "res_a", max_requests=1, window_seconds=60)
    limiter_b = RateLimiter(fake_redis, "res_b", max_requests=1, window_seconds=60)
    assert await limiter_a.acquire() is True
    assert await limiter_b.acquire() is True
    assert await limiter_a.acquire() is False
    assert await limiter_b.acquire() is False


@pytest.mark.asyncio
async def test_wait_for_slot_timeout(fake_redis):
    """wait_for_slot returns False when limit not freed within timeout."""
    limiter = RateLimiter(fake_redis, "test_timeout", max_requests=1, window_seconds=3600)
    await limiter.acquire()  # Use the single slot
    result = await limiter.wait_for_slot(max_wait=0.5)
    assert result is False


@pytest.mark.asyncio
async def test_sendgrid_limiter_factory(fake_redis):
    """sendgrid_limiter factory creates correctly configured limiter."""
    limiter = sendgrid_limiter(fake_redis, daily_limit=2)
    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is False


# ---------------------------------------------------------------------------
# Email Idempotency Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_idempotency_check(db_session, sample_contact):
    """check_idempotency returns existing event when key matches."""
    from app.services.email import EmailService

    svc = EmailService()

    # No existing event — should return None
    result = await svc.check_idempotency(db_session, f"{sample_contact.id}:0")
    assert result is None

    # Create an email_sent event with the idempotency key
    event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=sample_contact.id,
        event_type="email_sent",
        channel="email",
        metadata_={"idempotency_key": f"{sample_contact.id}:0", "sendgrid_message_id": "msg123"},
        created_at=datetime.utcnow(),
    )
    db_session.add(event)
    await db_session.commit()

    # Now should find the existing event
    result = await svc.check_idempotency(db_session, f"{sample_contact.id}:0")
    assert result is not None
    assert result.id == event.id


@pytest.mark.asyncio
async def test_email_idempotency_different_cadence_step(db_session, sample_contact):
    """Different cadence steps produce different idempotency keys."""
    from app.services.email import EmailService

    svc = EmailService()

    # Create event for step 0
    event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=sample_contact.id,
        event_type="email_sent",
        channel="email",
        metadata_={"idempotency_key": f"{sample_contact.id}:0"},
        created_at=datetime.utcnow(),
    )
    db_session.add(event)
    await db_session.commit()

    # Step 0 should find it
    result = await svc.check_idempotency(db_session, f"{sample_contact.id}:0")
    assert result is not None

    # Step 1 should NOT find it
    result = await svc.check_idempotency(db_session, f"{sample_contact.id}:1")
    assert result is None


# ---------------------------------------------------------------------------
# evaluate_contact Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_skips_already_converted(arq_ctx, db_session, sample_contact, sample_campaign):
    """If contact already converted, evaluate should exit immediately."""
    sample_contact.status = "converted"
    sample_campaign.status = "active"
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import evaluate_contact

        await evaluate_contact(arq_ctx, str(sample_contact.id), 1)

    # No jobs enqueued
    arq_ctx["pool"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_no_reply_enqueues_follow_up(arq_ctx, db_session, sample_contact, sample_campaign):
    """No reply + cadence continues -> enqueue send_follow_up."""
    sample_contact.status = "emailed"
    sample_campaign.status = "active"
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import evaluate_contact

        await evaluate_contact(arq_ctx, str(sample_contact.id), 1)

    arq_ctx["pool"].enqueue_job.assert_called_once_with("send_follow_up", str(sample_contact.id), 1)


@pytest.mark.asyncio
async def test_evaluate_cadence_exhausted_marks_unresponsive(arq_ctx, db_session, sample_contact, sample_campaign):
    """No reply + close action -> mark unresponsive."""
    sample_contact.status = "emailed"
    sample_campaign.status = "active"
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import evaluate_contact

        # cadence_step=2 has action="close"
        await evaluate_contact(arq_ctx, str(sample_contact.id), 2)

    # Verify contact marked unresponsive
    await db_session.refresh(sample_contact)
    assert sample_contact.status == "unresponsive"

    # No follow-up enqueued
    arq_ctx["pool"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_with_reply_enqueues_classify(arq_ctx, db_session, sample_contact, sample_campaign):
    """Reply exists after last email -> enqueue classify_reply."""
    sample_contact.status = "emailed"
    sample_campaign.status = "active"
    await db_session.commit()

    # Create an email_sent event
    sent_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=sample_contact.id,
        event_type="email_sent",
        channel="email",
        metadata_={"sendgrid_message_id": "msg1"},
        created_at=datetime(2026, 3, 1, 10, 0, 0),
    )
    db_session.add(sent_event)

    # Create a reply_received event AFTER the send
    reply_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=sample_contact.id,
        event_type="reply_received",
        channel="email",
        content="Thanks, I am interested",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
    )
    db_session.add(reply_event)
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import evaluate_contact

        await evaluate_contact(arq_ctx, str(sample_contact.id), 1)

    await db_session.refresh(sample_contact)
    assert sample_contact.status == "replied"
    arq_ctx["pool"].enqueue_job.assert_called_once_with("classify_reply", str(sample_contact.id))


# ---------------------------------------------------------------------------
# Campaign Launch Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_validates_pending_contacts(arq_ctx, db_session, sample_campaign):
    """Launch with no pending contacts should raise."""
    sample_campaign.sender_email = "test@example.com"
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import launch_campaign

        with pytest.raises(ValueError, match="No contacts with status 'pending'"):
            await launch_campaign(arq_ctx, str(sample_campaign.id))


@pytest.mark.asyncio
async def test_launch_validates_templates(arq_ctx, db_session, sample_campaign, sample_contact):
    """Launch with missing template should raise."""
    sample_campaign.cadence = [{"day": 0, "template": "nonexistent_template"}]
    sample_campaign.templates = {"initial": {"subject": "Test", "body": "Body"}}
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import launch_campaign

        with pytest.raises(ValueError, match="Template 'nonexistent_template'"):
            await launch_campaign(arq_ctx, str(sample_campaign.id))


@pytest.mark.asyncio
async def test_launch_validates_sender_email(arq_ctx, db_session, sample_campaign, sample_contact):
    """Launch without sender_email should raise."""
    sample_campaign.sender_email = None
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import launch_campaign

        with pytest.raises(ValueError, match="sender_email is required"):
            await launch_campaign(arq_ctx, str(sample_campaign.id))


@pytest.mark.asyncio
async def test_launch_staggered_enqueue(arq_ctx, db_session, sample_campaign, sample_contacts_pending):
    """Verify contacts are enqueued with increasing _defer_by."""
    with (
        patch("app.workers.tasks.get_async_session") as mock_session,
        patch("app.workers.tasks.app_settings") as mock_settings,
    ):
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_settings.gemini_api_key = "fake-key"
        mock_settings.anthropic_api_key = "fake-key"
        mock_settings.openai_api_key = "fake-key"
        from app.workers.tasks import launch_campaign

        result = await launch_campaign(arq_ctx, str(sample_campaign.id))

    assert result["enqueued"] == len(sample_contacts_pending)
    assert result["campaign_status"] == "active"

    calls = arq_ctx["pool"].enqueue_job.call_args_list
    assert len(calls) == len(sample_contacts_pending)
    for i, call in enumerate(calls):
        assert call.kwargs["_defer_by"] == timedelta(seconds=i * 5)
        assert call.args[0] == "research_contact"


# ---------------------------------------------------------------------------
# Follow-up Scheduling Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_schedules_evaluate(arq_ctx, db_session, sample_contact, sample_campaign):
    """After send_email, evaluate_contact should be enqueued with correct _defer_by."""
    # Set campaign active and contact to emailed-like state
    sample_campaign.status = "active"
    sample_campaign.cadence = [
        {"day": 0, "action": "send_initial", "template": "initial"},
        {"day": 3, "action": "follow_up", "template": "follow_up_1"},
    ]
    await db_session.commit()

    # Create a draft event so send_email can find it
    draft_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=sample_contact.id,
        event_type="draft_created",
        channel="system",
        subject="Test Subject",
        content="<p>Test body</p>",
        metadata_={"template_key": "initial", "cadence_step": 0},
        created_at=datetime.utcnow(),
    )
    db_session.add(draft_event)
    await db_session.commit()

    with (
        patch("app.workers.tasks.get_async_session") as mock_session,
        patch("app.workers.tasks.EmailService") as MockEmailSvc,
    ):
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_svc_instance = AsyncMock()
        mock_svc_instance.check_idempotency = AsyncMock(return_value=None)
        mock_svc_instance.send_email = AsyncMock(
            return_value={"status": "sent", "sendgrid_message_id": "msg123", "status_code": 202}
        )
        MockEmailSvc.return_value = mock_svc_instance

        from app.workers.tasks import send_email_task

        await send_email_task(arq_ctx, str(sample_contact.id), 0)

    # Verify evaluate_contact enqueued with 3 days defer
    arq_ctx["pool"].enqueue_job.assert_called_with(
        "evaluate_contact",
        str(sample_contact.id),
        1,
        _defer_by=timedelta(days=3),
    )


@pytest.mark.asyncio
async def test_send_email_idempotent_skip(arq_ctx, db_session, sample_contact, sample_campaign):
    """send_email_task skips when idempotency key already exists."""
    sample_campaign.status = "active"
    await db_session.commit()

    # Create an existing email_sent event with the idempotency key
    existing_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=sample_contact.id,
        event_type="email_sent",
        channel="email",
        metadata_={
            "idempotency_key": f"{sample_contact.id}:0",
            "sendgrid_message_id": "already_sent_msg",
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(existing_event)
    await db_session.commit()

    with (
        patch("app.workers.tasks.get_async_session") as mock_session,
        patch("app.workers.tasks.EmailService") as MockEmailSvc,
    ):
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_svc_instance = AsyncMock()
        mock_svc_instance.check_idempotency = AsyncMock(return_value=existing_event)
        MockEmailSvc.return_value = mock_svc_instance

        from app.workers.tasks import send_email_task

        await send_email_task(arq_ctx, str(sample_contact.id), 0)

    # send_email should NOT have been called on the service
    mock_svc_instance.send_email.assert_not_called()
    # No jobs enqueued
    arq_ctx["pool"].enqueue_job.assert_not_called()


# ---------------------------------------------------------------------------
# Redis Distributed Lock Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_lock_released_on_completion(arq_ctx, db_session, sample_contact, sample_campaign):
    """Lock should be released after evaluate_contact completes."""
    sample_contact.status = "emailed"
    sample_campaign.status = "active"
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import evaluate_contact

        await evaluate_contact(arq_ctx, str(sample_contact.id), 1)

    # Verify the lock was acquired and released during evaluate_contact
    redis = arq_ctx["redis"]
    lock_key = f"lock:contact:{sample_contact.id}"
    redis.lock.assert_called_with(lock_key, timeout=60, blocking_timeout=10)
    mock_lock = redis.lock.return_value
    mock_lock.acquire.assert_awaited_once()
    mock_lock.release.assert_awaited_once()


# ---------------------------------------------------------------------------
# Follow-up Template Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_up_guard_wrong_status(arq_ctx, db_session, sample_contact, sample_campaign):
    """send_follow_up should return early if contact is not in 'emailed' status."""
    sample_contact.status = "replied"
    sample_campaign.status = "active"
    await db_session.commit()

    with patch("app.workers.tasks.get_async_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.workers.tasks import send_follow_up

        await send_follow_up(arq_ctx, str(sample_contact.id), 1)

    # No jobs should be enqueued
    arq_ctx["pool"].enqueue_job.assert_not_called()


# ---------------------------------------------------------------------------
# Dry-Run Tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def dry_run_campaign(db_session):
    """Create a dry-run campaign for testing."""
    campaign = Campaign(
        id=uuid.uuid4(),
        name="Dry Run Campaign",
        slug=f"dry-run-{uuid.uuid4().hex[:8]}",
        goal="signup",
        status="active",
        templates={
            "initial": {
                "subject": "Hello {{contact_name}}",
                "body": "Hi there, this is a test.",
            },
        },
        cadence=[
            {"day": 0, "action": "send_initial", "template": "initial"},
            {"day": 3, "action": "follow_up", "template": "follow_up_1"},
        ],
        llm_config={
            "research": {"provider": "gemini", "model": "gemini-pro"},
            "compose": {"provider": "anthropic", "model": "claude-3-haiku"},
        },
        sender_name="Dry Run Sender",
        sender_email="dryrun@example.com",
        reply_to="dryrun-reply@example.com",
        auto_send=True,
        dry_run=True,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def dry_run_contact(db_session, dry_run_campaign):
    """Create a contact linked to the dry-run campaign."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=dry_run_campaign.id,
        name="Jane Solicitor",
        email="jane@example-law.com",
        firm_name="Example Law LLP",
        website="https://example-law.com",
        status="emailed",
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.mark.asyncio
async def test_send_email_dry_run_skips_sendgrid(arq_ctx, db_session, dry_run_contact, dry_run_campaign):
    """In dry_run mode, send_email_task should NOT call SendGrid."""
    # Create a draft event
    draft_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=dry_run_contact.id,
        event_type="draft_created",
        channel="system",
        subject="Dry Run Subject",
        content="<p>Dry run body</p>",
        metadata_={"template_key": "initial", "cadence_step": 0},
        created_at=datetime.utcnow(),
    )
    db_session.add(draft_event)
    await db_session.commit()

    with (
        patch("app.workers.tasks.get_async_session") as mock_session,
        patch("app.workers.tasks.EmailService") as MockEmailSvc,
    ):
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_svc_instance = AsyncMock()
        MockEmailSvc.return_value = mock_svc_instance

        from app.workers.tasks import send_email_task

        await send_email_task(arq_ctx, str(dry_run_contact.id), 0)

    # SendGrid should NEVER have been called
    mock_svc_instance.send_email.assert_not_called()
    mock_svc_instance.check_idempotency.assert_not_called()

    # Contact should still move to "emailed"
    await db_session.refresh(dry_run_contact)
    assert dry_run_contact.status == "emailed"


@pytest.mark.asyncio
async def test_send_email_dry_run_logs_event(arq_ctx, db_session, dry_run_contact, dry_run_campaign):
    """In dry_run mode, send_email_task should log an email_dry_run event with full content."""
    # Create a draft event
    draft_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=dry_run_contact.id,
        event_type="draft_created",
        channel="system",
        subject="Dry Run Subject",
        content="<p>Dry run body</p>",
        metadata_={"template_key": "initial", "cadence_step": 0},
        created_at=datetime.utcnow(),
    )
    db_session.add(draft_event)
    await db_session.commit()

    with (
        patch("app.workers.tasks.get_async_session") as mock_session,
        patch("app.workers.tasks.EmailService") as MockEmailSvc,
    ):
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_svc_instance = AsyncMock()
        MockEmailSvc.return_value = mock_svc_instance

        from app.workers.tasks import send_email_task

        await send_email_task(arq_ctx, str(dry_run_contact.id), 0)

    # Check for the email_dry_run event
    stmt = select(OutreachEvent).where(
        OutreachEvent.contact_id == dry_run_contact.id,
        OutreachEvent.event_type == "email_dry_run",
    )
    result = await db_session.execute(stmt)
    dry_run_event = result.scalar_one_or_none()

    assert dry_run_event is not None
    assert dry_run_event.subject == "Dry Run Subject"
    assert dry_run_event.content == "<p>Dry run body</p>"
    assert dry_run_event.metadata_["to_email"] == "jane@example-law.com"
    assert dry_run_event.metadata_["from_email"] == "dryrun@example.com"
    assert dry_run_event.metadata_["from_name"] == "Dry Run Sender"
    assert dry_run_event.metadata_["reply_to"] == "dryrun-reply@example.com"
    assert dry_run_event.metadata_["dry_run"] is True
    assert dry_run_event.metadata_["cadence_step"] == 0
