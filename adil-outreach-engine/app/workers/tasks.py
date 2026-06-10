"""Arq worker tasks for background processing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes.classify import classify_node
from app.agents.nodes.compose import compose_node
from app.agents.nodes.research import research_node
from app.agents.state import OutreachState
from app.config import settings as app_settings
from app.database import get_async_session
from app.models.campaign import Campaign, CampaignGoal
from app.models.contact import Contact, ContactStatus
from app.models.conversion import Conversion
from app.models.outreach_event import EventChannel, EventType, OutreachEvent
from app.services.bounce import cancel_deferred_jobs, handle_bounce_from_reply
from app.services.email import EmailService, SendGridPermanentError, SendGridTransientError
from app.services.events import get_contact_events, get_latest_event, log_outreach_event
from app.workers.locks import redis_lock
from app.workers.rate_limiter import llm_limiter, scrape_limiter, sendgrid_limiter

logger = logging.getLogger(__name__)

# Backoff delays in seconds: 5s, 30s, 5min
BACKOFF_DELAYS = [5, 30, 300]


async def fire_conversion_webhook(
    ctx: dict,
    conversion_id: str,
    webhook_url: str,
    attempt: int = 1,
) -> None:
    """Fire outbound webhook on conversion with retry logic.

    Uses arq task re-enqueue for explicit control over backoff delays.
    """
    from app.database import async_session

    async with async_session() as db:
        await _fire_webhook_impl(ctx, conversion_id, webhook_url, attempt, db)


async def fire_conversion_webhook_sync(
    conversion_id: str,
    webhook_url: str,
    db: AsyncSession,
) -> None:
    """Synchronous version that works within an existing DB session context.

    Used when arq is not available (e.g., during testing or direct calls).
    """
    await _fire_webhook_impl({}, conversion_id, webhook_url, 1, db)


async def _fire_webhook_impl(
    ctx: dict,
    conversion_id: str,
    webhook_url: str,
    attempt: int,
    db: AsyncSession,
) -> None:
    """Internal implementation of webhook firing with retry."""
    import uuid

    conversion_uuid = uuid.UUID(conversion_id) if isinstance(conversion_id, str) else conversion_id
    conversion = await db.get(Conversion, conversion_uuid)
    if not conversion:
        logger.error("Conversion %s not found for webhook", conversion_id)
        return

    # Load contact and campaign
    from app.models.contact import Contact
    from app.models.campaign import Campaign

    contact = await db.get(Contact, conversion.contact_id)
    if not contact:
        logger.error("Contact not found for conversion %s", conversion_id)
        return

    campaign = await db.get(Campaign, contact.campaign_id)

    # Build webhook payload
    payload = {
        "event": "conversion.completed",
        "conversion_id": str(conversion.id),
        "type": conversion.type.value,
        "campaign_id": str(campaign.id) if campaign else None,
        "campaign_slug": campaign.slug if campaign else None,
        "contact": {
            "id": str(contact.id),
            "name": contact.name,
            "email": contact.email,
            "firm_name": contact.firm_name,
            "metadata": contact.metadata_,
        },
        "data": conversion.data,
        "converted_at": conversion.created_at.isoformat() if conversion.created_at else None,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                webhook_url,
                json=payload,
                timeout=30.0,
                headers={
                    "Content-Type": "application/json",
                    "X-Outreach-Event": "conversion.completed",
                },
            )
            resp.raise_for_status()

        # Success: log webhook_sent event
        event = OutreachEvent(
            contact_id=contact.id,
            event_type=EventType.webhook_sent,
            channel=EventChannel.webhook,
            subject="Conversion webhook sent",
            metadata_={
                "webhook_url": webhook_url,
                "status_code": resp.status_code,
                "conversion_id": str(conversion.id),
            },
        )
        db.add(event)
        await db.commit()
        logger.info("Conversion webhook sent for %s (attempt %d)", conversion_id, attempt)

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.warning(
            "Webhook attempt %d failed for conversion %s: %s",
            attempt,
            conversion_id,
            str(e),
        )
        if attempt < 3:
            # Re-enqueue with backoff if arq context available
            delay = BACKOFF_DELAYS[attempt - 1]
            redis = ctx.get("redis")
            if redis:
                await redis.enqueue_job(
                    "fire_conversion_webhook",
                    conversion_id,
                    webhook_url,
                    attempt + 1,
                    _defer_by=timedelta(seconds=delay),
                )
                logger.info("Re-enqueued webhook for %s (attempt %d, delay %ds)", conversion_id, attempt + 1, delay)
            else:
                logger.warning("No arq redis context available for retry")
        else:
            # Final failure: log webhook_failed event
            event = OutreachEvent(
                contact_id=contact.id,
                event_type=EventType.webhook_failed,
                channel=EventChannel.webhook,
                subject="Conversion webhook failed",
                metadata_={
                    "webhook_url": webhook_url,
                    "error": str(e),
                    "attempts": 3,
                    "conversion_id": str(conversion.id),
                },
            )
            db.add(event)
            await db.commit()
            logger.error("Webhook permanently failed for conversion %s after 3 attempts", conversion_id)


# ---------------------------------------------------------------------------
# Task 4: research_contact
# ---------------------------------------------------------------------------


async def research_contact(ctx, contact_id: str):
    """Research a contact using LLM + scraping tools, then enqueue compose."""
    redis = ctx["redis"]

    async with get_async_session() as db:
        # Fetch contact
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact or contact.status != "pending":
            return  # Already processed or doesn't exist

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign or campaign.status != "active":
            return

        # Rate limiting — scrape domain
        if contact.website:
            domain = urlparse(contact.website).netloc
            limiter = scrape_limiter(redis, domain)
            if not await limiter.wait_for_slot(max_wait=30):
                raise Exception(f"Rate limit timeout for scraping {domain}")

        # Rate limiting — LLM provider
        llm_config = campaign.llm_config or {}
        research_config = llm_config.get("research", {})
        provider = research_config.get("provider", "gemini")
        llm_limit = llm_limiter(redis, provider)
        if not await llm_limit.wait_for_slot(max_wait=60):
            raise Exception(f"Rate limit timeout for LLM provider {provider}")

        # Update status
        contact.status = "researching"
        await db.commit()

        try:
            # Build state and run research node
            state = OutreachState(
                contact_id=str(contact.id),
                campaign_id=str(campaign.id),
                contact=contact.to_dict(),
                campaign=campaign.to_dict(),
                research_data={},
                draft_subject="",
                draft_body="",
                reply_text="",
                classification="",
                current_step="research",
                error="",
            )

            result_state = await research_node(state)

            # Save research data
            contact.research_data = result_state["research_data"]
            contact.status = "ready"

            # Log event
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.research_completed,
                channel=EventChannel.system,
                metadata_={"research_keys": list(result_state["research_data"].keys())},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()

            # Enqueue compose
            pool = ctx["pool"]
            await pool.enqueue_job("compose_email", str(contact.id))

        except Exception as e:
            contact.status = "pending"
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.research_failed,
                channel=EventChannel.system,
                metadata_={"error": str(e)},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            raise  # Let arq retry


# ---------------------------------------------------------------------------
# Task 5: compose_email
# ---------------------------------------------------------------------------


async def compose_email(ctx, contact_id: str):
    """Compose a personalised email using LLM, then enqueue send or set draft_pending."""
    redis = ctx["redis"]

    async with get_async_session() as db:
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact or contact.status != "ready":
            return

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign or campaign.status != "active":
            return

        # Rate limit LLM
        llm_config = campaign.llm_config or {}
        compose_config = llm_config.get("compose", {})
        provider = compose_config.get("provider", "anthropic")
        limiter = llm_limiter(redis, provider)
        if not await limiter.wait_for_slot(max_wait=60):
            raise Exception(f"Rate limit timeout for LLM provider {provider}")

        # Determine template for current cadence step
        cadence_step = contact.current_cadence_step or 0
        cadence = campaign.cadence or []
        if cadence_step < len(cadence):
            step_config = cadence[cadence_step]
            template_key = step_config.get("template", "initial")
        else:
            template_key = "initial"
        templates = campaign.templates or {}
        _template = templates.get(template_key, {})

        # Build state and run compose node
        state = OutreachState(
            contact_id=str(contact.id),
            campaign_id=str(campaign.id),
            contact=contact.to_dict(),
            campaign=campaign.to_dict(),
            research_data=contact.research_data or {},
            draft_subject="",
            draft_body="",
            reply_text="",
            classification="",
            current_step="compose",
            error="",
        )

        try:
            result_state = await compose_node(state)

            # Log draft event
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.draft_created,
                channel=EventChannel.system,
                subject=result_state["draft_subject"],
                content=result_state["draft_body"],
                metadata_={
                    "template_key": template_key,
                    "cadence_step": cadence_step,
                },
                created_at=datetime.utcnow(),
            )
            db.add(event)

            if campaign.auto_send:
                contact.status = "emailed"  # Will be confirmed by send_email
                await db.commit()
                pool = ctx["pool"]
                await pool.enqueue_job(
                    "send_email_task",
                    str(contact.id),
                    cadence_step,
                )
            else:
                contact.status = "draft_pending"
                await db.commit()

        except Exception as e:
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.compose_failed,
                channel=EventChannel.system,
                metadata_={"error": str(e)},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            raise


# ---------------------------------------------------------------------------
# Task 6: send_email_task
# ---------------------------------------------------------------------------


async def send_email_task(ctx, contact_id: str, cadence_step: int):
    """Send an email via SendGrid with idempotency, threading, and follow-up scheduling."""
    redis = ctx["redis"]
    idempotency_key = f"{contact_id}:{cadence_step}"

    async with get_async_session() as db:
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact:
            return

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign:
            return

        # --- Idempotency check (Spec 14.2) — skip for dry-run ---
        if not campaign.dry_run:
            email_svc = EmailService()
            existing = await email_svc.check_idempotency(db, idempotency_key)
            if existing:
                return  # Already sent for this contact + cadence step

        # --- Fetch draft ---
        stmt = (
            select(OutreachEvent)
            .where(
                OutreachEvent.contact_id == contact.id,
                OutreachEvent.event_type == EventType.draft_created,
            )
            .order_by(OutreachEvent.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        draft_event = result.scalar_one_or_none()
        if not draft_event:
            raise Exception(f"No draft found for contact {contact_id}")

        # --- Dry-run mode: skip SendGrid, log what WOULD have been sent ---
        if campaign.dry_run:
            logger.info("DRY RUN: skipping SendGrid for contact %s", contact_id)
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.email_dry_run,
                channel=EventChannel.email,
                subject=draft_event.subject,
                content=draft_event.content,
                metadata_={
                    "to_email": contact.email,
                    "from_email": campaign.sender_email,
                    "from_name": campaign.sender_name or campaign.name,
                    "reply_to": campaign.reply_to,
                    "idempotency_key": idempotency_key,
                    "cadence_step": cadence_step,
                    "dry_run": True,
                },
                created_at=datetime.utcnow(),
            )
            db.add(event)

            contact.status = "emailed"
            contact.current_cadence_step = cadence_step
            await db.commit()

            # Schedule follow-up evaluation even in dry-run mode
            cadence = campaign.cadence or []
            next_step_index = cadence_step + 1
            if next_step_index < len(cadence):
                next_step = cadence[next_step_index]
                current_day = cadence[cadence_step]["day"]
                next_day = next_step["day"]
                days_until = next_day - current_day
                pool = ctx["pool"]
                await pool.enqueue_job(
                    "evaluate_contact",
                    str(contact.id),
                    next_step_index,
                    _defer_by=timedelta(days=days_until),
                )

            return

        # --- Rate limit: SendGrid ---
        conv_config = campaign.conversion_config or {}
        daily_limit = conv_config.get("sendgrid_daily_limit", 100)
        sg_limiter = sendgrid_limiter(redis, daily_limit=daily_limit)
        if not await sg_limiter.wait_for_slot(max_wait=300):
            raise Exception("SendGrid daily rate limit reached, will retry")

        # --- Threading headers (Spec 14.7) ---
        initial_message_id = None
        if cadence_step > 0:
            stmt = (
                select(OutreachEvent)
                .where(
                    OutreachEvent.contact_id == contact.id,
                    OutreachEvent.event_type == EventType.email_sent,
                )
                .order_by(OutreachEvent.created_at.asc())
                .limit(1)
            )
            result = await db.execute(stmt)
            initial_event = result.scalar_one_or_none()
            if initial_event and initial_event.metadata_:
                initial_message_id = initial_event.metadata_.get("sendgrid_message_id")

        # --- Build HTML from plain text ---
        import html as html_mod

        plain_text = draft_event.content or ""
        escaped = html_mod.escape(plain_text)
        html_body = (
            "<!DOCTYPE html><html><body>"
            '<div style="font-family: Arial, sans-serif; font-size: 14px; '
            "line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; "
            'padding: 20px;">'
            f"{escaped.replace(chr(10), '<br>' + chr(10))}"
            "</div></body></html>"
        )

        # --- Send ---
        try:
            send_result = await email_svc.send_email(
                to_email=contact.email,
                from_email=campaign.sender_email,
                from_name=campaign.sender_name or campaign.name,
                subject=draft_event.subject,
                html_body=html_body,
                reply_to=campaign.reply_to,
                initial_message_id=initial_message_id,
                custom_args={
                    "contact_id": str(contact.id),
                    "campaign_id": str(campaign.id),
                },
                idempotency_key=idempotency_key,
                db_session=db,
            )
        except SendGridPermanentError as e:
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.email_failed,
                channel=EventChannel.email,
                metadata_={"error": str(e), "permanent": True, "idempotency_key": idempotency_key},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            return  # Do NOT retry permanent errors
        except SendGridTransientError:
            raise  # Let arq retry

        if send_result["status"] == "already_sent":
            return  # Double-check from EmailService

        # --- Log success event ---
        event = OutreachEvent(
            id=uuid.uuid4(),
            contact_id=contact.id,
            event_type=EventType.email_sent,
            channel=EventChannel.email,
            subject=draft_event.subject,
            content=draft_event.content,
            metadata_={
                "sendgrid_message_id": send_result["sendgrid_message_id"],
                "idempotency_key": idempotency_key,
                "cadence_step": cadence_step,
            },
            created_at=datetime.utcnow(),
        )
        db.add(event)

        # --- Update contact ---
        contact.status = "emailed"
        contact.current_cadence_step = cadence_step

        await db.commit()

        # --- Schedule follow-up evaluation (Spec 6.5) ---
        cadence = campaign.cadence or []
        next_step_index = cadence_step + 1

        if next_step_index < len(cadence):
            next_step = cadence[next_step_index]
            current_day = cadence[cadence_step]["day"]
            next_day = next_step["day"]
            days_until = next_day - current_day

            pool = ctx["pool"]
            await pool.enqueue_job(
                "evaluate_contact",
                str(contact.id),
                next_step_index,
                _defer_by=timedelta(days=days_until),
            )


# ---------------------------------------------------------------------------
# Task 7: evaluate_contact
# ---------------------------------------------------------------------------


async def evaluate_contact(ctx, contact_id: str, cadence_step: int):
    """Evaluate a contact after the wait period — route to classify, follow-up, or close."""
    redis = ctx["redis"]
    lock_key = f"lock:contact:{contact_id}"

    # --- Redis distributed lock (Spec 14.1) ---
    lock = redis.lock(lock_key, timeout=60, blocking_timeout=10)
    acquired = await lock.acquire()
    if not acquired:
        raise Exception(f"Could not acquire lock for contact {contact_id}")

    try:
        async with get_async_session() as db:
            contact = await db.get(Contact, uuid.UUID(contact_id))
            if not contact:
                return

            # Status guard — another task may have handled this contact
            if contact.status in ("replied", "converted", "declined", "bounced"):
                return

            campaign = await db.get(Campaign, contact.campaign_id)
            if not campaign or campaign.status != "active":
                return

            # Check for replies since last email_sent
            stmt = (
                select(OutreachEvent)
                .where(
                    OutreachEvent.contact_id == contact.id,
                    OutreachEvent.event_type == EventType.reply_received,
                )
                .order_by(OutreachEvent.created_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            reply_event = result.scalar_one_or_none()

            # Find last email_sent timestamp for comparison
            stmt = (
                select(OutreachEvent)
                .where(
                    OutreachEvent.contact_id == contact.id,
                    OutreachEvent.event_type == EventType.email_sent,
                )
                .order_by(OutreachEvent.created_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            last_sent = result.scalar_one_or_none()

            has_new_reply = reply_event and last_sent and reply_event.created_at > last_sent.created_at

            pool = ctx["pool"]
            cadence = campaign.cadence or []

            if has_new_reply:
                # Reply found — classify it
                contact.status = "replied"
                event = OutreachEvent(
                    id=uuid.uuid4(),
                    contact_id=contact.id,
                    event_type=EventType.evaluate_result,
                    channel=EventChannel.system,
                    metadata_={"result": "reply_found", "cadence_step": cadence_step},
                    created_at=datetime.utcnow(),
                )
                db.add(event)
                await db.commit()
                await pool.enqueue_job("classify_reply", str(contact.id))

            elif cadence_step < len(cadence):
                step_config = cadence[cadence_step]
                action = step_config.get("action", "follow_up")

                if action == "close":
                    # Cadence exhausted — mark unresponsive
                    contact.status = "unresponsive"
                    event = OutreachEvent(
                        id=uuid.uuid4(),
                        contact_id=contact.id,
                        event_type=EventType.marked_unresponsive,
                        channel=EventChannel.system,
                        metadata_={"cadence_step": cadence_step},
                        created_at=datetime.utcnow(),
                    )
                    db.add(event)
                    await db.commit()
                else:
                    # Follow-up needed
                    await db.commit()
                    await pool.enqueue_job(
                        "send_follow_up",
                        str(contact.id),
                        cadence_step,
                    )
            else:
                # Beyond cadence — mark unresponsive
                contact.status = "unresponsive"
                await db.commit()
    finally:
        await lock.release()


# ---------------------------------------------------------------------------
# Task 8: send_follow_up
# ---------------------------------------------------------------------------


async def send_follow_up(ctx, contact_id: str, cadence_step: int):
    """Compose and enqueue a follow-up email for the given cadence step."""
    redis = ctx["redis"]

    async with get_async_session() as db:
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact or contact.status not in ("emailed",):
            return

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign or campaign.status != "active":
            return

        cadence = campaign.cadence or []
        if cadence_step >= len(cadence):
            return

        step_config = cadence[cadence_step]
        template_key = step_config.get("template", f"follow_up_{cadence_step}")
        templates = campaign.templates or {}
        _template = templates.get(template_key, {})

        # Rate limit LLM
        llm_config = campaign.llm_config or {}
        compose_config = llm_config.get("compose", {})
        provider = compose_config.get("provider", "anthropic")
        limiter = llm_limiter(redis, provider)
        if not await limiter.wait_for_slot(max_wait=60):
            raise Exception(f"Rate limit timeout for LLM provider {provider}")

        # Fetch prior outreach history for context
        stmt = (
            select(OutreachEvent).where(OutreachEvent.contact_id == contact.id).order_by(OutreachEvent.created_at.asc())
        )
        result = await db.execute(stmt)
        _history = result.scalars().all()

        # Build state with history
        state = OutreachState(
            contact_id=str(contact.id),
            campaign_id=str(campaign.id),
            contact=contact.to_dict(),
            campaign=campaign.to_dict(),
            research_data=contact.research_data or {},
            draft_subject="",
            draft_body="",
            reply_text="",
            classification="",
            current_step="compose",
            error="",
        )

        try:
            result_state = await compose_node(state)

            # Log follow-up draft
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.draft_created,
                channel=EventChannel.system,
                subject=result_state["draft_subject"],
                content=result_state["draft_body"],
                metadata_={
                    "template_key": template_key,
                    "cadence_step": cadence_step,
                    "is_follow_up": True,
                },
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()

            # Enqueue send (send_email handles scheduling next evaluate)
            pool = ctx["pool"]
            await pool.enqueue_job("send_email_task", str(contact.id), cadence_step)

        except Exception as e:
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type=EventType.compose_failed,
                channel=EventChannel.system,
                metadata_={"error": str(e), "cadence_step": cadence_step, "is_follow_up": True},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            raise


# ---------------------------------------------------------------------------
# Task 9: classify_reply
# ---------------------------------------------------------------------------


async def classify_reply(ctx, contact_id: str) -> dict:
    """Classify an inbound reply and route to next action.

    Uses Redis lock to prevent race condition with evaluate_contact.
    See spec section 14.1.
    """
    redis = ctx["redis"]
    lock_key = f"lock:contact:{contact_id}"

    async with redis_lock(redis, lock_key, timeout=60):
        async with get_async_session() as db:
            contact = await db.get(Contact, uuid.UUID(contact_id))
            if not contact:
                raise ValueError(f"Contact {contact_id} not found")

            campaign = await db.get(Campaign, contact.campaign_id)

            # Get the most recent reply_received event
            reply_event = await get_latest_event(db, contact_id, event_type="reply_received")
            if not reply_event:
                logger.warning("No reply event found for contact %s", contact_id)
                return {"status": "no_reply_found"}

            # Get outreach history for context
            _history = await get_contact_events(db, contact_id)

            # Run classify agent via the classify_node
            state = OutreachState(
                contact_id=str(contact.id),
                campaign_id=str(campaign.id) if campaign else "",
                contact=contact.to_dict(),
                campaign=campaign.to_dict() if campaign else {},
                research_data=contact.research_data or {},
                draft_subject="",
                draft_body="",
                reply_text=reply_event.content or "",
                classification="",
                current_step="classify",
                error="",
            )

            result_state = await classify_node(state)

            category = result_state.get("classification", "question")
            confidence = 0.8  # Default confidence from node
            sponsorship_interest = bool(result_state.get("sponsorship_interest", False))

            classification = {
                "category": category,
                "confidence": confidence,
                "sponsorship_interest": sponsorship_interest,
                "extracted_data": {},
            }

            # Log classification event
            await log_outreach_event(
                db,
                contact.id,
                event_type="reply_classified",
                channel="system",
                metadata={
                    "category": classification["category"],
                    "confidence": classification["confidence"],
                    "sponsorship_interest": classification["sponsorship_interest"],
                    "extracted_data": classification.get("extracted_data"),
                },
            )

            # Wave-1 Q2 — when the classifier flags a sponsorship-affirmative
            # reply, insert a sponsorship_interests row keyed to (contact, reply
            # event). Idempotent via the unique constraint; re-classifying the
            # same reply will not duplicate.
            if sponsorship_interest:
                await _persist_sponsorship_interest(db, contact.id, reply_event.id)

            # Route based on classification
            await route_classification(ctx, db, contact, campaign, classification)

            return {
                "status": "classified",
                "category": classification["category"],
                "confidence": classification["confidence"],
                "sponsorship_interest": classification["sponsorship_interest"],
            }


async def _persist_sponsorship_interest(
    db: AsyncSession,
    contact_id: uuid.UUID,
    reply_event_id: uuid.UUID,
) -> None:
    """Insert a sponsorship_interests row, idempotent on (contact, reply event).

    Uses ON CONFLICT DO NOTHING against the unique constraint
    `uq_sponsorship_contact_reply` so this is safe to call repeatedly
    when classify_reply gets retried by arq.
    """
    from sqlalchemy.dialects.postgresql import insert

    from app.models import SponsorshipInterest, SponsorshipInterestStatus

    stmt = (
        insert(SponsorshipInterest)
        .values(
            contact_id=contact_id,
            raw_reply_event_id=reply_event_id,
            status=SponsorshipInterestStatus.new,
        )
        .on_conflict_do_nothing(constraint="uq_sponsorship_contact_reply")
    )
    await db.execute(stmt)
    await db.commit()


async def route_classification(
    ctx: dict,
    db: AsyncSession,
    contact: Contact,
    campaign: Campaign | None,
    classification: dict,
) -> None:
    """Route a classification result to the appropriate action."""
    category = classification["category"]
    redis = ctx.get("redis")
    pool = ctx.get("pool")

    # Check if this is a late reply
    was_late_reply = contact.status in (
        ContactStatus.unresponsive,
        ContactStatus.declined,
    )

    match category:
        case "interested":
            if was_late_reply:
                await log_outreach_event(
                    db,
                    contact.id,
                    event_type="reopened",
                    channel="system",
                    metadata={
                        "previous_status": contact.status.value
                        if isinstance(contact.status, ContactStatus)
                        else contact.status,
                        "reason": "late_reply_classified_interested",
                    },
                )
                logger.info(
                    "Contact %s reopened from %s after late reply classified as interested",
                    contact.id,
                    contact.status,
                )

            contact.status = ContactStatus.replied
            await db.commit()

            # Cancel deferred evaluate jobs
            if redis:
                await cancel_deferred_jobs(redis, contact.id)

            # If campaign goal is custom and success_criteria matches, auto-convert
            if campaign and campaign.goal == CampaignGoal.custom and campaign.success_criteria:
                if campaign.success_criteria.get("classification") == "interested":
                    if pool:
                        await pool.enqueue_job(
                            "process_conversion",
                            contact_id=str(contact.id),
                            conversion_type="custom",
                        )

        case "declined":
            if was_late_reply and contact.status == ContactStatus.declined:
                # Already declined, just log the additional reply
                await log_outreach_event(
                    db,
                    contact.id,
                    event_type="reply_classified",
                    channel="system",
                    metadata={"note": "Late reply reconfirms declined status"},
                )
                return  # Don't re-update status

            contact.status = ContactStatus.declined
            await db.commit()
            if redis:
                await cancel_deferred_jobs(redis, contact.id)

        case "question":
            contact.status = ContactStatus.replied
            await db.commit()
            if redis:
                await cancel_deferred_jobs(redis, contact.id)
            if pool:
                await pool.enqueue_job(
                    "compose_email",
                    contact_id=str(contact.id),
                    template_key="reply",
                    reply_context=classification.get("extracted_data", {}),
                )

        case "out_of_office":
            # Reschedule evaluate for later (7 days)
            if pool:
                await pool.enqueue_job(
                    "evaluate_contact",
                    contact_id=str(contact.id),
                    cadence_step=contact.current_cadence_step,
                    _defer_by=timedelta(days=7),
                )

        case "bounce":
            # Treat LLM-detected bounce same as SendGrid bounce
            await handle_bounce_from_reply(db, contact, redis)


# ---------------------------------------------------------------------------
# Task 10: launch_campaign
# ---------------------------------------------------------------------------


async def launch_campaign(ctx, campaign_id: str) -> dict:
    """Validate and launch a campaign, stagger-enqueuing research tasks for all pending contacts."""
    async with get_async_session() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        if campaign.status not in ("draft", "paused", "active"):
            raise ValueError(f"Campaign {campaign_id} is {campaign.status}, cannot launch")

        # --- Validation (Spec 14.5) ---
        errors = []

        # Check templates exist for cadence references
        cadence = campaign.cadence or []
        templates = campaign.templates or {}
        for step in cadence:
            template_key = step.get("template")
            if template_key and template_key not in templates:
                errors.append(f"Template '{template_key}' referenced in cadence but not defined")

        # Check sender
        if not campaign.sender_email:
            errors.append("sender_email is required")

        # Check LLM API keys
        llm_config = campaign.llm_config or {}
        provider_key_map = {
            "gemini": "gemini_api_key",
            "anthropic": "anthropic_api_key",
            "openai": "openai_api_key",
        }
        for role, config in llm_config.items():
            if isinstance(config, dict):
                provider = config.get("provider")
                attr_key = provider_key_map.get(provider)
                if attr_key and not getattr(app_settings, attr_key, None):
                    errors.append(f"LLM provider '{provider}' for {role} requires {attr_key.upper()}")

        # Goal-specific checks
        conv_config = campaign.conversion_config or {}
        if campaign.goal == "payment" and not conv_config.get("stripe_price_id"):
            errors.append("Payment goal requires conversion_config.stripe_price_id")
        if campaign.goal == "booking" and not conv_config.get("cal_event_link"):
            errors.append("Booking goal requires conversion_config.cal_event_link")

        # Check for pending contacts
        stmt = select(Contact).where(
            Contact.campaign_id == campaign.id,
            Contact.status == "pending",
        )
        result = await db.execute(stmt)
        pending_contacts = result.scalars().all()

        if not pending_contacts:
            errors.append("No contacts with status 'pending'")

        if errors:
            raise ValueError(f"Campaign validation failed: {'; '.join(errors)}")

        # --- Launch ---
        campaign.status = "active"
        await db.commit()

        # Staggered enqueue (Spec 6.4)
        pool = ctx["pool"]
        for i, contact in enumerate(pending_contacts):
            await pool.enqueue_job(
                "research_contact",
                str(contact.id),
                _defer_by=timedelta(seconds=i * 5),
            )

        return {"enqueued": len(pending_contacts), "campaign_status": "active"}
