# Plan 5: Conversion Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the conversion endpoints that let contacts sign up, book meetings, and make payments — completing the outreach funnel from email to conversion.

**Architecture:** Public endpoints (rate-limited, no auth) for signup forms, Stripe checkout, and Cal.com booking. Each conversion type updates the contact status and fires optional outbound webhooks.

**Tech Stack:** FastAPI, Stripe SDK, httpx (Cal.com + outbound webhooks), SendGrid (confirmation emails), slowapi (rate limiting)

**Depends on:** Plan 1 (models must exist — `campaigns`, `contacts`, `conversions`, `outreach_events` tables and ORM models)

**Spec references:** Sections 4.5, 7, 8.2, 14.6, 14.9, 14.10

---

## Task 1: Conversion Service (`app/services/conversion.py`)

Core service that all three conversion types funnel through.

- [ ] Create `app/services/conversion.py`
- [ ] Implement `process_conversion(contact_id: str, conversion_type: str, data: dict, db: AsyncSession) -> Conversion`:
  1. Fetch the contact and its campaign (raise `404` if not found)
  2. Check for existing conversion on this contact (raise `409 Conflict` if already converted — one conversion per contact per the `unique` constraint on `contact_id`)
  3. Create `Conversion` record with `type` and `data` JSONB
  4. Update `contact.status` to `"converted"`
  5. Log an `outreach_event` with appropriate `event_type`:
     - `signup_completed` for signups
     - `booking_made` for bookings
     - `payment_received` for payments
  6. If `campaign.conversion_config.confirmation_email` is `true`, call `send_confirmation_email()` (Task 1b)
  7. If `campaign.conversion_config.webhook_on_conversion` is set, enqueue `fire_conversion_webhook` arq task (Task 10)
  8. Return the `Conversion` record
- [ ] Implement `send_confirmation_email(contact: Contact, campaign: Campaign, conversion: Conversion)`:
  - Use SendGrid service (`app/services/email.py` — assumed from Plan 1 or created here as a thin wrapper)
  - Template: simple confirmation with campaign name and conversion type
  - From: `campaign.sender_email` / `campaign.sender_name`
  - To: `contact.email`
  - Log `outreach_event` of type `email_sent` with `metadata.purpose = "confirmation"`
- [ ] Add proper error handling: wrap DB operations in try/except, roll back on failure
- [ ] Add logging with `structlog` or stdlib logger: log contact_id, campaign_id, conversion_type on each conversion

**Key design decisions:**
- `process_conversion` is the single entry point — signup, booking, and payment endpoints all call it
- Confirmation email sending is fire-and-forget (don't fail the conversion if email fails, just log the error)
- Webhook firing is async via arq (see Task 10)

---

## Task 2: Signup Endpoints (`app/api/public.py`)

Public-facing signup form endpoints with dynamic field validation.

- [ ] Create `app/api/public.py` with a `public_router = APIRouter(prefix="/api/v1/outreach", tags=["public"])`
- [ ] `GET /signup/{campaign_slug}`:
  1. Fetch campaign by `slug` (raise `404` if not found or not `active`)
  2. Return `conversion_config.signup_fields` array — the field definitions for rendering a form:
     ```python
     class SignupFieldConfig(BaseModel):
         name: str
         type: str  # "text", "boolean", "multi_select", "select"
         required: bool
         options: list[str] | None = None  # for select/multi_select

     class SignupFormResponse(BaseModel):
         campaign_name: str
         campaign_slug: str
         fields: list[SignupFieldConfig]
     ```
  3. Response: `200 OK` with `SignupFormResponse`
- [ ] `POST /signup/{campaign_slug}`:
  1. Fetch campaign by `slug` (raise `404` if not found or not `active`)
  2. Extract `ref` from request body (optional contact UUID)
  3. If `ref` provided, fetch contact and validate it belongs to this campaign
  4. If `ref` not provided, try to match by email field in submission data
  5. Dynamic field validation against `conversion_config.signup_fields`:
     - Check all `required` fields are present and non-empty
     - Validate `multi_select` / `select` values against `options` list
     - Validate `boolean` fields are actual booleans
     - Validate `text` fields are strings (max 1000 chars)
     - Return `422` with per-field errors if validation fails
  6. Call `process_conversion(contact_id, "signup", validated_data)`
  7. Response: `201 Created` with conversion confirmation
- [ ] Create Pydantic schemas in `app/schemas/conversion.py`:
  ```python
  class SignupSubmission(BaseModel):
      ref: str | None = None  # contact UUID from email link
      # remaining fields are dynamic — use model_extra or dict
      model_config = ConfigDict(extra="allow")

  class ConversionResponse(BaseModel):
      id: str
      type: str
      contact_id: str
      message: str
      created_at: datetime
  ```

**Validation logic detail:**
```python
async def validate_signup_fields(
    submission: dict,
    field_configs: list[dict],
) -> tuple[dict, list[dict]]:
    """Returns (validated_data, errors)."""
    validated = {}
    errors = []
    for field in field_configs:
        value = submission.get(field["name"])
        if field["required"] and value is None:
            errors.append({"field": field["name"], "error": "required"})
            continue
        if value is None:
            continue
        match field["type"]:
            case "text":
                if not isinstance(value, str) or len(value) > 1000:
                    errors.append({"field": field["name"], "error": "invalid text"})
                else:
                    validated[field["name"]] = value
            case "boolean":
                if not isinstance(value, bool):
                    errors.append({"field": field["name"], "error": "must be boolean"})
                else:
                    validated[field["name"]] = value
            case "select":
                if value not in field.get("options", []):
                    errors.append({"field": field["name"], "error": f"must be one of {field['options']}"})
                else:
                    validated[field["name"]] = value
            case "multi_select":
                if not isinstance(value, list) or not all(v in field.get("options", []) for v in value):
                    errors.append({"field": field["name"], "error": f"must be list from {field['options']}"})
                else:
                    validated[field["name"]] = value
    return validated, errors
```

---

## Task 3: Signup Form Pre-population from `contact.metadata`

Per spec section 14.10 — reduce friction for contacts arriving from outreach emails.

- [ ] Modify `GET /signup/{campaign_slug}` to accept optional `ref` query parameter
- [ ] When `ref` is provided:
  1. Fetch the contact by UUID
  2. Validate contact belongs to this campaign
  3. Read `contact.metadata` JSONB
  4. For each field in `signup_fields`, check if `contact.metadata` has a matching key
  5. Return pre-populated values alongside field configs:
     ```python
     class SignupFieldWithValue(SignupFieldConfig):
         value: Any | None = None  # pre-populated from contact.metadata

     class SignupFormResponse(BaseModel):
         campaign_name: str
         campaign_slug: str
         fields: list[SignupFieldWithValue]
         contact_name: str | None = None  # for personalising the form
     ```
- [ ] If `ref` is invalid or contact not found, return the form without pre-population (don't error — graceful degradation)
- [ ] Security: do NOT return `contact.email` or `contact.phone` in the pre-populated response (PII filtering)

---

## Task 4: Stripe Service (`app/services/stripe.py`)

Stripe Checkout session creation and webhook processing.

- [ ] Create `app/services/stripe.py`
- [ ] Add Stripe config to `app/config.py`:
  ```python
  STRIPE_SECRET_KEY: str
  STRIPE_WEBHOOK_SECRET: str
  ```
- [ ] Implement `create_checkout_session(contact: Contact, campaign: Campaign) -> str`:
  1. Read `campaign.conversion_config.stripe_price_id`
  2. Read `campaign.conversion_config.payment_mode` (`"one_time"` or `"subscription"`)
  3. Map `payment_mode` to Stripe mode: `"one_time"` -> `"payment"`, `"subscription"` -> `"subscription"`
  4. Create Stripe Checkout Session:
     ```python
     import stripe
     stripe.api_key = settings.STRIPE_SECRET_KEY

     session = stripe.checkout.Session.create(
         mode=stripe_mode,
         line_items=[{"price": price_id, "quantity": 1}],
         client_reference_id=str(contact.id),
         customer_email=contact.email,
         success_url=f"{settings.PUBLIC_BASE_URL}/conversion/success?type=payment",
         cancel_url=f"{settings.PUBLIC_BASE_URL}/conversion/cancelled",
         metadata={
             "campaign_id": str(campaign.id),
             "contact_id": str(contact.id),
         },
     )
     ```
  5. Return `session.url`
- [ ] Implement `handle_stripe_webhook(payload: bytes, sig_header: str, db: AsyncSession) -> None`:
  1. Verify webhook signature:
     ```python
     event = stripe.Webhook.construct_event(
         payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
     )
     ```
  2. Only handle `checkout.session.completed` events (ignore all others)
  3. Extract `client_reference_id` (contact_id) and `metadata.campaign_id`
  4. Build conversion data dict from Stripe session:
     ```python
     data = {
         "stripe_session_id": session.id,
         "payment_intent": session.payment_intent,
         "amount_total": session.amount_total,
         "currency": session.currency,
         "customer_email": session.customer_details.email,
         "payment_status": session.payment_status,
     }
     ```
  5. Call `process_conversion(contact_id, "payment", data, db)`
- [ ] Handle errors: `stripe.error.SignatureVerificationError` returns `400`, other Stripe errors return `500`

---

## Task 5: Stripe Webhook Endpoint (`app/api/webhooks.py`)

- [ ] Create or extend `app/api/webhooks.py` with `webhooks_router = APIRouter(prefix="/api/v1/outreach/webhooks", tags=["webhooks"])`
- [ ] `POST /webhooks/stripe`:
  1. Read raw request body as bytes (important — Stripe signature verification requires raw body)
  2. Read `Stripe-Signature` header
  3. Call `handle_stripe_webhook(payload, sig_header, db)`
  4. Return `200 OK` with `{"status": "ok"}` (Stripe expects 2xx to stop retrying)
  5. On `SignatureVerificationError`: return `400 Bad Request`
  6. On any processing error: log the error but still return `200` to prevent Stripe infinite retries (log for manual investigation)
- [ ] Ensure the endpoint reads raw body, not parsed JSON:
  ```python
  @webhooks_router.post("/stripe")
  async def stripe_webhook(
      request: Request,
      db: AsyncSession = Depends(get_db),
  ):
      payload = await request.body()
      sig_header = request.headers.get("Stripe-Signature")
      if not sig_header:
          raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
      await handle_stripe_webhook(payload, sig_header, db)
      return {"status": "ok"}
  ```
- [ ] Add idempotency check: extract Stripe event ID, check if already processed in `outreach_events.metadata.stripe_event_id`, skip if duplicate

---

## Task 6: Payment Endpoint (`POST /pay/{slug}`)

Public endpoint that initiates a Stripe Checkout session.

- [ ] Add to `app/api/public.py`:
  ```python
  @public_router.post("/pay/{campaign_slug}")
  async def initiate_payment(
      campaign_slug: str,
      ref: str = Query(..., description="Contact UUID from email link"),
      db: AsyncSession = Depends(get_db),
  ):
  ```
- [ ] Implementation:
  1. Fetch campaign by slug (raise `404` if not found or not `active`)
  2. Validate campaign `goal` is `"payment"` (raise `400` if not)
  3. Validate `conversion_config.stripe_price_id` exists (raise `500 / config error` if missing)
  4. Fetch contact by `ref` UUID, validate it belongs to this campaign
  5. Check contact not already converted (raise `409 Conflict` if already has a conversion)
  6. Call `create_checkout_session(contact, campaign)`
  7. Return `200` with `{"checkout_url": session_url}` for client-side redirect
- [ ] Response schema:
  ```python
  class PaymentInitResponse(BaseModel):
      checkout_url: str
      message: str = "Redirecting to payment..."
  ```

---

## Task 7: Cal.com Service (`app/services/cal.py`)

Cal.com webhook handling for booking confirmations.

- [ ] Create `app/services/cal.py`
- [ ] Add Cal.com config to `app/config.py`:
  ```python
  CAL_API_KEY: str
  CAL_WEBHOOK_SECRET: str
  ```
- [ ] Implement `verify_cal_signature(payload: bytes, signature: str) -> bool`:
  - HMAC-SHA256 verification using `CAL_WEBHOOK_SECRET`
  ```python
  import hmac
  import hashlib

  def verify_cal_signature(payload: bytes, signature: str) -> bool:
      expected = hmac.new(
          settings.CAL_WEBHOOK_SECRET.encode(),
          payload,
          hashlib.sha256,
      ).hexdigest()
      return hmac.compare_digest(expected, signature)
  ```
- [ ] Implement `handle_cal_webhook(payload: dict, db: AsyncSession) -> None`:
  1. Only handle `BOOKING_CREATED` event type (ignore cancellations for now)
  2. Extract `contact_id` from booking metadata:
     - Cal.com booking URL includes `?contact={contact_id}` (per spec Section 7.2)
     - This appears in `payload.metadata.contact` or `payload.responses.contact`
  3. Fetch contact, validate exists
  4. Build conversion data:
     ```python
     data = {
         "cal_booking_id": payload.get("bookingId") or payload.get("uid"),
         "event_type": payload.get("eventTitle"),
         "start_time": payload.get("startTime"),
         "end_time": payload.get("endTime"),
         "attendee_email": payload.get("attendees", [{}])[0].get("email"),
         "attendee_name": payload.get("attendees", [{}])[0].get("name"),
         "meeting_url": payload.get("meetingUrl"),
     }
     ```
  5. Call `process_conversion(contact_id, "booking", data, db)`
- [ ] Handle missing `contact_id` in webhook payload: log warning and return `200` (don't break Cal.com's retry cycle)

---

## Task 8: Cal.com Webhook Endpoint (`app/api/webhooks.py`)

- [ ] Add to `app/api/webhooks.py`:
  ```python
  @webhooks_router.post("/cal")
  async def cal_webhook(
      request: Request,
      db: AsyncSession = Depends(get_db),
  ):
  ```
- [ ] Implementation:
  1. Read raw body as bytes
  2. Read signature from headers (Cal.com uses `X-Cal-Signature-256` header)
  3. Verify signature using `verify_cal_signature()` — return `400` if invalid
  4. Parse JSON payload
  5. Call `handle_cal_webhook(payload, db)`
  6. Return `200 OK` with `{"status": "ok"}`
- [ ] Add idempotency: check `outreach_events` for existing `booking_made` event with matching `cal_booking_id` in metadata

---

## Task 9: Booking Endpoint (`POST /book/{slug}`)

Public endpoint that generates a Cal.com booking link with contact tracking.

- [ ] Add to `app/api/public.py`:
  ```python
  @public_router.post("/book/{campaign_slug}")
  async def initiate_booking(
      campaign_slug: str,
      ref: str = Query(..., description="Contact UUID from email link"),
      db: AsyncSession = Depends(get_db),
  ):
  ```
- [ ] Implementation:
  1. Fetch campaign by slug (raise `404` if not found or not `active`)
  2. Validate campaign `goal` is `"booking"` (raise `400` if not)
  3. Validate `conversion_config.cal_event_link` exists
  4. Fetch contact by `ref` UUID, validate it belongs to this campaign
  5. Check contact not already converted (raise `409 Conflict`)
  6. Construct booking URL: append `?contact={contact_id}` to `cal_event_link`
     - If Cal.com link already has query params, use `&contact={contact_id}`
  7. Optionally pre-fill Cal.com fields: `&name={contact.name}&email={contact.email}`
  8. Return `200` with booking URL
- [ ] Response schema:
  ```python
  class BookingInitResponse(BaseModel):
      booking_url: str
      message: str = "Redirecting to booking..."
  ```

---

## Task 10: Outbound Webhook on Conversion with Retry

Per spec Section 14.9 — fire `webhook_on_conversion` URL with retry logic.

- [ ] Create arq task `fire_conversion_webhook` in `app/workers/tasks.py`:
  ```python
  async def fire_conversion_webhook(
      ctx: dict,
      conversion_id: str,
      webhook_url: str,
      attempt: int = 1,
  ):
  ```
- [ ] Implementation:
  1. Fetch conversion record with contact and campaign data
  2. Build webhook payload:
     ```python
     payload = {
         "event": "conversion.completed",
         "conversion_id": str(conversion.id),
         "type": conversion.type,
         "campaign_id": str(campaign.id),
         "campaign_slug": campaign.slug,
         "contact": {
             "id": str(contact.id),
             "name": contact.name,
             "email": contact.email,
             "firm_name": contact.firm_name,
             "metadata": contact.metadata,
         },
         "data": conversion.data,
         "converted_at": conversion.created_at.isoformat(),
     }
     ```
  3. POST to `webhook_url` with `httpx.AsyncClient`:
     - Timeout: 30 seconds
     - Headers: `Content-Type: application/json`, `X-Outreach-Event: conversion.completed`
     - Expect 2xx response
  4. On success: log `outreach_event` with `event_type="webhook_sent"`, `metadata.webhook_url`, `metadata.status_code`
- [ ] Retry logic (3 attempts with exponential backoff via arq):
  - Attempt 1: immediate
  - Attempt 2: defer by 5 seconds
  - Attempt 3: defer by 30 seconds
  - (Spec says 5s, 30s, 5min — but arq `max_tries=3` with `retry_backoff=True` handles this)
  - Implementation option A (arq native): set `max_tries=3` on the task and let arq handle retries
  - Implementation option B (manual): on HTTP error, re-enqueue with incremented `attempt` and `_defer_by`:
    ```python
    backoff_delays = [5, 30, 300]  # seconds
    if attempt <= 3:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook_url, json=payload, timeout=30)
                resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            if attempt < 3:
                delay = backoff_delays[attempt - 1]
                await ctx["redis"].enqueue_job(
                    "fire_conversion_webhook",
                    conversion_id, webhook_url, attempt + 1,
                    _defer_by=timedelta(seconds=delay),
                )
            else:
                # Final failure — log webhook_failed event
                await log_event(
                    contact_id=contact.id,
                    event_type="webhook_failed",
                    metadata={"webhook_url": webhook_url, "error": str(e), "attempts": 3},
                )
    ```
  - **Recommended:** Use option B for explicit control over backoff delays matching the spec (5s, 30s, 5min)
- [ ] Register `fire_conversion_webhook` in `app/workers/settings.py` `WorkerSettings.functions` list
- [ ] Failed webhooks should NOT roll back the conversion — the conversion record is already committed

---

## Task 11: Custom Goal Type — `success_criteria` Matching

Per spec Section 14.6 — campaigns with `goal="custom"` convert based on event matching.

- [ ] Create `app/services/goal_evaluator.py`:
  ```python
  async def evaluate_custom_goal(
      contact_id: str,
      event_type: str,
      event_metadata: dict,
      db: AsyncSession,
  ) -> bool:
  ```
- [ ] Implementation:
  1. Fetch the contact's campaign
  2. If `campaign.goal != "custom"`, return `False`
  3. Read `campaign.success_criteria` JSONB:
     ```json
     {
       "event_type": "reply_classified",
       "classification": "interested"
     }
     ```
  4. Match rules:
     - `success_criteria.event_type` must match the incoming `event_type`
     - All other keys in `success_criteria` are matched against `event_metadata` (flat key-value comparison)
     - Example: `{"event_type": "reply_classified", "classification": "interested"}` matches when a `reply_classified` event is logged with `metadata.classification == "interested"`
  5. If match: call `process_conversion(contact_id, "custom", {"matched_criteria": success_criteria, "trigger_event": event_type}, db)`
  6. Return `True` if converted, `False` if not matched
- [ ] Integration point: call `evaluate_custom_goal()` from the event logging utility (wherever `outreach_events` are created)
  - Specifically, hook into the `classify_reply` task in `app/workers/tasks.py`:
    ```python
    # After logging reply_classified event:
    if campaign.goal == "custom":
        converted = await evaluate_custom_goal(
            contact_id, "reply_classified", classification_result, db
        )
        if converted:
            return  # Don't proceed to other follow-up logic
    ```
- [ ] Support multiple criteria fields (AND logic — all must match)
- [ ] Add a `log_event_and_evaluate()` helper that wraps event creation + custom goal check for reuse

---

## Task 12: Rate Limiting on Public Endpoints (`slowapi`)

Per spec Sections 8.2 and 13 — 10 requests/minute per IP on all public endpoints.

- [ ] Install `slowapi` (already in `pyproject.toml` dependencies)
- [ ] Configure rate limiter in `app/main.py`:
  ```python
  from slowapi import Limiter, _rate_limit_exceeded_handler
  from slowapi.util import get_remote_address
  from slowapi.errors import RateLimitExceeded

  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
  ```
- [ ] Apply rate limits to public endpoints in `app/api/public.py`:
  ```python
  from app.main import limiter

  @public_router.get("/signup/{campaign_slug}")
  @limiter.limit("10/minute")
  async def get_signup_form(request: Request, campaign_slug: str, ...):

  @public_router.post("/signup/{campaign_slug}")
  @limiter.limit("10/minute")
  async def submit_signup(request: Request, campaign_slug: str, ...):

  @public_router.post("/book/{campaign_slug}")
  @limiter.limit("10/minute")
  async def initiate_booking(request: Request, campaign_slug: str, ...):

  @public_router.post("/pay/{campaign_slug}")
  @limiter.limit("10/minute")
  async def initiate_payment(request: Request, campaign_slug: str, ...):
  ```
- [ ] Ensure `Request` is the first parameter (slowapi requirement)
- [ ] Webhook endpoints (`/webhooks/stripe`, `/webhooks/cal`) should NOT be rate-limited (they come from trusted services)
- [ ] Return `429 Too Many Requests` with `Retry-After` header on rate limit exceeded
- [ ] Consider: use Redis backend for rate limiting in production (default is in-memory, which doesn't work across multiple workers):
  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address

  limiter = Limiter(
      key_func=get_remote_address,
      storage_uri=settings.REDIS_URL,  # Redis-backed for multi-worker
  )
  ```

---

## Task 13: Tests for All 3 Conversion Types + Webhook Retry

- [ ] Create `tests/test_conversions.py`
- [ ] **Test fixtures** (shared):
  ```python
  @pytest.fixture
  async def signup_campaign(db):
      """Campaign with goal=signup and signup_fields config."""

  @pytest.fixture
  async def booking_campaign(db):
      """Campaign with goal=booking and cal_event_link config."""

  @pytest.fixture
  async def payment_campaign(db):
      """Campaign with goal=payment and stripe_price_id config."""

  @pytest.fixture
  async def contact(db, signup_campaign):
      """Contact in emailed status with metadata."""
  ```

- [ ] **Signup tests:**
  - `test_get_signup_form_returns_field_config` — GET returns correct fields
  - `test_get_signup_form_with_prepopulation` — GET with `ref` returns values from contact.metadata
  - `test_get_signup_form_invalid_slug_404` — nonexistent campaign slug
  - `test_post_signup_success` — valid submission creates conversion, updates contact status to `converted`
  - `test_post_signup_missing_required_field_422` — missing required field returns validation error
  - `test_post_signup_invalid_multi_select_422` — value not in options list
  - `test_post_signup_already_converted_409` — duplicate conversion attempt
  - `test_post_signup_invalid_ref_graceful` — bad ref still allows signup (matches by email)

- [ ] **Booking tests:**
  - `test_initiate_booking_returns_url` — POST returns Cal.com URL with contact param
  - `test_initiate_booking_wrong_goal_400` — campaign goal is not `booking`
  - `test_cal_webhook_creates_conversion` — valid Cal.com webhook creates conversion
  - `test_cal_webhook_invalid_signature_400` — bad HMAC signature rejected
  - `test_cal_webhook_missing_contact_id_logged` — missing contact gracefully handled
  - `test_cal_webhook_idempotent` — duplicate booking ID does not create duplicate conversion

- [ ] **Payment tests:**
  - `test_initiate_payment_returns_checkout_url` — POST returns Stripe session URL (mock `stripe.checkout.Session.create`)
  - `test_initiate_payment_wrong_goal_400` — campaign goal is not `payment`
  - `test_stripe_webhook_creates_conversion` — valid `checkout.session.completed` webhook creates conversion
  - `test_stripe_webhook_invalid_signature_400` — bad signature rejected
  - `test_stripe_webhook_idempotent` — duplicate event ID does not create duplicate conversion
  - `test_stripe_webhook_ignores_other_events` — non-checkout events return 200 but no conversion

- [ ] **Webhook retry tests:**
  - `test_conversion_webhook_fires_on_success` — mock httpx, verify POST to webhook URL with correct payload
  - `test_conversion_webhook_retries_on_failure` — mock httpx to fail, verify re-enqueue with backoff delay
  - `test_conversion_webhook_logs_failure_after_3_attempts` — verify `webhook_failed` event logged
  - `test_conversion_webhook_does_not_rollback_conversion` — conversion record persists even if webhook fails

- [ ] **Custom goal tests:**
  - `test_custom_goal_converts_on_matching_event` — `reply_classified` with `interested` triggers conversion
  - `test_custom_goal_no_match_no_conversion` — `reply_classified` with `declined` does not trigger
  - `test_custom_goal_ignored_for_signup_campaigns` — non-custom goal campaigns skip evaluation

- [ ] **Rate limiting tests:**
  - `test_public_endpoint_rate_limited` — 11th request within 1 minute returns `429`
  - `test_webhook_endpoint_not_rate_limited` — webhook endpoints accept unlimited requests

- [ ] **Mocking strategy:**
  - Stripe: mock `stripe.checkout.Session.create` and `stripe.Webhook.construct_event`
  - Cal.com: mock HMAC verification for valid/invalid cases
  - SendGrid: mock email sending (already handled if Plan 1 has email service mocks)
  - httpx: mock `httpx.AsyncClient.post` for outbound webhook tests
  - arq: mock `arq.connections.ArqRedis.enqueue_job` to verify task enqueueing

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `app/services/conversion.py` | Create | Core conversion processor + confirmation email |
| `app/services/stripe.py` | Create | Stripe checkout session + webhook handler |
| `app/services/cal.py` | Create | Cal.com webhook handler + signature verification |
| `app/services/goal_evaluator.py` | Create | Custom goal type evaluation |
| `app/api/public.py` | Create | Public signup/book/pay endpoints (rate-limited) |
| `app/api/webhooks.py` | Create | Stripe + Cal.com inbound webhook endpoints |
| `app/schemas/conversion.py` | Create/Extend | Pydantic models for conversion requests/responses |
| `app/workers/tasks.py` | Extend | Add `fire_conversion_webhook` task |
| `app/workers/settings.py` | Extend | Register new task in `WorkerSettings.functions` |
| `app/main.py` | Extend | Add slowapi limiter + public/webhook routers |
| `app/config.py` | Extend | Add Stripe + Cal.com settings |
| `tests/test_conversions.py` | Create | All conversion + webhook + rate limit tests |

---

## Dependency Graph

```
Task 1 (conversion service)
├── Task 2 (signup endpoints) ← depends on Task 1
│   └── Task 3 (pre-population) ← depends on Task 2
├── Task 4 (stripe service) ← depends on Task 1
│   ├── Task 5 (stripe webhook endpoint) ← depends on Task 4
│   └── Task 6 (payment endpoint) ← depends on Task 4
├── Task 7 (cal.com service) ← depends on Task 1
│   ├── Task 8 (cal.com webhook endpoint) ← depends on Task 7
│   └── Task 9 (booking endpoint) ← depends on Task 7
├── Task 10 (outbound webhook) ← depends on Task 1
└── Task 11 (custom goal) ← depends on Task 1

Task 12 (rate limiting) ← depends on Tasks 2, 6, 9
Task 13 (tests) ← depends on all above
```

**Recommended implementation order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13
