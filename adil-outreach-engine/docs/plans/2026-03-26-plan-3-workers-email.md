# Plan 3: Workers & Email Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the arq worker infrastructure that executes agent tasks asynchronously — research, compose, send emails via SendGrid, schedule follow-ups, and handle rate limiting.

**Architecture:** arq async workers backed by Redis. Tasks execute LangGraph agent nodes and SendGrid API calls. Redis-based rate limiting prevents API abuse. Deferred jobs handle follow-up cadence scheduling.

**Tech Stack:** arq, Redis, SendGrid v6, asyncio

**Depends on:** Plan 1 (SQLAlchemy models, enums, database session) + Plan 2 (LangGraph agent graph, nodes, OutreachState)

**Design spec reference:** Sections 6 (arq Worker) and 14 (Edge Cases & Safety)

---

## Task 1: Redis Connection Setup

**File:** `app/workers/settings.py`

- [ ] Create `app/workers/__init__.py` (empty)
- [ ] Create `app/workers/settings.py` with Redis connection factory
- [ ] Read `REDIS_URL` from `app/config.py` settings (e.g. `redis://host:6379/0`)
- [ ] Create `get_redis_pool()` async function that returns an `arq.connections.ArqRedis` instance
- [ ] Create `get_raw_redis()` function returning a plain `redis.asyncio.Redis` for rate limiting / locking (separate from arq's pool)
- [ ] Both functions must be safe to call multiple times (singleton pattern or connection caching)
- [ ] Add a `close_redis()` cleanup function for graceful shutdown

```python
# app/workers/settings.py (partial — connection portion)
from arq.connections import RedisSettings, ArqRedis, create_pool
from app.config import settings

def get_redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.REDIS_URL)

_arq_pool: ArqRedis | None = None

async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_redis_settings())
    return _arq_pool

async def close_redis():
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None
```

**Acceptance criteria:**
- `get_arq_pool()` returns a working ArqRedis connection
- `get_redis_settings()` correctly parses the DSN from env
- Connection is reused across calls (singleton)

---

## Task 2: Rate Limiter

**File:** `app/workers/rate_limiter.py`

- [ ] Create Redis counter-based rate limiter class `RateLimiter`
- [ ] Constructor accepts: `redis` (asyncio Redis client), `resource` (string key prefix), `max_requests` (int), `window_seconds` (int)
- [ ] Implement `async acquire() -> bool` — returns True if under limit, False if rate limited
- [ ] Implement `async wait_for_slot()` — blocks (with asyncio.sleep polling) until a slot is available, with a max wait timeout
- [ ] Use Redis `INCR` + `EXPIRE` pattern for atomic counter with TTL
- [ ] Key format: `ratelimit:{resource}:{window_bucket}` where window_bucket = `int(time.time() / window_seconds)`
- [ ] Support the three resource types from the spec:
  - SendGrid sends: configurable (default 100/day)
  - LLM API calls: per-provider configurable, per minute
  - Research scraping: 1 request per 2 seconds per domain

```python
# app/workers/rate_limiter.py
import time
import asyncio
from redis.asyncio import Redis


class RateLimiter:
    def __init__(
        self,
        redis: Redis,
        resource: str,
        max_requests: int,
        window_seconds: int,
    ):
        self.redis = redis
        self.resource = resource
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _key(self) -> str:
        bucket = int(time.time() / self.window_seconds)
        return f"ratelimit:{self.resource}:{bucket}"

    async def acquire(self) -> bool:
        key = self._key()
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window_seconds)
        results = await pipe.execute()
        current_count = results[0]
        return current_count <= self.max_requests

    async def wait_for_slot(self, max_wait: float = 120.0) -> bool:
        """Block until a rate limit slot is available. Returns False on timeout."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            if await self.acquire():
                return True
            # Sleep for a fraction of the window before retrying
            await asyncio.sleep(min(1.0, self.window_seconds / 10))
        return False


# Pre-configured limiter factories
def sendgrid_limiter(redis: Redis, daily_limit: int = 100) -> RateLimiter:
    return RateLimiter(redis, "sendgrid", max_requests=daily_limit, window_seconds=86400)

def llm_limiter(redis: Redis, provider: str, per_minute: int = 60) -> RateLimiter:
    return RateLimiter(redis, f"llm:{provider}", max_requests=per_minute, window_seconds=60)

def scrape_limiter(redis: Redis, domain: str) -> RateLimiter:
    return RateLimiter(redis, f"scrape:{domain}", max_requests=1, window_seconds=2)
```

**Acceptance criteria:**
- `acquire()` returns True when under limit, False when exceeded
- Counter auto-expires via Redis TTL (no stale keys)
- `wait_for_slot()` retries until a slot opens or timeout is reached
- Factory functions produce correctly configured limiters

---

## Task 3: Email Service

**File:** `app/services/email.py`

- [ ] Create `EmailService` class wrapping SendGrid v6 Python SDK
- [ ] Constructor takes SendGrid API key from `app/config.py` settings
- [ ] Implement `async send_email()` method with these parameters:
  - `to_email: str`
  - `from_email: str`
  - `from_name: str`
  - `subject: str`
  - `html_body: str`
  - `reply_to: str | None`
  - `headers: dict | None` (for In-Reply-To / References threading)
  - `custom_args: dict | None` (for SendGrid metadata — contact_id, campaign_id)
  - `idempotency_key: str | None`
- [ ] Implement idempotency check **before** calling SendGrid (Spec 14.2):
  - Query `outreach_events` for existing `email_sent` event where `metadata->>'idempotency_key' == key`
  - If found, return the existing event (skip send)
  - Idempotency key format: `{contact_id}:{cadence_step}`
- [ ] On successful send, extract `X-Message-Id` from SendGrid response and return it
- [ ] Implement `In-Reply-To` / `References` header support for email threading (Spec 14.7):
  - Accept optional `initial_message_id` parameter
  - If provided, set `In-Reply-To: <{initial_message_id}>` and `References: <{initial_message_id}>`
- [ ] Store `sendgrid_message_id` in returned metadata for future threading
- [ ] Handle SendGrid API errors gracefully (raise typed exceptions for retry vs permanent failure)

```python
# app/services/email.py
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Email, To, Content, Header, CustomArg, ReplyTo,
)
from sqlalchemy import select
from app.config import settings
from app.models.outreach_event import OutreachEvent


class SendGridError(Exception):
    """Base SendGrid error."""
    pass


class SendGridTransientError(SendGridError):
    """Retryable error (5xx, rate limit)."""
    pass


class SendGridPermanentError(SendGridError):
    """Non-retryable error (4xx except 429)."""
    pass


class EmailService:
    def __init__(self):
        self.client = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)

    async def check_idempotency(self, db_session, idempotency_key: str) -> OutreachEvent | None:
        """Check if an email with this idempotency key was already sent."""
        stmt = select(OutreachEvent).where(
            OutreachEvent.event_type == "email_sent",
            OutreachEvent.metadata["idempotency_key"].as_string() == idempotency_key,
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
        # 1. Idempotency guard
        if idempotency_key and db_session:
            existing = await self.check_idempotency(db_session, idempotency_key)
            if existing:
                return {
                    "status": "already_sent",
                    "event_id": str(existing.id),
                    "message_id": existing.metadata.get("sendgrid_message_id"),
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
```

**Acceptance criteria:**
- Idempotency check prevents duplicate sends on retry
- Email threading headers set correctly for follow-ups
- Transient vs permanent errors distinguished for arq retry logic
- SendGrid message ID extracted and returned for threading chain

---

## Task 4: `research_contact` Task

**File:** `app/workers/tasks.py`

- [ ] Create `app/workers/tasks.py`
- [ ] Import the research agent node from `app/agents/nodes/research.py` (Plan 2)
- [ ] Import DB session factory, Contact model, OutreachEvent model (Plan 1)
- [ ] Implement `async def research_contact(ctx, contact_id: str):`
  1. Acquire rate limiter slot for scraping (domain from contact's website) and LLM provider
  2. Fetch contact + campaign from DB
  3. Guard: if `contact.status != "pending"`, return early (idempotency)
  4. Update `contact.status = "researching"`
  5. Build `OutreachState` with contact and campaign data
  6. Execute the research agent node (from Plan 2's LangGraph)
  7. Save `research_data` to `contact.research_data`
  8. Update `contact.status = "ready"`
  9. Log `outreach_event` (type: `research_completed`, channel: `system`)
  10. Enqueue `compose_email` task for this contact
  11. On error: log event with error details, set `contact.status = "pending"` for retry

```python
# app/workers/tasks.py (research_contact)
import uuid
from datetime import datetime
from sqlalchemy import select
from app.database import get_async_session
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.outreach_event import OutreachEvent
from app.agents.state import OutreachState
from app.agents.nodes.research import research_node
from app.workers.rate_limiter import scrape_limiter, llm_limiter
from urllib.parse import urlparse


async def research_contact(ctx, contact_id: str):
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
        research_config = campaign.llm_config.get("research", {})
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

            result_state = await research_node(state, research_config)

            # Save research data
            contact.research_data = result_state["research_data"]
            contact.status = "ready"

            # Log event
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type="research_completed",
                channel="system",
                metadata={"research_keys": list(result_state["research_data"].keys())},
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
                event_type="research_failed",
                channel="system",
                metadata={"error": str(e)},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            raise  # Let arq retry
```

**Acceptance criteria:**
- Contact status transitions: `pending` -> `researching` -> `ready`
- Rate limiting applied before scraping and LLM calls
- Research data persisted to contact record
- `compose_email` enqueued on success
- Error handling resets status for arq retry

---

## Task 5: `compose_email` Task

**File:** `app/workers/tasks.py` (append)

- [ ] Implement `async def compose_email(ctx, contact_id: str):`
  1. Fetch contact (must have `status = "ready"` and non-null `research_data`)
  2. Fetch campaign with templates and compose_instructions
  3. Rate limit the LLM provider (compose config)
  4. Build `OutreachState` with contact, campaign, research_data, and template for current cadence step
  5. Execute the compose agent node (from Plan 2)
  6. Store draft subject + body in an `outreach_event` (type: `draft_created`, channel: `system`)
  7. If `campaign.auto_send` is True: enqueue `send_email` task immediately
  8. If `campaign.auto_send` is False: update `contact.status = "draft_pending"` and wait for human approval via `/approve-draft` endpoint
  9. On error: log event, allow arq retry

```python
async def compose_email(ctx, contact_id: str):
    redis = ctx["redis"]

    async with get_async_session() as db:
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact or contact.status != "ready":
            return

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign or campaign.status != "active":
            return

        # Rate limit LLM
        compose_config = campaign.llm_config.get("compose", {})
        provider = compose_config.get("provider", "anthropic")
        limiter = llm_limiter(redis, provider)
        if not await limiter.wait_for_slot(max_wait=60):
            raise Exception(f"Rate limit timeout for LLM provider {provider}")

        # Determine template for current cadence step
        cadence_step = contact.current_cadence_step or 0
        cadence = campaign.cadence
        if cadence_step < len(cadence):
            step_config = cadence[cadence_step]
            template_key = step_config.get("template", "initial")
        else:
            template_key = "initial"
        template = campaign.templates.get(template_key, {})

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
            result_state = await compose_node(state, compose_config, template)

            # Log draft event
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type="draft_created",
                channel="system",
                subject=result_state["draft_subject"],
                content=result_state["draft_body"],
                metadata={
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
                    "send_email",
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
                event_type="compose_failed",
                channel="system",
                metadata={"error": str(e)},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            raise
```

**Acceptance criteria:**
- Correct template selected based on `current_cadence_step` and cadence config
- Draft event logged with subject + body content
- Auto-send campaigns enqueue `send_email`; manual campaigns set `draft_pending`
- LLM rate limiting applied

---

## Task 6: `send_email` Task

**File:** `app/workers/tasks.py` (append)

- [ ] Implement `async def send_email(ctx, contact_id: str, cadence_step: int):`
- [ ] **Idempotency check** (Spec 14.2): idempotency key = `{contact_id}:{cadence_step}`
  - Before sending, query `outreach_events` for existing `email_sent` with matching `metadata.idempotency_key`
  - If found, skip send entirely and return
- [ ] **Rate limiting**: acquire SendGrid rate limit slot via `sendgrid_limiter`
- [ ] Fetch the most recent `draft_created` event for this contact to get subject + body
- [ ] Call `EmailService.send_email()` with:
  - Threading headers if `cadence_step > 0` (fetch `sendgrid_message_id` from initial send event)
  - Custom args: `{"contact_id": contact_id, "campaign_id": campaign_id}`
  - The idempotency key
- [ ] On success:
  - Log `email_sent` event with `sendgrid_message_id` and `idempotency_key` in metadata
  - Update `contact.status = "emailed"`
  - Update `contact.current_cadence_step = cadence_step`
  - **Schedule follow-up** (Spec 6.5): calculate days until next cadence step, enqueue `evaluate_contact` with `_defer_by=timedelta(days=days_until)`
- [ ] On `SendGridPermanentError`: log event, mark contact appropriately, do NOT retry
- [ ] On `SendGridTransientError`: re-raise for arq retry

```python
from datetime import timedelta
from app.services.email import EmailService, SendGridTransientError, SendGridPermanentError


async def send_email_task(ctx, contact_id: str, cadence_step: int):
    redis = ctx["redis"]
    idempotency_key = f"{contact_id}:{cadence_step}"

    async with get_async_session() as db:
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact:
            return

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign:
            return

        # --- Idempotency check (Spec 14.2) ---
        email_svc = EmailService()
        existing = await email_svc.check_idempotency(db, idempotency_key)
        if existing:
            return  # Already sent for this contact + cadence step

        # --- Rate limit: SendGrid ---
        sg_limiter = sendgrid_limiter(redis, daily_limit=campaign.metadata.get("sendgrid_daily_limit", 100) if campaign.metadata else 100)
        if not await sg_limiter.wait_for_slot(max_wait=300):
            raise Exception("SendGrid daily rate limit reached, will retry")

        # --- Fetch draft ---
        stmt = (
            select(OutreachEvent)
            .where(
                OutreachEvent.contact_id == contact.id,
                OutreachEvent.event_type == "draft_created",
            )
            .order_by(OutreachEvent.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        draft_event = result.scalar_one_or_none()
        if not draft_event:
            raise Exception(f"No draft found for contact {contact_id}")

        # --- Threading headers (Spec 14.7) ---
        initial_message_id = None
        if cadence_step > 0:
            stmt = (
                select(OutreachEvent)
                .where(
                    OutreachEvent.contact_id == contact.id,
                    OutreachEvent.event_type == "email_sent",
                )
                .order_by(OutreachEvent.created_at.asc())
                .limit(1)
            )
            result = await db.execute(stmt)
            initial_event = result.scalar_one_or_none()
            if initial_event and initial_event.metadata:
                initial_message_id = initial_event.metadata.get("sendgrid_message_id")

        # --- Send ---
        try:
            send_result = await email_svc.send_email(
                to_email=contact.email,
                from_email=campaign.sender_email,
                from_name=campaign.sender_name,
                subject=draft_event.subject,
                html_body=draft_event.content,
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
                event_type="email_failed",
                channel="email",
                metadata={"error": str(e), "permanent": True, "idempotency_key": idempotency_key},
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
            event_type="email_sent",
            channel="email",
            subject=draft_event.subject,
            content=draft_event.content,
            metadata={
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
        cadence = campaign.cadence
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
```

**Acceptance criteria:**
- Idempotency key `{contact_id}:{cadence_step}` prevents duplicate sends on retry
- Threading headers (In-Reply-To, References) set for follow-up emails using initial send's message ID
- Follow-up `evaluate_contact` scheduled with correct `_defer_by` based on cadence day deltas
- Permanent SendGrid errors do not trigger retry; transient errors do
- `email_sent` event logged with `sendgrid_message_id` for future threading

---

## Task 7: `evaluate_contact` Task

**File:** `app/workers/tasks.py` (append)

- [ ] Implement `async def evaluate_contact(ctx, contact_id: str, cadence_step: int):`
- [ ] **Redis distributed lock** (Spec 14.1): acquire `lock:contact:{contact_id}` with 60s timeout
  - Both `evaluate_contact` and `classify_reply` compete for this lock
  - If lock cannot be acquired within timeout, re-raise for arq retry
- [ ] **Status guard**: after acquiring lock, check contact status
  - If status in (`replied`, `converted`, `declined`, `bounced`) -> release lock, return immediately
  - Another task (e.g. `classify_reply` from inbound webhook) already handled this contact
- [ ] Check if contact has any `reply_received` events since last email was sent
  - If reply exists -> enqueue `classify_reply` task
  - If no reply and cadence has more follow-up steps -> enqueue `send_follow_up`
  - If no reply and cadence exhausted (action == "close") -> mark contact `unresponsive`, log event

```python
async def evaluate_contact(ctx, contact_id: str, cadence_step: int):
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
                    OutreachEvent.event_type == "reply_received",
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
                    OutreachEvent.event_type == "email_sent",
                )
                .order_by(OutreachEvent.created_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            last_sent = result.scalar_one_or_none()

            has_new_reply = (
                reply_event
                and last_sent
                and reply_event.created_at > last_sent.created_at
            )

            pool = ctx["pool"]
            cadence = campaign.cadence

            if has_new_reply:
                # Reply found — classify it
                contact.status = "replied"
                event = OutreachEvent(
                    id=uuid.uuid4(),
                    contact_id=contact.id,
                    event_type="evaluate_result",
                    channel="system",
                    metadata={"result": "reply_found", "cadence_step": cadence_step},
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
                        event_type="marked_unresponsive",
                        channel="system",
                        metadata={"cadence_step": cadence_step},
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
```

**Acceptance criteria:**
- Redis distributed lock prevents race between `evaluate_contact` and `classify_reply`
- Status guard exits early if contact already handled
- Correctly routes to classify (reply found), follow-up (cadence continues), or close (cadence exhausted)
- Lock always released in `finally` block

---

## Task 8: `send_follow_up` Task

**File:** `app/workers/tasks.py` (append)

- [ ] Implement `async def send_follow_up(ctx, contact_id: str, cadence_step: int):`
  1. Fetch contact and campaign
  2. Guard: if contact status not in (`emailed`) or campaign not active, return
  3. Determine the follow-up template from `campaign.cadence[cadence_step].template`
  4. Run the compose agent with the follow-up template + research_data + prior outreach history
  5. Log `draft_created` event for the follow-up
  6. Enqueue `send_email` task with the new `cadence_step`
  7. The `send_email` task handles scheduling the next evaluate via `_defer_by` (Task 6)

```python
async def send_follow_up(ctx, contact_id: str, cadence_step: int):
    redis = ctx["redis"]

    async with get_async_session() as db:
        contact = await db.get(Contact, uuid.UUID(contact_id))
        if not contact or contact.status not in ("emailed",):
            return

        campaign = await db.get(Campaign, contact.campaign_id)
        if not campaign or campaign.status != "active":
            return

        cadence = campaign.cadence
        if cadence_step >= len(cadence):
            return

        step_config = cadence[cadence_step]
        template_key = step_config.get("template", f"follow_up_{cadence_step}")
        template = campaign.templates.get(template_key, {})

        # Rate limit LLM
        compose_config = campaign.llm_config.get("compose", {})
        provider = compose_config.get("provider", "anthropic")
        limiter = llm_limiter(redis, provider)
        if not await limiter.wait_for_slot(max_wait=60):
            raise Exception(f"Rate limit timeout for LLM provider {provider}")

        # Fetch prior outreach history for context
        stmt = (
            select(OutreachEvent)
            .where(OutreachEvent.contact_id == contact.id)
            .order_by(OutreachEvent.created_at.asc())
        )
        result = await db.execute(stmt)
        history = result.scalars().all()

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
            result_state = await compose_node(
                state,
                compose_config,
                template,
                outreach_history=[
                    {"type": e.event_type, "subject": e.subject, "content": e.content}
                    for e in history
                ],
            )

            # Log follow-up draft
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type="draft_created",
                channel="system",
                subject=result_state["draft_subject"],
                content=result_state["draft_body"],
                metadata={
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
            await pool.enqueue_job("send_email", str(contact.id), cadence_step)

        except Exception as e:
            event = OutreachEvent(
                id=uuid.uuid4(),
                contact_id=contact.id,
                event_type="compose_failed",
                channel="system",
                metadata={"error": str(e), "cadence_step": cadence_step, "is_follow_up": True},
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
            raise
```

**Acceptance criteria:**
- Correct follow-up template selected from cadence config
- Compose node receives prior outreach history for contextual follow-ups
- Delegates to `send_email` which handles threading headers and next evaluate scheduling
- Follow-up drafts marked with `is_follow_up: True` in metadata

---

## Task 9: Campaign Launch Flow

**File:** `app/workers/tasks.py` (append)

- [ ] Implement `async def launch_campaign(ctx, campaign_id: str):`
  1. Fetch campaign, validate it is in `draft` or `paused` status
  2. **Validation checks** (Spec 14.5):
     - All templates referenced in `cadence` exist in `templates`
     - At least 1 contact with `status = "pending"`
     - `sender_email` is set
     - LLM config providers have corresponding API keys
     - Goal-specific checks (payment -> stripe_price_id, booking -> cal_event_link)
  3. Set `campaign.status = "active"`
  4. Query all contacts where `status = "pending"`
  5. **Staggered enqueue**: for each contact at index `i`, enqueue `research_contact` with `_defer_by = i * 5 seconds`
  6. Log campaign launch event
  7. Return `{"enqueued": N, "campaign_status": "active"}`

```python
from app.config import settings as app_settings


async def launch_campaign(ctx, campaign_id: str) -> dict:
    async with get_async_session() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        if campaign.status not in ("draft", "paused"):
            raise ValueError(f"Campaign {campaign_id} is {campaign.status}, cannot launch")

        # --- Validation (Spec 14.5) ---
        errors = []

        # Check templates exist for cadence references
        for step in campaign.cadence:
            template_key = step.get("template")
            if template_key and template_key not in campaign.templates:
                errors.append(f"Template '{template_key}' referenced in cadence but not defined")

        # Check sender
        if not campaign.sender_email:
            errors.append("sender_email is required")

        # Check LLM API keys
        llm_config = campaign.llm_config or {}
        provider_key_map = {
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        for role, config in llm_config.items():
            provider = config.get("provider")
            env_key = provider_key_map.get(provider)
            if env_key and not getattr(app_settings, env_key, None):
                errors.append(f"LLM provider '{provider}' for {role} requires {env_key}")

        # Goal-specific checks
        conv_config = campaign.conversion_config or {}
        if campaign.goal == "payment" and not conv_config.get("stripe_price_id"):
            errors.append("Payment goal requires conversion_config.stripe_price_id")
        if campaign.goal == "booking" and not conv_config.get("cal_event_link"):
            errors.append("Booking goal requires conversion_config.cal_event_link")

        # Check for pending contacts
        stmt = (
            select(Contact)
            .where(
                Contact.campaign_id == campaign.id,
                Contact.status == "pending",
            )
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
```

**Acceptance criteria:**
- All validation checks from Spec 14.5 enforced before launch
- Contacts enqueued with staggered 5-second intervals via `_defer_by`
- Campaign status set to `active` before enqueueing
- Returns count of enqueued contacts

---

## Task 10: WorkerSettings and arq Startup

**File:** `app/workers/settings.py` (extend from Task 1)

- [ ] Define `class WorkerSettings` per arq convention
- [ ] Register all task functions: `research_contact`, `compose_email`, `send_email`, `evaluate_contact`, `classify_reply`, `process_conversion`, `send_follow_up`, `launch_campaign`
- [ ] Configure worker settings from Spec 6.2:
  - `max_jobs = 10`
  - `job_timeout = 300` (5 minutes)
  - `max_tries = 3`
  - `retry_backoff = True`
  - `health_check_interval = 30`
  - `poll_delay = 1.0`
- [ ] Implement `on_startup` handler:
  - Initialize DB engine
  - Create raw Redis client for rate limiting / locking
  - Store both in `ctx` dict for tasks to access
- [ ] Implement `on_shutdown` handler:
  - Close DB engine
  - Close Redis connections

```python
# app/workers/settings.py (full file)
from arq.connections import RedisSettings, ArqRedis, create_pool
from redis.asyncio import Redis
from app.config import settings
from app.workers.tasks import (
    research_contact,
    compose_email,
    send_email_task,
    evaluate_contact,
    classify_reply,
    process_conversion,
    send_follow_up,
    launch_campaign,
)
from app.database import engine, dispose_engine


def get_redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.REDIS_URL)


_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_redis_settings())
    return _arq_pool


async def close_redis():
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def on_startup(ctx):
    """Called when arq worker starts."""
    # Raw Redis for rate limiting and distributed locks
    ctx["redis"] = Redis.from_url(settings.REDIS_URL)
    # arq pool for enqueueing child jobs
    ctx["pool"] = await get_arq_pool()


async def on_shutdown(ctx):
    """Called when arq worker shuts down."""
    if "redis" in ctx:
        await ctx["redis"].close()
    await close_redis()
    await dispose_engine()


class WorkerSettings:
    """arq worker configuration — run with: arq app.workers.settings.WorkerSettings"""

    redis_settings = get_redis_settings()

    functions = [
        research_contact,
        compose_email,
        send_email_task,
        evaluate_contact,
        classify_reply,
        process_conversion,
        send_follow_up,
        launch_campaign,
    ]

    on_startup = on_startup
    on_shutdown = on_shutdown

    # Concurrency
    max_jobs = 10

    # Timeout: 5 minutes per task (research/compose can be slow)
    job_timeout = 300

    # Retry: 3 attempts with exponential backoff
    max_tries = 3
    retry_backoff = True

    # Health check every 30 seconds
    health_check_interval = 30

    # Poll Redis every 1 second
    poll_delay = 1.0
```

**Run command:** `arq app.workers.settings.WorkerSettings`

**Acceptance criteria:**
- Worker starts, connects to Redis, initializes DB
- All task functions registered and discoverable by arq
- `ctx["redis"]` and `ctx["pool"]` available in all tasks
- Graceful shutdown closes all connections

---

## Task 11: Wire Campaign Launch Endpoint

**File:** `app/api/campaigns.py` (modify existing from Plan 1)

- [ ] Add or modify `POST /api/v1/outreach/campaigns/{id}/launch` endpoint
- [ ] Endpoint should:
  1. Validate campaign exists and is in `draft` or `paused` status
  2. Enqueue `launch_campaign` arq task (validation happens in the task)
  3. Return `202 Accepted` with `{"message": "Campaign launch enqueued", "campaign_id": id}`
- [ ] Import `get_arq_pool` from `app/workers/settings.py`
- [ ] Keep the endpoint thin — all business logic in the arq task

```python
# In app/api/campaigns.py

from fastapi import APIRouter, HTTPException
from app.workers.settings import get_arq_pool
from app.database import get_async_session
from app.models.campaign import Campaign

router = APIRouter(prefix="/api/v1/outreach/campaigns", tags=["campaigns"])


@router.post("/{campaign_id}/launch", status_code=202)
async def launch_campaign_endpoint(campaign_id: str):
    """Activate campaign and enqueue all pending contacts for outreach."""
    async with get_async_session() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign.status not in ("draft", "paused"):
            raise HTTPException(
                status_code=409,
                detail=f"Campaign is '{campaign.status}', must be 'draft' or 'paused' to launch",
            )

    # Enqueue the launch task — validation + staggered enqueue happens in worker
    pool = await get_arq_pool()
    job = await pool.enqueue_job("launch_campaign", campaign_id)

    return {
        "message": "Campaign launch enqueued",
        "campaign_id": campaign_id,
        "job_id": job.job_id,
    }
```

**Acceptance criteria:**
- Endpoint returns 202 with job ID
- Basic pre-checks (exists, correct status) at API level for fast feedback
- Full validation deferred to arq task
- arq pool correctly obtained and used

---

## Task 12: Tests with fakeredis

**File:** `tests/test_workers.py`

- [ ] Install dev dependency: `fakeredis[aioredis]`
- [ ] Create test fixtures:
  - `fake_redis` — fakeredis async client
  - `arq_ctx` — mock arq context dict with `redis` and `pool` keys
  - `db_session` — async SQLAlchemy session with test DB
  - `sample_campaign` — factory for Campaign with templates, cadence, llm_config
  - `sample_contact` — factory for Contact linked to sample_campaign
- [ ] **Test: Rate limiter**
  - [ ] `test_rate_limiter_allows_within_limit` — acquire N times within limit returns True
  - [ ] `test_rate_limiter_blocks_over_limit` — acquire beyond limit returns False
  - [ ] `test_rate_limiter_resets_after_window` — counter resets in next time window
  - [ ] `test_wait_for_slot_timeout` — returns False when limit not freed within timeout
- [ ] **Test: Email idempotency**
  - [ ] `test_send_email_idempotent` — second send with same key returns `already_sent`
  - [ ] `test_send_email_different_cadence_step` — different cadence_step = different key, both send
- [ ] **Test: evaluate_contact routing**
  - [ ] `test_evaluate_with_reply_enqueues_classify` — reply exists -> classify
  - [ ] `test_evaluate_no_reply_enqueues_follow_up` — no reply, cadence continues -> follow_up
  - [ ] `test_evaluate_cadence_exhausted_marks_unresponsive` — no reply, close action -> unresponsive
  - [ ] `test_evaluate_skips_already_converted` — status is `converted` -> early return
- [ ] **Test: Redis distributed lock**
  - [ ] `test_concurrent_evaluate_and_classify` — simulate two tasks competing for lock, only one proceeds
- [ ] **Test: Campaign launch**
  - [ ] `test_launch_validates_templates` — missing template -> raises error
  - [ ] `test_launch_validates_pending_contacts` — no pending contacts -> raises error
  - [ ] `test_launch_staggered_enqueue` — verify `_defer_by` increases per contact
- [ ] **Test: Follow-up scheduling**
  - [ ] `test_send_email_schedules_evaluate` — after send, evaluate_contact enqueued with correct `_defer_by`
  - [ ] `test_follow_up_uses_correct_template` — follow-up step selects right template key

```python
# tests/test_workers.py (skeleton)
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

import fakeredis.aioredis

from app.workers.rate_limiter import RateLimiter, sendgrid_limiter
from app.workers.tasks import (
    research_contact,
    send_email_task,
    evaluate_contact,
    launch_campaign,
    send_follow_up,
)


@pytest.fixture
async def fake_redis():
    """Provide a fakeredis async client."""
    redis = fakeredis.aioredis.FakeRedis()
    yield redis
    await redis.close()


@pytest.fixture
def arq_ctx(fake_redis):
    """Mock arq worker context."""
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    return {"redis": fake_redis, "pool": pool}


# --- Rate Limiter Tests ---

@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit(fake_redis):
    limiter = RateLimiter(fake_redis, "test", max_requests=5, window_seconds=60)
    for _ in range(5):
        assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit(fake_redis):
    limiter = RateLimiter(fake_redis, "test", max_requests=2, window_seconds=60)
    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is False


@pytest.mark.asyncio
async def test_wait_for_slot_timeout(fake_redis):
    limiter = RateLimiter(fake_redis, "test", max_requests=1, window_seconds=3600)
    await limiter.acquire()  # Use the single slot
    result = await limiter.wait_for_slot(max_wait=0.5)
    assert result is False


# --- Idempotency Tests ---

@pytest.mark.asyncio
async def test_send_email_idempotent(arq_ctx, db_session, sample_contact, sample_campaign):
    """Second send_email call with same contact_id + cadence_step should skip."""
    # First send succeeds
    with patch("app.services.email.EmailService.send_email") as mock_send:
        mock_send.return_value = {"status": "sent", "sendgrid_message_id": "msg123"}
        await send_email_task(arq_ctx, str(sample_contact.id), 0)

    # Second send should detect existing event and skip
    with patch("app.services.email.EmailService.send_email") as mock_send:
        await send_email_task(arq_ctx, str(sample_contact.id), 0)
        mock_send.assert_not_called()


# --- Evaluate Contact Tests ---

@pytest.mark.asyncio
async def test_evaluate_skips_already_converted(arq_ctx, db_session, sample_contact):
    """If contact already converted, evaluate should exit immediately."""
    sample_contact.status = "converted"
    await db_session.commit()

    await evaluate_contact(arq_ctx, str(sample_contact.id), 1)

    # No jobs enqueued
    arq_ctx["pool"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_no_reply_enqueues_follow_up(arq_ctx, db_session, sample_contact, sample_campaign):
    """No reply + cadence continues -> enqueue send_follow_up."""
    sample_contact.status = "emailed"
    await db_session.commit()

    await evaluate_contact(arq_ctx, str(sample_contact.id), 1)

    arq_ctx["pool"].enqueue_job.assert_called_once_with(
        "send_follow_up", str(sample_contact.id), 1
    )


# --- Campaign Launch Tests ---

@pytest.mark.asyncio
async def test_launch_validates_pending_contacts(arq_ctx, db_session, sample_campaign):
    """Launch with no pending contacts should raise."""
    # All contacts already emailed
    with pytest.raises(ValueError, match="No contacts with status 'pending'"):
        await launch_campaign(arq_ctx, str(sample_campaign.id))


@pytest.mark.asyncio
async def test_launch_staggered_enqueue(arq_ctx, db_session, sample_campaign, sample_contacts_pending):
    """Verify contacts are enqueued with increasing _defer_by."""
    result = await launch_campaign(arq_ctx, str(sample_campaign.id))

    assert result["enqueued"] == len(sample_contacts_pending)
    calls = arq_ctx["pool"].enqueue_job.call_args_list
    for i, call in enumerate(calls):
        assert call.kwargs["_defer_by"] == timedelta(seconds=i * 5)


# --- Follow-up Scheduling Test ---

@pytest.mark.asyncio
async def test_send_email_schedules_evaluate(arq_ctx, db_session, sample_contact, sample_campaign):
    """After send_email, evaluate_contact should be enqueued with correct _defer_by."""
    # Campaign cadence: day 0 (initial), day 3 (follow_up_1)
    sample_campaign.cadence = [
        {"day": 0, "action": "send_initial"},
        {"day": 3, "action": "follow_up", "template": "follow_up_1"},
    ]
    await db_session.commit()

    with patch("app.services.email.EmailService.send_email") as mock_send:
        mock_send.return_value = {"status": "sent", "sendgrid_message_id": "msg123"}
        await send_email_task(arq_ctx, str(sample_contact.id), 0)

    # Verify evaluate_contact enqueued with 3 days defer
    arq_ctx["pool"].enqueue_job.assert_called_with(
        "evaluate_contact",
        str(sample_contact.id),
        1,
        _defer_by=timedelta(days=3),
    )
```

**Acceptance criteria:**
- All tests use fakeredis (no real Redis required)
- Rate limiter tested for allow, block, and timeout scenarios
- Idempotency verified: same key = skip, different key = send
- evaluate_contact routing tested for all three outcomes
- Campaign launch stagger verified with `_defer_by` assertions
- Follow-up scheduling verified with correct day deltas

---

## Summary: Key Patterns Reference

### Idempotency Pattern (Spec 14.2)

```
Key = f"{contact_id}:{cadence_step}"
1. Check outreach_events for email_sent with metadata.idempotency_key == Key
2. If found → return (already sent)
3. Send via SendGrid
4. Log event with idempotency_key in metadata
```

### Redis Lock Pattern (Spec 14.1)

```
lock_key = f"lock:contact:{contact_id}"
lock = redis.lock(lock_key, timeout=60, blocking_timeout=10)
async with lock:
    # Check status guard first
    if contact.status in terminal_states:
        return
    # Proceed with evaluation
```

### Follow-up Scheduling with _defer_by (Spec 6.5)

```
After send_email completes at cadence_step N:
  next = cadence[N + 1]
  days_until = next["day"] - cadence[N]["day"]
  enqueue("evaluate_contact", contact_id, N+1, _defer_by=timedelta(days=days_until))

evaluate_contact checks:
  - Reply exists?      → classify_reply
  - No reply, more steps? → send_follow_up
  - No reply, close?     → mark unresponsive
```

### Task Chain

```
launch_campaign
  └─ research_contact (staggered _defer_by=i*5s)
       └─ compose_email
            └─ send_email (or wait for human approval)
                 └─ evaluate_contact (_defer_by=cadence days)
                      ├─ classify_reply (if reply exists)
                      ├─ send_follow_up → send_email → evaluate_contact (loop)
                      └─ close (mark unresponsive)
```

---

## File Checklist

| File | Action | Task |
|------|--------|------|
| `app/workers/__init__.py` | Create (empty) | 1 |
| `app/workers/settings.py` | Create | 1, 10 |
| `app/workers/rate_limiter.py` | Create | 2 |
| `app/services/email.py` | Create | 3 |
| `app/workers/tasks.py` | Create | 4, 5, 6, 7, 8, 9 |
| `app/api/campaigns.py` | Modify | 11 |
| `tests/test_workers.py` | Create | 12 |
