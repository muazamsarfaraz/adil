# adil-outreach-engine: Design Specification

**Date:** 26 March 2026
**Status:** Approved design — ready for implementation planning
**Service:** `adil-outreach-engine`
**Type:** Independent FastAPI microservice

---

## 1. Purpose

A generic, AI-powered outreach and conversion platform. Manages goal-driven campaigns that research targets, compose personalised emails, handle follow-ups, classify responses, and convert contacts through signup forms, meeting bookings, or payments.

The solicitor directory outreach is the first campaign. The system is designed to run any outreach campaign without code changes — only configuration.

---

## 2. Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **API** | FastAPI + Pydantic v2 | Async, auto-generated OpenAPI docs, matches existing stack |
| **Queue** | arq + Redis | Lightweight async task queue, retry with backoff, deferred scheduling |
| **Intelligence** | LangGraph (StateGraph) | Stateful agent workflows with checkpointing, human-in-the-loop gates |
| **LLM** | Configurable per agent | Gemini Flash (research/classify), Claude Sonnet (compose) — overridable per campaign |
| **Database** | PostgreSQL + SQLAlchemy (async) | Persistent state, campaign data, outreach history |
| **Email** | SendGrid v6 | Outbound sends + inbound parse (reply capture) |
| **Payments** | Stripe Checkout | One-time and subscription billing |
| **Booking** | Cal.com API | Meeting scheduling via webhook |
| **Auth** | API key (internal) + JWT (external portal) | Service-to-service + contact self-service |
| **Deploy** | Docker + Railway | One-click Redis add-on, consistent with existing services |

---

## 3. Data Model

### 3.1 campaigns

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | |
| `name` | text | Human-readable campaign name |
| `slug` | text (unique) | URL-safe identifier for public endpoints |
| `goal` | enum | `signup`, `booking`, `payment`, `custom` |
| `status` | enum | `draft`, `active`, `paused`, `completed` |
| `templates` | jsonb | Email templates with `{{variable}}` slots — keyed by `initial`, `follow_up_1`, etc. |
| `cadence` | jsonb | Follow-up schedule array: `[{"day": 3, "action": "follow_up", "template": "follow_up_1"}, ...]` |
| `llm_config` | jsonb | Per-agent LLM selection: `{"research": {"provider": "gemini", "model": "gemini-2.5-flash"}, ...}` |
| `research_instructions` | text | Natural language instructions for the research agent |
| `compose_instructions` | text | Natural language instructions for the compose agent |
| `classify_instructions` | text | Natural language instructions for the classify agent |
| `conversion_config` | jsonb | Signup fields, Stripe price ID, Cal.com event link, confirmation email toggle, webhook URL |
| `auto_send` | boolean | If false, emails queue for human approval before sending |
| `sender_name` | text | Display name on outbound emails |
| `sender_email` | text | From address (must be verified in SendGrid) |
| `reply_to` | text | Reply-to address (for inbound parse routing) |
| `success_criteria` | jsonb | What counts as converted (optional custom rules) |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 3.2 contacts

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | |
| `campaign_id` | uuid (FK → campaigns) | |
| `name` | text | Contact person name |
| `email` | text | Primary email |
| `phone` | text (nullable) | |
| `firm_name` | text (nullable) | Organisation name |
| `website` | text (nullable) | For research agent to scrape |
| `metadata` | jsonb | Arbitrary extra data (specialisms, location, source, etc.) |
| `research_data` | jsonb (nullable) | Populated by research agent (best contact, personalisation hooks, SRA status) |
| `status` | enum | `pending`, `researching`, `ready`, `draft_pending`, `emailed`, `replied`, `converted`, `declined`, `unresponsive`, `bounced` |
| `current_cadence_step` | integer | Which step in the cadence array this contact is at |
| `consent` | boolean (nullable) | Explicit consent to be listed/contacted |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Index:** `(campaign_id, status)` for efficient filtering.

### 3.3 outreach_events

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | |
| `contact_id` | uuid (FK → contacts) | |
| `event_type` | enum | `email_sent`, `email_opened`, `email_clicked`, `reply_received`, `reply_classified`, `follow_up_sent`, `draft_created`, `draft_approved`, `signup_completed`, `booking_made`, `payment_received`, `manually_updated` |
| `channel` | enum | `email`, `webhook`, `manual`, `system` |
| `subject` | text (nullable) | Email subject line |
| `content` | text (nullable) | Email body or reply text |
| `metadata` | jsonb | SendGrid message_id, classification result, error details, etc. |
| `created_at` | timestamptz | |

**Index:** `(contact_id, created_at)` for timeline queries.

### 3.4 conversions

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | |
| `contact_id` | uuid (FK → contacts, unique) | One conversion per contact |
| `type` | enum | `signup`, `booking`, `payment` |
| `data` | jsonb | Form submission fields, booking details, or Stripe session data |
| `created_at` | timestamptz | |

### 3.5 agent_checkpoints

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | |
| `contact_id` | uuid (FK → contacts) | Multiple runs possible per contact |
| `run_id` | uuid | Unique per outreach attempt (new run on retry) |
| `graph_name` | text | LangGraph flow identifier |
| `state` | jsonb | Serialised LangGraph checkpoint |
| `current_node` | text | Last completed node in the graph |
| `is_active` | boolean | Only one active checkpoint per contact |
| `updated_at` | timestamptz | |

**Unique constraint:** `(contact_id, is_active)` partial index where `is_active = true` — ensures only one active run per contact. On retry, old checkpoint is marked `is_active = false`.

---

## 4. API Specification

### 4.1 Campaign Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/outreach/campaigns` | Create campaign |
| `GET` | `/api/v1/outreach/campaigns` | List campaigns (`?status=active&limit=50&offset=0`) |
| `GET` | `/api/v1/outreach/campaigns/{id}` | Get campaign with aggregate stats |
| `PATCH` | `/api/v1/outreach/campaigns/{id}` | Update campaign config |
| `POST` | `/api/v1/outreach/campaigns/{id}/launch` | Activate and enqueue all pending contacts |
| `POST` | `/api/v1/outreach/campaigns/{id}/pause` | Pause all outreach |
| `DELETE` | `/api/v1/outreach/campaigns/{id}` | Soft delete |

**POST /campaigns request body:**
```json
{
  "name": "Solicitor Directory Outreach - Wave 1",
  "slug": "solicitor-wave1",
  "goal": "signup",
  "templates": {
    "initial": {
      "subject": "AskAdil — Free Solicitor Directory Listing",
      "body": "Assalamu Alaikum {{contact_name}},\n\n{{personalised_intro}}\n\n..."
    },
    "follow_up_1": {
      "subject": "Re: AskAdil Directory",
      "body": "Hi {{contact_name}},\n\nJust following up..."
    }
  },
  "cadence": [
    {"day": 0, "action": "send_initial"},
    {"day": 3, "action": "follow_up", "template": "follow_up_1"},
    {"day": 7, "action": "follow_up", "template": "follow_up_2"},
    {"day": 14, "action": "close"}
  ],
  "llm_config": {
    "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "classify": {"provider": "gemini", "model": "gemini-2.5-flash"}
  },
  "research_instructions": "Visit the firm's website...",
  "compose_instructions": "Write a warm, professional email...",
  "classify_instructions": "Classify the reply as: interested, declined, question, out_of_office, bounce.",
  "conversion_config": {
    "type": "signup",
    "signup_fields": [
      {"name": "firm_name", "type": "text", "required": true},
      {"name": "specialisms", "type": "multi_select", "required": true, "options": ["islamic_family_law", "islamic_wills", "islamic_finance", "discrimination"]}
    ],
    "confirmation_email": true,
    "webhook_on_conversion": "https://api.askadil.org/api/v1/solicitors"
  },
  "auto_send": false,
  "sender_name": "AskAdil Team",
  "sender_email": "outreach@askadil.org",
  "reply_to": "outreach@askadil.org"
}
```

**GET /campaigns/{id} response (with stats):**
```json
{
  "id": "...",
  "name": "Solicitor Directory Outreach - Wave 1",
  "status": "active",
  "stats": {
    "total_contacts": 50,
    "pending": 5,
    "researching": 2,
    "emailed": 30,
    "replied": 8,
    "converted": 5,
    "declined": 3,
    "unresponsive": 7,
    "open_rate": 0.73,
    "reply_rate": 0.27,
    "conversion_rate": 0.17
  },
  "...config fields..."
}
```

### 4.2 Contact Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/outreach/campaigns/{id}/contacts` | Add single contact |
| `POST` | `/api/v1/outreach/campaigns/{id}/contacts/bulk` | Bulk import (JSON array or CSV) |
| `GET` | `/api/v1/outreach/campaigns/{id}/contacts` | List contacts (`?status=emailed&limit=50&offset=0`) |
| `GET` | `/api/v1/outreach/contacts/{id}` | Full contact detail + events timeline |
| `PATCH` | `/api/v1/outreach/contacts/{id}` | Update contact |
| `DELETE` | `/api/v1/outreach/contacts/{id}` | Remove from campaign |
| `POST` | `/api/v1/outreach/contacts/{id}/retry` | Re-enqueue failed/unresponsive contact |

**POST /contacts request body:**
```json
{
  "name": "Samara Iqbal",
  "email": "info@aramaslaw.com",
  "firm_name": "Aramas Family Law",
  "website": "https://www.aramaslaw.com",
  "metadata": {
    "specialisms": ["islamic_family_law", "islamic_divorce"],
    "location": "Manchester",
    "source": "web_research",
    "priority": "tier_a"
  }
}
```

**POST /contacts/bulk:** Accepts `Content-Type: application/json` (array) or `multipart/form-data` (CSV upload).

### 4.3 Outreach Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/outreach/contacts/{id}/research` | Manually trigger research agent |
| `GET` | `/api/v1/outreach/contacts/{id}/draft` | Preview personalised email draft |
| `POST` | `/api/v1/outreach/contacts/{id}/approve-draft` | Approve draft, trigger send |
| `POST` | `/api/v1/outreach/contacts/{id}/send` | Force send (bypass queue) |
| `GET` | `/api/v1/outreach/contacts/{id}/events` | Full outreach event timeline |

**GET /contacts/{id}/draft response:**
```json
{
  "contact_id": "...",
  "subject": "AskAdil — Free Solicitor Directory Listing",
  "body": "Assalamu Alaikum Samara,\n\nI noticed Aramas Family Law was recently ranked by Chambers...",
  "personalisation_hooks": ["Chambers ranking", "Islamic Scholar on staff", "Manchester focus"],
  "status": "pending_approval"
}
```

### 4.4 Webhooks (Inbound)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/outreach/webhooks/sendgrid/events` | Delivery, open, click tracking |
| `POST` | `/api/v1/outreach/webhooks/sendgrid/inbound` | Reply parsing (inbound parse) |
| `POST` | `/api/v1/outreach/webhooks/stripe` | Payment confirmations |
| `POST` | `/api/v1/outreach/webhooks/cal` | Booking confirmations |

**SendGrid event webhook payload processing:**
- `delivered` → log event
- `open` → log event, update contact metadata
- `click` → log event with clicked URL
- `bounce` / `dropped` → log event, mark contact status accordingly

**SendGrid inbound parse:**
- Extract `from`, `subject`, `text`, `html` from multipart POST
- Match sender email to contact record
- Enqueue `classify_reply` arq task
- Log `reply_received` event

### 4.5 Public Conversion Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/outreach/signup/{campaign_slug}` | None (rate-limited) | Get signup form config |
| `POST` | `/api/v1/outreach/signup/{campaign_slug}` | None (rate-limited) | Submit signup form |
| `POST` | `/api/v1/outreach/book/{campaign_slug}` | None (rate-limited) | Initiate booking |
| `POST` | `/api/v1/outreach/pay/{campaign_slug}` | None (rate-limited) | Initiate Stripe checkout |

**POST /signup/{slug} request body:**
```json
{
  "ref": "contact_uuid_from_email_link",
  "firm_name": "Aramas Family Law",
  "specialisms": ["islamic_family_law", "islamic_divorce"],
  "free_consultation": true,
  "legal_aid": false,
  "languages": ["English", "Arabic", "Urdu"],
  "preferred_referral_method": "email"
}
```

**Response:** `201 Created` with confirmation details.

### 4.6 Dashboard & Reporting

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/outreach/campaigns/{id}/stats` | Funnel metrics |
| `GET` | `/api/v1/outreach/campaigns/{id}/export` | Export as CSV |
| `GET` | `/api/v1/outreach/health` | Service health (Redis, Postgres, SendGrid) |

---

## 5. Agent Architecture (LangGraph)

### 5.1 Graph Definition

One `StateGraph` per contact, executed as arq tasks.

**State schema:**
```python
class OutreachState(TypedDict):
    contact_id: str
    campaign_id: str
    contact: dict          # contact record
    campaign: dict         # campaign config
    research_data: dict    # populated by research node
    draft_subject: str     # populated by compose node
    draft_body: str        # populated by compose node
    reply_text: str        # populated when reply received
    classification: str    # populated by classify node
    current_step: str      # current node name
    error: str             # last error if any
```

**Graph nodes:**

```
START → research → compose → gate → send → wait
                                              ↓
                              evaluate ← (scheduled by arq)
                                 ↓
                        ┌────────┴────────┐
                        ↓                 ↓
                   reply_exists      no_reply
                        ↓                 ↓
                    classify         follow_up_or_close
                        ↓                 ↓
                 ┌──────┴──────┐    (loops back to compose
                 ↓             ↓     or marks unresponsive)
            interested     declined
                 ↓             ↓
              convert        close
```

**Conditional edges:**
- `gate`: If `campaign.auto_send` is true → `send`. If false → `interrupt` (waits for `/approve-draft`).
- `evaluate`: If reply exists → `classify`. If no reply and cadence steps remain → `follow_up`. If cadence exhausted → `close`.
- `classify`: If `interested` → `convert`. If `declined` → `close`. If `question` → `compose` (reply to question). If `out_of_office` → reschedule evaluate.

### 5.2 Agent Definitions

**Research Agent:**
```
LLM: campaign.llm_config.research (default: gemini-2.5-flash)
System prompt: campaign.research_instructions
Tools:
  - scrape_website(url) → extracted text, contact details, key info
  - search_sra_register(name, firm) → SRA number, regulatory status
  - search_web(query) → web search results for recent news/awards
Output: research_data dict saved to contact record
```

**Compose Agent:**
```
LLM: campaign.llm_config.compose (default: claude-sonnet-4-6)
System prompt: campaign.compose_instructions
Input: campaign template + research_data + outreach history
Output: personalised subject + body with template variables resolved
No tools — pure generation.
```

**Classify Agent:**
```
LLM: campaign.llm_config.classify (default: gemini-2.5-flash)
System prompt: campaign.classify_instructions
Input: reply text + outreach history
Output: structured classification {category, confidence, extracted_data}
No tools — pure classification.
```

### 5.3 Checkpoint & Resume

- After each node completes, LangGraph state serialised to `agent_checkpoints` table
- `current_node` column enables quick status queries without deserialising
- If worker crashes, next pickup reads checkpoint and resumes from last completed node
- Checkpoints expire 30 days after campaign completion (configurable)

### 5.4 LLM Provider Abstraction

```python
def get_llm(config: dict) -> BaseChatModel:
    provider = config["provider"]
    model = config["model"]

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
```

---

## 6. arq Worker

### 6.1 Task Definitions

| Task | Trigger | Does |
|------|---------|------|
| `research_contact` | Campaign launch or manual | Runs research agent → updates contact.research_data → enqueues compose |
| `compose_email` | After research | Runs compose agent → creates draft event → auto-sends or waits for approval |
| `send_email` | After compose (auto) or approval | SendGrid API call → logs event → schedules first evaluate |
| `evaluate_contact` | Deferred by cadence schedule | Checks for replies/opens → routes to classify or follow-up |
| `classify_reply` | SendGrid inbound webhook | Runs classify agent → routes to convert or follow-up |
| `process_conversion` | Signup/booking/payment webhook | Creates conversion record → confirmation email → optional webhook |
| `send_follow_up` | evaluate_contact decides follow-up needed | Runs compose agent with follow-up template → sends |

### 6.2 Worker Configuration

```python
class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    functions = [
        research_contact,
        compose_email,
        send_email,
        evaluate_contact,
        classify_reply,
        process_conversion,
        send_follow_up,
    ]
    max_jobs = 10
    job_timeout = 300          # 5 min per task
    max_tries = 3
    retry_backoff = True
    health_check_interval = 30
    poll_delay = 1.0
```

### 6.3 Rate Limiting

Implemented via Redis counters:

| Resource | Limit | Window |
|----------|-------|--------|
| SendGrid sends | Configurable (default 100/day for free tier) | Per day |
| LLM API calls | Per-provider configurable | Per minute |
| Research scraping | 1 request per 2 seconds | Per domain |

### 6.4 Campaign Launch Flow

```
POST /campaigns/{id}/launch
  1. Validate: campaign has templates, at least 1 contact, LLM config
  2. Set campaign.status = "active"
  3. For each contact where status = "pending":
     - Enqueue research_contact with stagger (_defer_by = i * 5 seconds)
  4. Return {"enqueued": N, "campaign_status": "active"}
```

### 6.5 Follow-up Scheduling

```python
# After send_email completes:
cadence = campaign.cadence
next_step_index = contact.current_cadence_step + 1

if next_step_index < len(cadence):
    next_step = cadence[next_step_index]
    days_until = next_step["day"] - cadence[contact.current_cadence_step]["day"]

    await arq_pool.enqueue_job(
        "evaluate_contact",
        contact_id=contact.id,
        cadence_step=next_step_index,
        _defer_by=timedelta(days=days_until),
    )
```

---

## 7. Conversion Layer

### 7.1 Signup

Campaign defines `conversion_config.signup_fields` — an array of field definitions:

```json
{"name": "firm_name", "type": "text", "required": true}
{"name": "specialisms", "type": "multi_select", "required": true, "options": [...]}
{"name": "free_consultation", "type": "boolean", "required": true}
```

`GET /signup/{slug}` returns the field config (for rendering a form).
`POST /signup/{slug}` validates against the config, creates a conversion, updates contact status.

If `conversion_config.webhook_on_conversion` is set, POST the conversion data to that URL (e.g. to update the solicitor directory in adil-rag-api).

### 7.2 Booking

Campaign stores `conversion_config.cal_event_link` (e.g. `https://cal.com/askadil/onboarding`).

Outreach emails include the link with `?contact={contact_id}` appended.

Cal.com webhook (`POST /webhooks/cal`) fires on booking:
- Match `contact_id` from booking metadata
- Create conversion record (`type=booking`)
- Update contact status → `converted`
- Send confirmation email

### 7.3 Payments

Campaign stores `conversion_config.stripe_price_id` and `conversion_config.payment_mode` (`one_time` or `subscription`).

`POST /pay/{slug}?ref={contact_id}`:
1. Create Stripe Checkout Session with `client_reference_id = contact_id`
2. Return Stripe session URL for redirect

Stripe webhook (`checkout.session.completed`):
- Match `client_reference_id` to contact
- Create conversion record (`type=payment`, data includes Stripe session details)
- Update contact status → `converted`
- Send confirmation email

---

## 8. Authentication & Security

### 8.1 Internal API (Campaign Management)

- **Method:** API key in `X-API-Key` header
- **Storage:** Environment variable `OUTREACH_API_KEY`
- **Scope:** Full access to all campaign/contact endpoints

### 8.2 Public Endpoints (Signup, Book, Pay)

- **Method:** No auth (public-facing)
- **Protection:** Rate limiting via `slowapi` (10 requests/minute per IP)
- **Validation:** `ref` parameter (contact UUID) must exist and belong to the campaign

### 8.3 Webhooks

- **SendGrid:** Signature verification via `X-Twilio-Email-Event-Webhook-Signature`
- **Stripe:** Signature verification via `stripe.Webhook.construct_event()`
- **Cal.com:** HMAC signature verification

### 8.4 Data Protection

- Contact emails and personal data encrypted at application level using `cryptography.fernet` — encrypt `email`, `phone` columns before DB write, decrypt on read. Key stored in env var `ENCRYPTION_KEY`.
- Outreach email content stored for audit trail
- Contact deletion (`DELETE /contacts/{id}`) is hard delete (GDPR right to erasure)
- Campaign export (`GET /campaigns/{id}/export`) for data portability

---

## 9. Project Structure

```
adil-outreach-engine/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app, lifespan, middleware
│   ├── config.py                    # Settings from env vars
│   ├── database.py                  # SQLAlchemy async engine, session
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── campaign.py
│   │   ├── contact.py
│   │   ├── outreach_event.py
│   │   ├── conversion.py
│   │   └── agent_checkpoint.py
│   │
│   ├── schemas/                     # Pydantic request/response models
│   │   ├── campaign.py
│   │   ├── contact.py
│   │   ├── event.py
│   │   ├── conversion.py
│   │   └── stats.py
│   │
│   ├── api/                         # FastAPI routers
│   │   ├── campaigns.py
│   │   ├── contacts.py
│   │   ├── outreach.py              # draft, approve, send
│   │   ├── webhooks.py              # SendGrid, Stripe, Cal.com
│   │   ├── public.py                # signup, book, pay
│   │   └── dashboard.py             # stats, export, health
│   │
│   ├── agents/                      # LangGraph agent definitions
│   │   ├── graph.py                 # Main outreach StateGraph
│   │   ├── nodes/
│   │   │   ├── research.py
│   │   │   ├── compose.py
│   │   │   ├── classify.py
│   │   │   ├── send.py
│   │   │   └── evaluate.py
│   │   ├── tools/
│   │   │   ├── scraper.py           # Website scraping tool
│   │   │   ├── sra.py               # SRA register lookup
│   │   │   └── web_search.py        # Web search tool
│   │   ├── llm.py                   # LLM provider abstraction
│   │   └── state.py                 # OutreachState TypedDict
│   │
│   ├── workers/                     # arq task definitions
│   │   ├── tasks.py                 # All arq task functions
│   │   ├── settings.py              # WorkerSettings
│   │   └── rate_limiter.py          # Redis-based rate limiting
│   │
│   ├── services/                    # Business logic
│   │   ├── email.py                 # SendGrid send/parse
│   │   ├── stripe.py                # Stripe checkout/webhook
│   │   ├── cal.py                   # Cal.com integration
│   │   └── conversion.py            # Conversion processing
│   │
│   └── auth/
│       ├── api_key.py               # Internal API key auth
│       └── webhook_verify.py        # Webhook signature verification
│
├── migrations/                      # Alembic migrations
│   └── versions/
│
├── tests/
│   ├── test_campaigns.py
│   ├── test_contacts.py
│   ├── test_agents.py
│   ├── test_webhooks.py
│   └── test_conversions.py
│
├── docs/
│   └── 2026-03-26-outreach-engine-design.md  # This file
│
├── Dockerfile
├── docker-compose.yml               # Local dev (FastAPI + Redis + Postgres)
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md
```

---

## 10. Configuration (.env)

```bash
# Service
OUTREACH_API_KEY=xxx
OUTREACH_PORT=8001

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/outreach

# Redis
REDIS_URL=redis://host:6379/0

# SendGrid
SENDGRID_API_KEY=xxx
SENDGRID_WEBHOOK_VERIFICATION_KEY=xxx

# Stripe
STRIPE_SECRET_KEY=xxx
STRIPE_WEBHOOK_SECRET=xxx

# Cal.com
CAL_API_KEY=xxx
CAL_WEBHOOK_SECRET=xxx

# LLM Providers (agents use whichever is configured per campaign)
GEMINI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
OPENAI_API_KEY=xxx
```

---

## 11. First Campaign: Solicitor Directory Outreach

The design is validated by loading the existing solicitor directory data as the first campaign:

```bash
# 1. Create campaign
POST /api/v1/outreach/campaigns
  → body: solicitor outreach config (templates from outreach-plan.md)

# 2. Bulk import contacts
POST /api/v1/outreach/campaigns/{id}/contacts/bulk
  → body: 50 firms from solicitor-directory-comprehensive.json

# 3. Launch
POST /api/v1/outreach/campaigns/{id}/launch
  → Researches all 50 firms, composes personalised emails, queues for approval

# 4. Review drafts
GET /api/v1/outreach/contacts/{id}/draft
  → Review each personalised email

# 5. Approve and send
POST /api/v1/outreach/contacts/{id}/approve-draft
  → Sends email, schedules follow-ups

# 6. Monitor
GET /api/v1/outreach/campaigns/{id}/stats
  → Track funnel: 50 → emailed → opened → replied → converted
```

---

## 12. Dependencies

```toml
[project]
name = "adil-outreach-engine"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.0",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "arq>=0.26",
    "redis>=5.0",
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "langchain-google-genai>=2.0",
    "langchain-anthropic>=0.2",
    "langchain-openai>=0.2",
    "sendgrid>=6.10",
    "stripe>=8.0",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "slowapi>=0.1",
    "python-multipart>=0.0.9",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "httpx", "fakeredis", "factory-boy"]
```

---

## 13. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| API response time | < 200ms for CRUD, < 5s for agent triggers |
| Email delivery | 99%+ via SendGrid |
| Agent task timeout | 5 minutes max |
| Task retry | 3 attempts with exponential backoff |
| Concurrent tasks | 10 (arq workers) |
| Data retention | Outreach events retained indefinitely; checkpoints expire after 30 days |
| Rate limits (public) | 10 req/min per IP |
| Uptime | 99.5% (Railway SLA) |

---

## 14. Edge Cases & Safety (Review Addendum)

### 14.1 Race Condition: classify_reply vs evaluate_contact (CRITICAL)

Both the inbound webhook (`classify_reply`) and the deferred cadence scheduler (`evaluate_contact`) can fire concurrently for the same contact.

**Solution:** Redis distributed lock per contact_id. Both tasks acquire `lock:contact:{id}` before executing. Additionally, `evaluate_contact` checks contact status — if already `replied`, `converted`, or `declined`, it exits immediately.

```python
async def evaluate_contact(ctx, contact_id: str, cadence_step: int):
    async with redis_lock(ctx["redis"], f"lock:contact:{contact_id}", timeout=60):
        contact = await get_contact(contact_id)
        if contact.status in ("replied", "converted", "declined", "bounced"):
            return  # Another task already handled this contact
        # ... proceed with evaluation
```

### 14.2 Idempotent Email Sends (CRITICAL)

Retries after partial failure (SendGrid accepted but DB write failed) must not send duplicates.

**Solution:** Idempotency key = `contact_id + cadence_step`. Before calling SendGrid, check `outreach_events` for an existing `email_sent` event with matching metadata. SendGrid also supports `custom_args` for deduplication.

```python
async def send_email(ctx, contact_id: str, cadence_step: int):
    idempotency_key = f"{contact_id}:{cadence_step}"
    existing = await get_event(contact_id, event_type="email_sent", idempotency_key=idempotency_key)
    if existing:
        return  # Already sent
    # ... send via SendGrid, then log event with idempotency_key in metadata
```

### 14.3 Late Replies (after contact marked unresponsive) (CRITICAL)

A contact may reply days after being marked `unresponsive` (e.g. they were on holiday).

**Solution:** The inbound webhook always processes replies regardless of contact status. If contact is `unresponsive` or `declined`, the reply is logged as `reply_received`, the classify agent runs, and if classified as `interested`, the contact status is reopened to `replied`. An `outreach_event` of type `reopened` is logged for audit.

### 14.4 Bounce Handling

**Solution:** SendGrid `bounce` and `dropped` events trigger:
1. Contact status → `bounced`
2. Cancel any deferred `evaluate_contact` arq jobs for this contact (via `arq.jobs.Job.abort()`)
3. Log `email_bounced` event with bounce reason

### 14.5 Campaign Launch Validation

Before launching, validate:
- All templates referenced in `cadence` array exist in `templates` object
- At least 1 contact with status `pending`
- `sender_email` is verified in SendGrid
- LLM config providers have corresponding API keys in env
- If goal is `payment`, `stripe_price_id` exists in conversion_config
- If goal is `booking`, `cal_event_link` exists in conversion_config

Return `422 Unprocessable Entity` with specific validation errors if any check fails.

### 14.6 Custom Goal Type

The `custom` goal type uses `success_criteria` JSONB to define what counts as converted. Format:

```json
{
  "success_criteria": {
    "event_type": "reply_classified",
    "classification": "interested"
  }
}
```

When a matching event is logged, the contact is automatically marked as `converted`. This enables campaigns where conversion = getting a positive reply (no signup form/booking/payment needed).

### 14.7 Email Threading

Follow-up emails include `In-Reply-To` and `References` headers to thread in the recipient's inbox. The initial send stores `sendgrid_message_id` in `outreach_events.metadata`. Follow-up sends read this and set:

```python
headers = {
    "In-Reply-To": f"<{initial_message_id}>",
    "References": f"<{initial_message_id}>",
}
```

### 14.8 LLM Config Extensibility

The `llm_config` JSONB supports optional parameters beyond provider/model:

```json
{
  "research": {
    "provider": "gemini",
    "model": "gemini-2.5-flash",
    "temperature": 0.3,
    "max_tokens": 2000
  },
  "compose": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "temperature": 0.7,
    "max_tokens": 1000
  }
}
```

All optional params are passed through to the LangChain model constructor.

### 14.9 Conversion Webhook Reliability

When `webhook_on_conversion` fires and the target is unavailable:
- Retry 3 times with exponential backoff (5s, 30s, 5min) via arq
- After 3 failures, log a `webhook_failed` event and continue (conversion is still recorded locally)
- Failed webhooks visible in campaign stats for manual retry

### 14.10 Signup Form Pre-population

`GET /signup/{slug}?ref={contact_id}` returns pre-populated field values from `contact.metadata` where field names match, reducing friction for the contact filling the form.

### 14.11 Retry Behaviour

`POST /contacts/{id}/retry`:
1. Marks existing `agent_checkpoint` as `is_active = false`
2. Resets contact status to `pending`
3. Enqueues a fresh `research_contact` task with a new `run_id`
4. Previous outreach events are preserved for audit trail
