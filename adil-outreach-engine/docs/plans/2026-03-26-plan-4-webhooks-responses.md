# Plan 4: Webhooks & Response Handling

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Handle inbound webhooks from SendGrid for email tracking and reply capture, classify responses using the LangGraph classify agent, and manage edge cases like bounces and late replies.

**Architecture:** FastAPI webhook endpoints with signature verification. SendGrid event webhooks for delivery tracking. Inbound parse for reply capture. arq tasks for async classification. Redis locks prevent race conditions.

**Tech Stack:** FastAPI, SendGrid webhook verification, arq, Redis

**Depends on:** Plan 3 (workers and email must exist)

**Spec references:** Sections 4.3, 4.4, 8.3, 14.1, 14.2, 14.3, 14.4

---

## Task 1: Webhook Signature Verification

**File:** `app/auth/webhook_verify.py`

Implement SendGrid webhook signature verification using the `X-Twilio-Email-Event-Webhook-Signature` and `X-Twilio-Email-Event-Webhook-Timestamp` headers.

### Steps

- [ ] **1.1** Create `app/auth/webhook_verify.py` with a `verify_sendgrid_signature` function
  - Accept `request: Request` as parameter
  - Read raw body bytes from the request
  - Extract `X-Twilio-Email-Event-Webhook-Signature` and `X-Twilio-Email-Event-Webhook-Timestamp` headers
  - Use the `SENDGRID_WEBHOOK_VERIFICATION_KEY` from `app/config.py` (added in Plan 1)
  - Verify using SendGrid's ECDSA signature verification:
    ```python
    from sendgrid.helpers.eventwebhook import EventWebhook, EventWebhookHeader

    async def verify_sendgrid_signature(request: Request) -> bool:
        """Verify SendGrid event webhook signature (ECDSA)."""
        body = (await request.body()).decode("utf-8")
        signature = request.headers.get(EventWebhookHeader.SIGNATURE, "")
        timestamp = request.headers.get(EventWebhookHeader.TIMESTAMP, "")

        ew = EventWebhook()
        key = ew.convert_public_key_to_ecdsa(settings.SENDGRID_WEBHOOK_VERIFICATION_KEY)
        return ew.verify_signature(body, signature, timestamp, key)
    ```
  - Return `bool` — `True` if valid, `False` otherwise

- [ ] **1.2** Create a FastAPI dependency `require_sendgrid_signature` that calls `verify_sendgrid_signature` and raises `HTTPException(403)` if invalid
  ```python
  async def require_sendgrid_signature(request: Request) -> None:
      if not await verify_sendgrid_signature(request):
          raise HTTPException(status_code=403, detail="Invalid SendGrid signature")
  ```

- [ ] **1.3** Add a config flag `SENDGRID_WEBHOOK_VERIFY_ENABLED: bool = True` to `app/config.py` so signature verification can be disabled in local dev/testing. The dependency should skip verification when this is `False`.

### Acceptance Criteria
- Valid SendGrid signatures pass through
- Invalid/missing signatures return 403
- Verification can be toggled off for local development

---

## Task 2: SendGrid Event Webhook Endpoint

**File:** `app/api/webhooks.py`

Handle delivery tracking events from SendGrid (delivered, open, click, bounce, dropped).

### Steps

- [ ] **2.1** Create `app/api/webhooks.py` with a FastAPI router (`prefix="/api/v1/outreach/webhooks"`)

- [ ] **2.2** Create Pydantic schema `SendGridEvent` in `app/schemas/webhook.py`
  ```python
  class SendGridEvent(BaseModel):
      email: str
      timestamp: int
      event: str  # delivered, open, click, bounce, dropped, etc.
      sg_message_id: str | None = None
      reason: str | None = None  # bounce reason
      url: str | None = None  # clicked URL
      useragent: str | None = None
      ip: str | None = None
      category: list[str] | None = None
      # custom_args from send — used to match contact
      contact_id: str | None = None
      campaign_id: str | None = None
  ```

- [ ] **2.3** Implement `POST /api/v1/outreach/webhooks/sendgrid/events`
  - Dependency: `require_sendgrid_signature`
  - SendGrid sends a JSON array of events — parse as `list[SendGridEvent]`
  - For each event, process based on `event` type:
    ```python
    @router.post("/sendgrid/events", dependencies=[Depends(require_sendgrid_signature)])
    async def handle_sendgrid_events(
        request: Request,
        events: list[SendGridEvent],
        db: AsyncSession = Depends(get_db),
    ):
        for event in events:
            contact = await match_event_to_contact(db, event)
            if not contact:
                logger.warning(f"No contact found for SendGrid event: {event.email}")
                continue

            match event.event:
                case "delivered":
                    await log_outreach_event(db, contact.id, "email_delivered", metadata={"sg_message_id": event.sg_message_id})

                case "open":
                    await log_outreach_event(db, contact.id, "email_opened", metadata={"ip": event.ip, "useragent": event.useragent})

                case "click":
                    await log_outreach_event(db, contact.id, "email_clicked", metadata={"url": event.url})

                case "bounce" | "dropped":
                    await handle_bounce(db, contact, event)

        return {"status": "ok"}
    ```

- [ ] **2.4** Implement `match_event_to_contact` helper
  - Primary match: use `contact_id` from `custom_args` (set during `send_email` in Plan 3)
  - Fallback: match by decrypted email address + campaign_id
  - Return `Contact | None`

- [ ] **2.5** Implement `log_outreach_event` helper (shared utility in `app/services/events.py`)
  ```python
  async def log_outreach_event(
      db: AsyncSession,
      contact_id: UUID,
      event_type: str,
      channel: str = "email",
      subject: str | None = None,
      content: str | None = None,
      metadata: dict | None = None,
  ) -> OutreachEvent:
      event = OutreachEvent(
          id=uuid4(),
          contact_id=contact_id,
          event_type=event_type,
          channel=channel,
          subject=subject,
          content=content,
          metadata=metadata or {},
          created_at=datetime.utcnow(),
      )
      db.add(event)
      await db.commit()
      return event
  ```

- [ ] **2.6** Register the webhooks router in `app/main.py`

### Acceptance Criteria
- Endpoint accepts SendGrid event webhook payloads
- Events are matched to contacts and logged as `outreach_events`
- Unknown contacts are logged as warnings but don't cause errors
- Endpoint returns 200 quickly (SendGrid retries on non-2xx)

---

## Task 3: Bounce Handling

**Files:** `app/api/webhooks.py`, `app/services/bounce.py`

When a bounce or dropped event is received, mark the contact as bounced and cancel any pending deferred jobs. (Spec section 14.4)

### Steps

- [ ] **3.1** Create `app/services/bounce.py` with `handle_bounce` function
  ```python
  async def handle_bounce(
      db: AsyncSession,
      contact: Contact,
      event: SendGridEvent,
      redis: Redis,
  ) -> None:
      # 1. Update contact status to bounced
      contact.status = ContactStatus.bounced
      await db.commit()

      # 2. Log the bounce event
      await log_outreach_event(
          db,
          contact.id,
          event_type="email_bounced",
          channel="email",
          metadata={
              "reason": event.reason,
              "original_event": event.event,  # "bounce" or "dropped"
              "sg_message_id": event.sg_message_id,
          },
      )

      # 3. Cancel deferred evaluate_contact jobs
      await cancel_deferred_jobs(redis, contact.id)
  ```

- [ ] **3.2** Implement `cancel_deferred_jobs` to abort pending arq jobs for a contact
  ```python
  async def cancel_deferred_jobs(redis: Redis, contact_id: UUID) -> int:
      """Cancel all deferred arq jobs for a given contact.

      Scans the arq deferred job set and aborts jobs matching this contact_id.
      Returns count of cancelled jobs.
      """
      cancelled = 0
      # Get all pending jobs from arq's queue
      # arq stores deferred jobs in a sorted set keyed by queue name
      pool = ArqRedis(redis)
      all_jobs = await pool.queued_jobs()

      for job_info in all_jobs:
          job = Job(job_id=job_info.job_id, redis=redis)
          job_def = await job.info()
          if job_def and job_def.function == "evaluate_contact":
              # Check if args contain our contact_id
              if str(contact_id) in [str(a) for a in (job_def.args or [])]:
                  await job.abort()
                  cancelled += 1
                  logger.info(f"Cancelled deferred evaluate_contact job {job_info.job_id} for contact {contact_id}")

      return cancelled
  ```

- [ ] **3.3** Ensure `evaluate_contact` (from Plan 3) checks for `bounced` status before proceeding — add guard at the top of the task (within the Redis lock):
  ```python
  if contact.status in ("replied", "converted", "declined", "bounced"):
      return  # Another task already handled this contact
  ```

- [ ] **3.4** Add `email_bounced` to the `EventType` enum in `app/models/outreach_event.py` if not already present

### Acceptance Criteria
- Bounce events update contact status to `bounced`
- Deferred `evaluate_contact` jobs are cancelled on bounce
- No follow-up emails are sent to bounced contacts
- Bounce reason is preserved in event metadata

---

## Task 4: SendGrid Inbound Parse Endpoint

**File:** `app/api/webhooks.py`

Handle inbound email replies via SendGrid's Inbound Parse webhook. Extract reply content, match to a contact, and enqueue classification. (Spec section 4.4)

### Steps

- [ ] **4.1** Implement `POST /api/v1/outreach/webhooks/sendgrid/inbound`
  - SendGrid inbound parse sends `multipart/form-data` (NOT JSON)
  - Extract fields: `from`, `to`, `subject`, `text`, `html`, `envelope`, `headers`
  ```python
  @router.post("/sendgrid/inbound")
  async def handle_sendgrid_inbound(
      request: Request,
      db: AsyncSession = Depends(get_db),
      redis: Redis = Depends(get_redis),
  ):
      form = await request.form()

      sender_email = extract_email_from_field(form.get("from", ""))
      to_email = form.get("to", "")
      subject = form.get("subject", "")
      text_body = form.get("text", "")
      html_body = form.get("html", "")

      # Match sender to a contact
      contact = await match_inbound_to_contact(db, sender_email)
      if not contact:
          logger.warning(f"Inbound email from unknown sender: {sender_email}")
          return {"status": "ignored", "reason": "unknown_sender"}

      # Log reply_received event
      await log_outreach_event(
          db,
          contact.id,
          event_type="reply_received",
          channel="email",
          subject=subject,
          content=text_body or html_body,
          metadata={"sender": sender_email, "to": to_email},
      )

      # Update contact status to replied (unless already converted)
      if contact.status not in ("converted",):
          contact.status = ContactStatus.replied
          await db.commit()

      # Enqueue classify_reply task
      pool = await get_arq_pool(redis)
      await pool.enqueue_job("classify_reply", contact_id=str(contact.id))

      return {"status": "ok", "contact_id": str(contact.id)}
  ```

- [ ] **4.2** Implement `extract_email_from_field` helper
  ```python
  def extract_email_from_field(from_field: str) -> str:
      """Extract email address from 'Name <email@example.com>' format."""
      import re
      match = re.search(r'<([^>]+)>', from_field)
      if match:
          return match.group(1).lower()
      return from_field.strip().lower()
  ```

- [ ] **4.3** Implement `match_inbound_to_contact` helper
  - Query contacts where decrypted email matches `sender_email`
  - Filter to campaigns with status `active`
  - If multiple matches (contact in multiple campaigns), prefer the most recently emailed one
  ```python
  async def match_inbound_to_contact(db: AsyncSession, sender_email: str) -> Contact | None:
      """Match an inbound reply to a contact by sender email.

      Returns the most recently emailed contact if there are multiple matches.
      """
      result = await db.execute(
          select(Contact)
          .join(Campaign, Contact.campaign_id == Campaign.id)
          .where(Campaign.status == CampaignStatus.active)
          .where(Contact.status.in_([
              ContactStatus.emailed,
              ContactStatus.replied,
              ContactStatus.unresponsive,
              ContactStatus.declined,
          ]))
          .order_by(Contact.updated_at.desc())
      )
      contacts = result.scalars().all()

      # Decrypt and compare emails
      for contact in contacts:
          if decrypt_field(contact.email) == sender_email:
              return contact

      return None
  ```

- [ ] **4.4** Note: Inbound parse does NOT use SendGrid signature verification (it uses a different mechanism — the parse URL itself is the secret). Add rate limiting via `slowapi` to prevent abuse.

### Acceptance Criteria
- Inbound emails are parsed from multipart form data
- Sender is matched to a contact record
- `reply_received` event is logged with full reply content
- `classify_reply` task is enqueued
- Unknown senders are logged and ignored gracefully

---

## Task 5: classify_reply arq Task

**Files:** `app/workers/tasks.py`, `app/agents/nodes/classify.py`

Run the classify agent on a reply, then route to the appropriate next action (convert, follow-up, close). Includes the critical Redis lock pattern from spec section 14.1.

### Steps

- [ ] **5.1** Implement `classify_reply` arq task in `app/workers/tasks.py`
  ```python
  async def classify_reply(ctx: dict, contact_id: str) -> dict:
      """Classify an inbound reply and route to next action.

      Uses Redis lock to prevent race condition with evaluate_contact.
      See spec section 14.1.
      """
      redis = ctx["redis"]
      lock_key = f"lock:contact:{contact_id}"

      async with redis_lock(redis, lock_key, timeout=60):
          async with get_db_session() as db:
              contact = await get_contact(db, contact_id)
              if not contact:
                  raise ValueError(f"Contact {contact_id} not found")

              campaign = await get_campaign(db, contact.campaign_id)

              # Get the most recent reply_received event
              reply_event = await get_latest_event(
                  db, contact_id, event_type="reply_received"
              )
              if not reply_event:
                  logger.warning(f"No reply event found for contact {contact_id}")
                  return {"status": "no_reply_found"}

              # Get outreach history for context
              history = await get_contact_events(db, contact_id)

              # Run classify agent
              classification = await run_classify_agent(
                  reply_text=reply_event.content,
                  history=history,
                  campaign=campaign,
              )

              # Log classification event
              await log_outreach_event(
                  db,
                  contact.id,
                  event_type="reply_classified",
                  channel="system",
                  metadata={
                      "category": classification["category"],
                      "confidence": classification["confidence"],
                      "extracted_data": classification.get("extracted_data"),
                  },
              )

              # Route based on classification
              await route_classification(
                  ctx, db, contact, campaign, classification
              )

              return {
                  "status": "classified",
                  "category": classification["category"],
                  "confidence": classification["confidence"],
              }
  ```

- [ ] **5.2** Implement `run_classify_agent` in `app/agents/nodes/classify.py`
  ```python
  async def run_classify_agent(
      reply_text: str,
      history: list[OutreachEvent],
      campaign: Campaign,
  ) -> dict:
      """Run the classify LangGraph node.

      Returns: {"category": str, "confidence": float, "extracted_data": dict | None}
      Categories: interested, declined, question, out_of_office, bounce
      """
      llm = get_llm(campaign.llm_config.get("classify", {
          "provider": "gemini", "model": "gemini-2.5-flash"
      }))

      history_text = format_history_for_llm(history)

      prompt = ChatPromptTemplate.from_messages([
          ("system", campaign.classify_instructions or DEFAULT_CLASSIFY_INSTRUCTIONS),
          ("human", CLASSIFY_TEMPLATE),
      ])

      chain = prompt | llm | JsonOutputParser()

      result = await chain.ainvoke({
          "reply_text": reply_text,
          "outreach_history": history_text,
      })

      return result
  ```

- [ ] **5.3** Define `DEFAULT_CLASSIFY_INSTRUCTIONS` and `CLASSIFY_TEMPLATE`
  ```python
  DEFAULT_CLASSIFY_INSTRUCTIONS = """You are a reply classifier for an outreach campaign.
  Classify the reply into exactly one category:
  - interested: The contact expresses interest, asks how to proceed, or agrees
  - declined: The contact explicitly declines or asks to be removed
  - question: The contact asks a question that needs answering
  - out_of_office: An auto-reply or out-of-office message
  - bounce: A delivery failure notification

  Return JSON: {"category": "...", "confidence": 0.0-1.0, "extracted_data": {...}}
  extracted_data should contain any useful structured info from the reply (e.g. preferred contact method, questions asked, reason for declining)."""

  CLASSIFY_TEMPLATE = """## Reply to classify:
  {reply_text}

  ## Previous outreach history:
  {outreach_history}

  Classify this reply. Return JSON only."""
  ```

- [ ] **5.4** Implement `route_classification` to handle each category
  ```python
  async def route_classification(
      ctx: dict,
      db: AsyncSession,
      contact: Contact,
      campaign: Campaign,
      classification: dict,
  ) -> None:
      category = classification["category"]
      redis = ctx["redis"]
      pool = ArqRedis(redis)

      match category:
          case "interested":
              contact.status = ContactStatus.replied
              await db.commit()
              # Cancel deferred evaluate jobs — contact is now in active conversation
              await cancel_deferred_jobs(redis, contact.id)
              # If campaign goal is custom and success_criteria matches, auto-convert
              if campaign.goal == "custom" and campaign.success_criteria:
                  if campaign.success_criteria.get("classification") == "interested":
                      await pool.enqueue_job("process_conversion", contact_id=str(contact.id), conversion_type="custom")

          case "declined":
              contact.status = ContactStatus.declined
              await db.commit()
              await cancel_deferred_jobs(redis, contact.id)

          case "question":
              # Re-compose a reply addressing the question
              contact.status = ContactStatus.replied
              await db.commit()
              await cancel_deferred_jobs(redis, contact.id)
              await pool.enqueue_job(
                  "compose_email",
                  contact_id=str(contact.id),
                  template_key="reply",
                  reply_context=classification.get("extracted_data", {}),
              )

          case "out_of_office":
              # Reschedule evaluate for later (7 days)
              await pool.enqueue_job(
                  "evaluate_contact",
                  contact_id=str(contact.id),
                  cadence_step=contact.current_cadence_step,
                  _defer_by=timedelta(days=7),
              )

          case "bounce":
              # Treat LLM-detected bounce same as SendGrid bounce
              await handle_bounce_from_reply(db, contact, redis)
  ```

- [ ] **5.5** Implement the `redis_lock` context manager (shared utility in `app/workers/locks.py`)
  ```python
  import asyncio
  from contextlib import asynccontextmanager
  from redis.asyncio import Redis

  @asynccontextmanager
  async def redis_lock(redis: Redis, key: str, timeout: int = 60):
      """Distributed lock using Redis SET NX EX.

      Prevents race condition between classify_reply and evaluate_contact
      operating on the same contact simultaneously (spec section 14.1).

      Args:
          redis: Redis connection
          key: Lock key (e.g. "lock:contact:{contact_id}")
          timeout: Lock TTL in seconds (auto-releases if holder crashes)

      Raises:
          LockAcquisitionError: If lock cannot be acquired after retries
      """
      lock_value = str(uuid4())
      acquired = False
      retries = 0
      max_retries = 10

      try:
          while not acquired and retries < max_retries:
              acquired = await redis.set(key, lock_value, nx=True, ex=timeout)
              if not acquired:
                  retries += 1
                  await asyncio.sleep(0.5 * retries)  # linear backoff

          if not acquired:
              raise LockAcquisitionError(f"Could not acquire lock: {key}")

          yield

      finally:
          # Only release if we still hold the lock (compare-and-delete)
          if acquired:
              current = await redis.get(key)
              if current and current.decode() == lock_value:
                  await redis.delete(key)


  class LockAcquisitionError(Exception):
      pass
  ```

### Acceptance Criteria
- classify_reply acquires Redis lock before processing (prevents race with evaluate_contact)
- Classification result is logged as `reply_classified` event
- Routing correctly handles all 5 categories
- Interested replies cancel deferred jobs
- Questions trigger a compose-reply flow
- Out-of-office replies reschedule evaluation

---

## Task 6: Late Reply Handling

**Files:** `app/api/webhooks.py`, `app/workers/tasks.py`

Handle replies from contacts already marked as `unresponsive` or `declined`. Reopen them when appropriate. (Spec section 14.3)

### Steps

- [ ] **6.1** Update the inbound parse handler (Task 4) to process replies regardless of contact status
  - Remove any status check that would skip unresponsive/declined contacts
  - Always log `reply_received` and enqueue `classify_reply`

- [ ] **6.2** Update `classify_reply` routing to handle late replies
  ```python
  # Add at the start of route_classification, before the match statement:
  was_late_reply = contact.status in (
      ContactStatus.unresponsive,
      ContactStatus.declined,
  )
  ```

- [ ] **6.3** Add reopening logic for interested late replies
  ```python
  # Inside route_classification, in the "interested" case:
  if was_late_reply:
      await log_outreach_event(
          db,
          contact.id,
          event_type="reopened",
          channel="system",
          metadata={
              "previous_status": contact.status.value,
              "reason": "late_reply_classified_interested",
          },
      )
      logger.info(
          f"Contact {contact.id} reopened from {contact.status.value} "
          f"after late reply classified as interested"
      )
  ```

- [ ] **6.4** Handle late replies classified as `declined` — no reopening, just log
  ```python
  # In the "declined" case:
  if was_late_reply and contact.status == ContactStatus.declined:
      # Already declined, just log the additional reply
      await log_outreach_event(
          db, contact.id,
          event_type="reply_classified",
          channel="system",
          metadata={"note": "Late reply reconfirms declined status"},
      )
      return  # Don't re-update status
  ```

- [ ] **6.5** Add `reopened` to the `EventType` enum in `app/models/outreach_event.py`

### Acceptance Criteria
- Replies from unresponsive contacts are processed (not ignored)
- Interested late replies reopen the contact to `replied` status
- A `reopened` event is logged with the previous status for audit
- Declined late replies do not flip the contact back to active
- Late question replies trigger compose-reply flow

---

## Task 7: Draft Preview and Approval Endpoints

**File:** `app/api/outreach.py`

Endpoints for reviewing and approving email drafts before sending. (Spec section 4.3)

### Steps

- [ ] **7.1** Create Pydantic schemas in `app/schemas/outreach.py`
  ```python
  class DraftResponse(BaseModel):
      contact_id: UUID
      subject: str
      body: str
      personalisation_hooks: list[str]
      status: str  # "pending_approval" or "approved"
      created_at: datetime

  class DraftApprovalRequest(BaseModel):
      edited_subject: str | None = None  # Optional: approve with edits
      edited_body: str | None = None
  ```

- [ ] **7.2** Implement `GET /api/v1/outreach/contacts/{id}/draft`
  ```python
  @router.get("/contacts/{contact_id}/draft", response_model=DraftResponse)
  async def get_draft(
      contact_id: UUID,
      db: AsyncSession = Depends(get_db),
      _: str = Depends(require_api_key),
  ):
      contact = await get_contact_or_404(db, contact_id)

      # Find the most recent draft_created event
      draft_event = await get_latest_event(
          db, contact_id, event_type="draft_created"
      )
      if not draft_event:
          raise HTTPException(404, "No draft found for this contact")

      return DraftResponse(
          contact_id=contact.id,
          subject=draft_event.subject,
          body=draft_event.content,
          personalisation_hooks=draft_event.metadata.get("personalisation_hooks", []),
          status="pending_approval" if contact.status == ContactStatus.draft_pending else "approved",
          created_at=draft_event.created_at,
      )
  ```

- [ ] **7.3** Implement `POST /api/v1/outreach/contacts/{id}/approve-draft`
  ```python
  @router.post("/contacts/{contact_id}/approve-draft")
  async def approve_draft(
      contact_id: UUID,
      approval: DraftApprovalRequest | None = None,
      db: AsyncSession = Depends(get_db),
      redis: Redis = Depends(get_redis),
      _: str = Depends(require_api_key),
  ):
      contact = await get_contact_or_404(db, contact_id)

      if contact.status != ContactStatus.draft_pending:
          raise HTTPException(400, f"Contact status is {contact.status}, expected draft_pending")

      # Get draft event
      draft_event = await get_latest_event(db, contact_id, event_type="draft_created")
      if not draft_event:
          raise HTTPException(404, "No draft found for this contact")

      # Apply edits if provided
      subject = approval.edited_subject if (approval and approval.edited_subject) else draft_event.subject
      body = approval.edited_body if (approval and approval.edited_body) else draft_event.content

      # Log approval event
      await log_outreach_event(
          db, contact.id,
          event_type="draft_approved",
          channel="manual",
          subject=subject,
          content=body,
          metadata={
              "was_edited": bool(
                  approval and (approval.edited_subject or approval.edited_body)
              ),
          },
      )

      # Enqueue send_email task
      pool = ArqRedis(redis)
      await pool.enqueue_job(
          "send_email",
          contact_id=str(contact.id),
          subject=subject,
          body=body,
          cadence_step=contact.current_cadence_step,
      )

      return {"status": "approved", "contact_id": str(contact.id)}
  ```

- [ ] **7.4** Register the outreach router in `app/main.py`

### Acceptance Criteria
- GET draft returns the latest pending draft with personalisation hooks
- POST approve-draft accepts optional edits before approving
- Approval enqueues `send_email` task
- Non-draft_pending contacts cannot be approved (400 error)
- Drafts can be approved with modifications

---

## Task 8: Contact Events Timeline Endpoint

**File:** `app/api/outreach.py`

Full event timeline for a contact, used by the dashboard. (Spec section 4.3)

### Steps

- [ ] **8.1** Create Pydantic schema in `app/schemas/event.py`
  ```python
  class OutreachEventResponse(BaseModel):
      id: UUID
      event_type: str
      channel: str
      subject: str | None
      content: str | None
      metadata: dict
      created_at: datetime

  class EventTimelineResponse(BaseModel):
      contact_id: UUID
      contact_name: str
      contact_status: str
      events: list[OutreachEventResponse]
      total_events: int
  ```

- [ ] **8.2** Implement `GET /api/v1/outreach/contacts/{id}/events`
  ```python
  @router.get("/contacts/{contact_id}/events", response_model=EventTimelineResponse)
  async def get_contact_events_timeline(
      contact_id: UUID,
      limit: int = Query(50, ge=1, le=200),
      offset: int = Query(0, ge=0),
      event_type: str | None = Query(None, description="Filter by event type"),
      db: AsyncSession = Depends(get_db),
      _: str = Depends(require_api_key),
  ):
      contact = await get_contact_or_404(db, contact_id)

      query = (
          select(OutreachEvent)
          .where(OutreachEvent.contact_id == contact_id)
          .order_by(OutreachEvent.created_at.desc())
      )

      if event_type:
          query = query.where(OutreachEvent.event_type == event_type)

      # Get total count
      count_query = select(func.count()).select_from(
          query.subquery()
      )
      total = (await db.execute(count_query)).scalar()

      # Get paginated results
      result = await db.execute(query.offset(offset).limit(limit))
      events = result.scalars().all()

      return EventTimelineResponse(
          contact_id=contact.id,
          contact_name=decrypt_field(contact.name),
          contact_status=contact.status.value,
          events=[
              OutreachEventResponse(
                  id=e.id,
                  event_type=e.event_type,
                  channel=e.channel,
                  subject=e.subject,
                  content=e.content,
                  metadata=e.metadata,
                  created_at=e.created_at,
              )
              for e in events
          ],
          total_events=total,
      )
  ```

- [ ] **8.3** Add index verification — ensure `(contact_id, created_at)` index exists on `outreach_events` table (should be created in Plan 1 migration, verify here)

### Acceptance Criteria
- Returns paginated event timeline sorted by newest first
- Supports optional `event_type` filter
- Returns total count for pagination
- Includes contact name and current status in response

---

## Task 9: Tests for All Webhook Scenarios

**File:** `tests/test_webhooks.py`

Comprehensive tests for delivery tracking, bounce handling, inbound replies, classification routing, and late replies.

### Steps

- [ ] **9.1** Set up test fixtures
  ```python
  @pytest.fixture
  async def active_campaign(db):
      """Campaign with auto_send=True for testing."""
      ...

  @pytest.fixture
  async def emailed_contact(db, active_campaign):
      """Contact with status=emailed and a sent email event."""
      ...

  @pytest.fixture
  async def unresponsive_contact(db, active_campaign):
      """Contact with status=unresponsive (cadence exhausted)."""
      ...

  @pytest.fixture
  def mock_sendgrid_signature():
      """Bypass signature verification for tests."""
      ...
  ```

- [ ] **9.2** Test SendGrid event webhook — delivered
  ```python
  async def test_sendgrid_event_delivered(client, emailed_contact, mock_sendgrid_signature):
      response = await client.post(
          "/api/v1/outreach/webhooks/sendgrid/events",
          json=[{
              "email": "test@example.com",
              "event": "delivered",
              "timestamp": 1711411200,
              "sg_message_id": "abc123",
              "contact_id": str(emailed_contact.id),
          }],
      )
      assert response.status_code == 200

      # Verify event was logged
      events = await get_events_for_contact(emailed_contact.id)
      assert any(e.event_type == "email_delivered" for e in events)
  ```

- [ ] **9.3** Test SendGrid event webhook — opened
  ```python
  async def test_sendgrid_event_opened(client, emailed_contact, mock_sendgrid_signature):
      response = await client.post(
          "/api/v1/outreach/webhooks/sendgrid/events",
          json=[{
              "email": "test@example.com",
              "event": "open",
              "timestamp": 1711411200,
              "contact_id": str(emailed_contact.id),
              "useragent": "Mozilla/5.0",
              "ip": "1.2.3.4",
          }],
      )
      assert response.status_code == 200
      events = await get_events_for_contact(emailed_contact.id)
      assert any(e.event_type == "email_opened" for e in events)
  ```

- [ ] **9.4** Test bounce handling — status update + job cancellation
  ```python
  async def test_bounce_handling(client, emailed_contact, mock_sendgrid_signature, redis):
      response = await client.post(
          "/api/v1/outreach/webhooks/sendgrid/events",
          json=[{
              "email": "test@example.com",
              "event": "bounce",
              "timestamp": 1711411200,
              "contact_id": str(emailed_contact.id),
              "reason": "550 User not found",
          }],
      )
      assert response.status_code == 200

      # Verify contact status changed to bounced
      contact = await get_contact(emailed_contact.id)
      assert contact.status == ContactStatus.bounced

      # Verify bounce event logged
      events = await get_events_for_contact(emailed_contact.id)
      bounce_events = [e for e in events if e.event_type == "email_bounced"]
      assert len(bounce_events) == 1
      assert bounce_events[0].metadata["reason"] == "550 User not found"
  ```

- [ ] **9.5** Test inbound reply parsing + classify enqueue
  ```python
  async def test_inbound_reply(client, emailed_contact, mock_classify):
      response = await client.post(
          "/api/v1/outreach/webhooks/sendgrid/inbound",
          data={
              "from": "Samara Iqbal <info@aramaslaw.com>",
              "to": "outreach@askadil.org",
              "subject": "Re: AskAdil Directory",
              "text": "Thanks for reaching out, we'd love to be listed!",
          },
      )
      assert response.status_code == 200

      # Verify reply_received event
      events = await get_events_for_contact(emailed_contact.id)
      reply_events = [e for e in events if e.event_type == "reply_received"]
      assert len(reply_events) == 1
      assert "love to be listed" in reply_events[0].content

      # Verify contact status updated to replied
      contact = await get_contact(emailed_contact.id)
      assert contact.status == ContactStatus.replied
  ```

- [ ] **9.6** Test classify_reply — interested classification
  ```python
  async def test_classify_reply_interested(arq_ctx, emailed_contact, mock_llm):
      mock_llm.return_value = {
          "category": "interested",
          "confidence": 0.95,
          "extracted_data": {"preferred_contact": "email"},
      }

      result = await classify_reply(arq_ctx, contact_id=str(emailed_contact.id))
      assert result["category"] == "interested"

      # Verify classification event logged
      events = await get_events_for_contact(emailed_contact.id)
      assert any(e.event_type == "reply_classified" for e in events)
  ```

- [ ] **9.7** Test classify_reply — declined classification
  ```python
  async def test_classify_reply_declined(arq_ctx, emailed_contact, mock_llm):
      mock_llm.return_value = {
          "category": "declined",
          "confidence": 0.90,
          "extracted_data": {"reason": "not interested at this time"},
      }

      result = await classify_reply(arq_ctx, contact_id=str(emailed_contact.id))
      assert result["category"] == "declined"

      contact = await get_contact(emailed_contact.id)
      assert contact.status == ContactStatus.declined
  ```

- [ ] **9.8** Test late reply — unresponsive contact reopened
  ```python
  async def test_late_reply_reopens_unresponsive(client, unresponsive_contact, arq_ctx, mock_llm):
      # Simulate inbound reply from unresponsive contact
      await client.post(
          "/api/v1/outreach/webhooks/sendgrid/inbound",
          data={
              "from": f"contact <{unresponsive_contact.email}>",
              "to": "outreach@askadil.org",
              "subject": "Re: AskAdil Directory",
              "text": "Sorry for the late reply, yes we're interested!",
          },
      )

      # Simulate classify_reply with interested result
      mock_llm.return_value = {
          "category": "interested",
          "confidence": 0.92,
          "extracted_data": {},
      }
      await classify_reply(arq_ctx, contact_id=str(unresponsive_contact.id))

      # Verify contact was reopened
      contact = await get_contact(unresponsive_contact.id)
      assert contact.status == ContactStatus.replied

      # Verify reopened event exists
      events = await get_events_for_contact(unresponsive_contact.id)
      reopened_events = [e for e in events if e.event_type == "reopened"]
      assert len(reopened_events) == 1
      assert reopened_events[0].metadata["previous_status"] == "unresponsive"
  ```

- [ ] **9.9** Test Redis lock prevents race condition
  ```python
  async def test_classify_evaluate_race_condition(arq_ctx, emailed_contact, mock_llm, redis):
      """Verify that classify_reply and evaluate_contact cannot run simultaneously."""
      mock_llm.return_value = {
          "category": "interested",
          "confidence": 0.95,
          "extracted_data": {},
      }

      # Acquire lock manually to simulate classify_reply holding it
      lock_key = f"lock:contact:{emailed_contact.id}"
      await redis.set(lock_key, "test-holder", nx=True, ex=60)

      # evaluate_contact should wait/retry, not process simultaneously
      with pytest.raises(LockAcquisitionError):
          await asyncio.wait_for(
              evaluate_contact(arq_ctx, str(emailed_contact.id), cadence_step=1),
              timeout=6.0,  # Must exceed lock retry window
          )

      await redis.delete(lock_key)
  ```

- [ ] **9.10** Test unknown sender inbound reply
  ```python
  async def test_inbound_reply_unknown_sender(client):
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
  ```

- [ ] **9.11** Test signature verification rejects invalid signatures
  ```python
  async def test_invalid_sendgrid_signature(client, emailed_contact):
      """Without mock signature bypass, invalid signatures should be rejected."""
      response = await client.post(
          "/api/v1/outreach/webhooks/sendgrid/events",
          json=[{"email": "test@example.com", "event": "delivered", "timestamp": 123}],
          headers={"X-Twilio-Email-Event-Webhook-Signature": "invalid"},
      )
      assert response.status_code == 403
  ```

- [ ] **9.12** Test draft preview and approval flow
  ```python
  async def test_draft_preview_and_approve(client, draft_pending_contact, api_key_header):
      # Get draft
      response = await client.get(
          f"/api/v1/outreach/contacts/{draft_pending_contact.id}/draft",
          headers=api_key_header,
      )
      assert response.status_code == 200
      draft = response.json()
      assert draft["status"] == "pending_approval"
      assert len(draft["personalisation_hooks"]) > 0

      # Approve with edits
      response = await client.post(
          f"/api/v1/outreach/contacts/{draft_pending_contact.id}/approve-draft",
          json={"edited_subject": "Updated Subject"},
          headers=api_key_header,
      )
      assert response.status_code == 200
      assert response.json()["status"] == "approved"
  ```

- [ ] **9.13** Test events timeline endpoint
  ```python
  async def test_events_timeline(client, emailed_contact_with_events, api_key_header):
      response = await client.get(
          f"/api/v1/outreach/contacts/{emailed_contact_with_events.id}/events",
          headers=api_key_header,
      )
      assert response.status_code == 200
      data = response.json()
      assert data["total_events"] > 0
      assert data["contact_status"] == "emailed"
      # Events should be newest first
      timestamps = [e["created_at"] for e in data["events"]]
      assert timestamps == sorted(timestamps, reverse=True)

      # Test event_type filter
      response = await client.get(
          f"/api/v1/outreach/contacts/{emailed_contact_with_events.id}/events?event_type=email_sent",
          headers=api_key_header,
      )
      assert response.status_code == 200
      for e in response.json()["events"]:
          assert e["event_type"] == "email_sent"
  ```

### Acceptance Criteria
- All webhook scenarios have passing tests
- Bounce, reply, and late reply edge cases are covered
- Redis lock race condition is tested
- Signature verification is tested (both valid and invalid)
- Draft approval flow is tested end-to-end
- Events timeline pagination and filtering are tested

---

## File Summary

| File | Purpose |
|------|---------|
| `app/auth/webhook_verify.py` | SendGrid ECDSA signature verification dependency |
| `app/api/webhooks.py` | Webhook router: SendGrid events + inbound parse |
| `app/api/outreach.py` | Draft preview, approval, events timeline |
| `app/schemas/webhook.py` | SendGrid event Pydantic model |
| `app/schemas/outreach.py` | Draft/approval Pydantic models |
| `app/schemas/event.py` | Event timeline Pydantic models |
| `app/services/events.py` | `log_outreach_event` shared helper |
| `app/services/bounce.py` | Bounce handling + deferred job cancellation |
| `app/workers/locks.py` | Redis distributed lock context manager |
| `app/workers/tasks.py` | `classify_reply` task (extends Plan 3) |
| `app/agents/nodes/classify.py` | Classify agent LLM chain |
| `tests/test_webhooks.py` | Comprehensive webhook + response tests |

---

## Key Patterns

### Redis Lock (classify_reply vs evaluate_contact)

```
classify_reply ──┐
                 ├── lock:contact:{id} ──► only one proceeds
evaluate_contact ┘
```

Both tasks acquire `lock:contact:{contact_id}` before modifying contact state. The lock has a 60-second TTL to prevent deadlocks if a worker crashes. The lock uses SET NX EX with a unique value and compare-and-delete on release.

### Event Flow

```
SendGrid event webhook ──► log event ──► (bounce? ──► cancel jobs, update status)
SendGrid inbound parse ──► log reply ──► enqueue classify_reply
classify_reply ──► run LLM ──► route: interested/declined/question/ooo/bounce
Late reply (unresponsive) ──► classify ──► interested? ──► reopen + log "reopened"
```

### Idempotency

- SendGrid events include `sg_message_id` — deduplicate on `(contact_id, event_type, sg_message_id)`
- Inbound parse: check for existing `reply_received` event with same content hash before re-enqueuing classify
