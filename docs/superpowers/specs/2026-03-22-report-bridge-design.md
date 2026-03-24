# adil-report-bridge — Design Specification

**Date:** 2026-03-22
**Status:** Approved
**Author:** AskAdil Development Team

---

## Overview

A standalone FastAPI microservice that uses AI-powered browser automation (browser-use + Gemini Flash) to submit hate crime reports to external reporting portals on behalf of AskAdil users. Deployed as a private internal service on Railway, called by the RAG API.

The bridge is **target-agnostic** — adding a new reporting portal (Tell MAMA, Police Scotland, IRU) requires only a new configuration entry, not new scraper code. The AI agent reads form labels semantically and adapts to UI changes.

---

## Architecture

```
User (Chainlit / Telegram / any client)
    │
    │  "I want to report this to police"
    │  → AskAdil collects PII in-chat
    │  → User reviews and confirms submission
    │
    ▼
RAG API  ──POST /api/v1/submit-report──►  Report Bridge (internal)
    │                                          │
    │                                    ┌─────┴─────┐
    │                                    │ browser-use│
    │                                    │ + Gemini   │
    │                                    │ + Playwright│
    │                                    └─────┬─────┘
    │                                          │
    │                                    Fills & submits form
    │                                    Captures confirmation
    │                                    Screenshots result
    │                                          │
    │  ◄──── { success, reference, screenshot }┘
    │
    ▼
User sees: confirmation, reference number, screenshot
"Please save this reference number. AskAdil does not
 store your personal information after submission."
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Calling pattern | RAG API calls bridge internally | Single gateway for all clients (Chainlit, Telegram, mobile). Bridge stays private. |
| LLM for automation | Gemini Flash | Already have API key, cheapest (~$0.01/submission), forms are structured not adversarial. |
| PII retention | Pass-through, purge immediately | No database needed. User told to save reference number. Email receipt is roadmap item. |
| Failure handling | Fail fast + fallback text | If bridge fails, RAG API generates Tier 1 incident summary for manual submission. No retry queue (would require PII persistence). |
| Deployment | Separate Railway service | Playwright+Chromium is ~400MB, different scaling needs, browser crash shouldn't take down query API. |
| Authentication | Shared secret (`BRIDGE_API_KEY`) | Railway private networking is not sufficient — any co-located service could reach the bridge. Mirror the `ADIL_API_KEY` pattern. |
| Concurrency | Semaphore (max 1 concurrent submission) | Chromium is memory-heavy. Two simultaneous sessions will OOM a typical Railway container. Additional requests wait up to 30s for the semaphore; if not acquired, return 503 Service Busy. |
| Duplicate protection | RAG API must never retry a submission | No idempotency key needed at bridge level — the RAG API is the single caller and must disable retry. |

---

## Timeout Chain

| Hop | Timeout | Rationale |
|-----|---------|-----------|
| Frontend → RAG API | 120s | Already set in Chainlit httpx client |
| RAG API → Bridge | 90s | Must be less than frontend timeout to allow fallback generation |
| Bridge → Form submission | 60s | browser-use agent timeout for the full form flow |
| Bridge → Screenshot capture | 10s | After submission, capture confirmation quickly |

---

## Bridge Service API

### Authentication

All bridge endpoints require `X-Bridge-Key` header matching the `BRIDGE_API_KEY` environment variable. Requests without a valid key receive 403.

### POST /submit

Submits a report to the specified target form.

**Request:**

```json
{
  "target": "police-uk",
  "data": {
    "first_name": "Ahmad",
    "surname": "Hassan",
    "dob": { "day": "15", "month": "06", "year": "1990" },
    "gender": "male",
    "email": "ahmad@example.com",
    "phone": "07700900123",
    "address": "123 High Street, London",
    "role": "victim",
    "incident_details": "On 10 March 2026, outside Whitechapel station...",
    "location": "Whitechapel Road, London E1",
    "date_time": "10 March 2026, approximately 5:30pm",
    "suspect_description": "White male, approximately 40 years old, wearing a grey jacket",
    "additional_info": "Submitted via AskAdil (askadil.org) on behalf of the reporter.",
    "evidence_urls": ["https://twitter.com/example/status/123456"]
  }
}
```

**Success Response (200):**

```json
{
  "success": true,
  "reference_number": "HC-2026-12345",
  "confirmation_screenshot": "<base64 png, max 500KB, resized to 1024px wide>",
  "confirmation_text": "Your report has been submitted to [force name].",
  "target": "police-uk",
  "submitted_at": "2026-03-22T19:30:00Z"
}
```

**Failure Response (200 with success=false):**

```json
{
  "success": false,
  "error": "Form submission failed — site unreachable",
  "fallback_report": "--- INCIDENT REPORT SUMMARY ---\nGenerated by AskAdil...\n...",
  "target_url": "https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/"
}
```

Note: Failures return 200 with `success: false` because the bridge operated correctly — it's the external form that failed. HTTP errors (4xx/5xx) are reserved for bridge-level errors (bad request, service down).

### GET /health

Liveness probe. Returns bridge health only — does NOT check external targets (so it stays fast and doesn't depend on third-party availability).

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### GET /health/targets

Checks external target form reachability. Cached for 5 minutes. Not used for liveness probes.

```json
{
  "targets": {
    "police-uk": { "reachable": true, "last_checked": "2026-03-22T19:00:00Z" }
  }
}
```

### GET /targets

Returns available submission targets and their required fields.

```json
{
  "police-uk": {
    "name": "Police UK — National Hate Crime Report",
    "url": "https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
    "required_fields": ["first_name", "surname", "dob", "gender", "email", "incident_details", "location", "date_time"],
    "optional_fields": ["phone", "address", "suspect_description", "evidence_urls"],
    "coverage": "England & Wales"
  }
}
```

---

## Target Configuration

Each reporting portal is defined as a config entry. Adding a new target site means adding configuration, not writing scraper code.

```python
TARGETS = {
    "police-uk": {
        "name": "Police UK — National Hate Crime Report",
        "url": "https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
        "instructions": (
            "Fill the multi-step hate crime reporting form with the provided data. "
            "Step 1: Enter personal details (first name, surname, date of birth, gender). "
            "Step 2: Enter contact details (email, phone, address). "
            "Step 3: Select role (victim, witness, or third party). "
            "Step 4: Enter incident details (what happened, where, when). "
            "Step 5: Add any evidence or URLs. "
            "Step 6: Enter suspect description if provided. "
            "Step 7: Review all details and submit. "
            "Always add 'Submitted via AskAdil (askadil.org) on behalf of the reporter' "
            "in the additional information field. "
            "After submission, capture the confirmation page including any reference number."
        ),
        "required_fields": [
            "first_name", "surname", "dob", "gender", "email",
            "incident_details", "location", "date_time"
        ],
        "optional_fields": [
            "phone", "address", "role", "suspect_description",
            "additional_info", "evidence_urls"
        ],
        "coverage": "England & Wales",
    },
    # Future targets (not in MVP):
    # "tell-mama": { ... },
    # "police-scotland": { ... },
    # "iru": { ... },
}
```

---

## RAG API Changes

### New Endpoint: POST /api/v1/submit-report

Added to the existing RAG API. This is the public-facing endpoint that clients call.

**Request:**

```json
{
  "target": "police-uk",
  "reporter": {
    "first_name": "Ahmad",
    "surname": "Hassan",
    "dob": { "day": "15", "month": "06", "year": "1990" },
    "gender": "male",
    "email": "ahmad@example.com",
    "phone": "07700900123",
    "address": "123 High Street, London"
  },
  "incident": {
    "details": "On 10 March 2026, outside Whitechapel station...",
    "location": "Whitechapel Road, London E1",
    "date_time": "10 March 2026, approximately 5:30pm",
    "suspect_description": "White male, approximately 40 years old",
    "role": "victim"
  },
  "evidence_urls": [],
  "conversation_history": []
}
```

**Behaviour:**

1. Validate request (all required fields present for the target)
2. Transform nested public format → flat bridge format:
   - `reporter.first_name` → `data.first_name`
   - `reporter.dob` → `data.dob`
   - `incident.details` → `data.incident_details`
   - `incident.location` → `data.location`
   - etc.
3. Call bridge service at `POST <BRIDGE_INTERNAL_URL>/submit` with `X-Bridge-Key` header
4. If bridge succeeds → return confirmation, reference number, screenshot
5. If bridge fails → use Gemini to generate a Tier 1 incident summary from `conversation_history` as fallback (this is the sole purpose of `conversation_history` in this endpoint — it is NOT sent to the bridge)
6. PII is never written to disk or database — pass-through only
7. RAG API must NEVER retry the bridge call — a failed submission is treated as final to prevent duplicate police reports

**Response (success):**

```json
{
  "success": true,
  "target": "police-uk",
  "reference_number": "HC-2026-12345",
  "confirmation_screenshot": "<base64 png>",
  "message": "Your hate crime report has been submitted to Police UK. Please save reference number HC-2026-12345.",
  "submitted_at": "2026-03-22T19:30:00Z"
}
```

**Response (failure with fallback):**

```json
{
  "success": false,
  "target": "police-uk",
  "error": "Automated submission failed. Please submit manually using the report below.",
  "fallback_report": "--- INCIDENT REPORT SUMMARY ---\n...",
  "target_url": "https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
  "form_guide": "Step 1: Enter your name and date of birth..."
}
```

### New Endpoint: GET /api/v1/report-targets

Returns available reporting targets with required fields, so the frontend knows what PII to collect.

---

## Frontend (Chainlit) Changes

### Submission Flow

1. After intake conversation, if user wants to report:
   - AskAdil calls `GET /api/v1/report-targets` to get available targets
   - Shows options: *"I can submit a report for you to: Police UK (England & Wales). Which would you like?"*
2. User selects target
3. AskAdil asks for required PII fields one at a time:
   - *"What is your first name?"*
   - *"What is your surname?"*
   - *"What is your date of birth? (DD/MM/YYYY)"*
   - *"What is your gender?"*
   - *"What is your email address?"*
   - *"What is your phone number? (optional)"*
4. AskAdil shows consent summary:
   - *"I will submit a hate crime report to Police UK with the following: [summary of all fields]. Do you confirm? (yes/no)"*
5. User confirms → `POST /api/v1/submit-report`
6. Show result:
   - Success: confirmation message + reference number + screenshot + *"Please save this reference number. AskAdil does not store your personal information after submission."*
   - Failure: fallback report text + manual submission link + form guide

---

## Deployment

### Bridge Service

- **Service name:** `adil-report-bridge`
- **Dockerfile:** Python 3.11-slim + Playwright + Chromium
- **Port:** Injected by Railway (`$PORT`)
- **Internal only:** No public domain — accessible via Railway private networking
- **Env vars:**
  - `GOOGLE_API_KEY` — Google API key for Gemini via langchain-google-genai (set in Railway dashboard)
  - `GEMINI_MODEL` — model for browser-use agent (default: `gemini-2.5-flash`)
  - `BRIDGE_API_KEY` — shared secret for RAG API → Bridge authentication
  - `PORT` — injected by Railway

### Dockerfile sketch

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Playwright system dependencies + Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxdamage1 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

# Security: run as non-root user
RUN useradd -m appuser
USER appuser

ENV PORT=8000 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
```

### RAG API changes

- Add env var: `REPORT_BRIDGE_URL` — internal Railway URL of the bridge service
- Add env var: `BRIDGE_API_KEY` — shared secret for authenticating with the bridge
- Add `httpx` call to bridge in the new `/api/v1/submit-report` endpoint (httpx already a dependency)
- httpx client must set `timeout=90.0` (fits within the 120s frontend timeout, leaves time for fallback generation)

---

## Security

- **No public access:** Bridge has no public domain. Only the RAG API can reach it via Railway internal networking.
- **Bridge authentication:** `BRIDGE_API_KEY` shared secret in `X-Bridge-Key` header. Railway private networking alone is not sufficient.
- **No PII persistence:** Reporter data passes through memory only. Never written to disk, database, or logs.
- **PII excluded from logs:** The RAG API and bridge must never log PII fields. Log only: target, success/fail, timestamp, reference number.
- **Rate limited:** Existing RAG API rate limiter covers the submit-report endpoint.
- **Attribution:** Every submission includes "Submitted via AskAdil (askadil.org)" so the receiving organisation knows the source.
- **Consent required:** Frontend must collect explicit user consent before calling submit-report.
- **Concurrency limit:** Bridge uses an asyncio semaphore (max 1) to prevent concurrent Chromium sessions from exhausting memory.
- **Non-root Chromium:** Dockerfile runs Chromium as a non-root user for container security.

### PII Lifecycle

```
1. User provides PII in Chainlit chat
   → held in Chainlit session memory (volatile)

2. Frontend sends to RAG API /api/v1/submit-report
   → held in request memory only, never logged

3. RAG API transforms and forwards to Bridge /submit
   → held in request memory only, never logged

4. Bridge passes to browser-use agent
   → agent types values into form fields
   → Playwright page closed after submission

5. Bridge returns confirmation (no PII) to RAG API

6. RAG API returns confirmation (no PII) to frontend

7. PII exists only in Chainlit session memory
   → cleared when session ends or tab closes
```

**Limitations acknowledged:** PII in memory can theoretically leak via crash dumps or OS swap. Mitigations:
- `PYTHONDONTWRITEBYTECODE=1` in Dockerfile (reduces disk writes generally)
- Explicit `del` of PII variables after use in bridge agent
- Railway containers are ephemeral (no persistent swap)
- These are best-effort; full memory encryption requires infrastructure-level controls outside MVP scope

---

## Failure Handling

| Failure | Bridge returns | RAG API does |
|---------|---------------|-------------|
| Target site unreachable | `success: false` + error | Generate Tier 1 fallback report |
| Form structure changed | `success: false` + error | Generate Tier 1 fallback report |
| CAPTCHA detected | `success: false` + error | Generate Tier 1 fallback report + flag for manual review |
| Timeout (>60s) | `success: false` + error | Generate Tier 1 fallback report |
| Bridge service down | HTTP error | Generate Tier 1 fallback report |
| Invalid/missing fields | HTTP 422 | Return validation error to client |

**Fallback report** is a structured incident summary (Tier 1 from the reporting roadmap) that the user can copy-paste into the form manually.

**Health monitoring:** Bridge exposes `GET /health/targets` which periodically loads each target URL (without submitting) to verify accessibility. RAG API can check this to warn users proactively if a target is down.

---

## File Structure

```
adil-report-bridge/
├── app.py                 # FastAPI app, /submit, /health, /targets endpoints
├── browser_agent.py       # browser-use integration, runs form submission
├── targets.py             # Target configuration (TARGETS dict)
├── models.py              # Pydantic request/response models
├── screenshot.py          # Screenshot capture + resize/compress to max 500KB
├── Dockerfile
├── requirements.txt
├── railway.toml
└── tests/
    └── test_targets.py    # Config validation tests
```

---

## Dependencies

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
browser-use>=0.2.0
playwright>=1.40.0
langchain-google-genai>=2.0.0
python-dotenv>=1.0.0
pydantic>=2.5.0
httpx>=0.25.0
Pillow>=10.0.0
```

---

## Implemented Post-Design Additions

The following features were added after the original spec was approved:

### Additional Bridge Targets (7 total, up from 1)

| Target | Adapter | PII Required | Coverage |
|--------|---------|-------------|----------|
| Police UK | Browser | Yes | England & Wales |
| Tell MAMA | Browser | Yes | UK-wide |
| Police Scotland | Browser | Yes | Scotland |
| IRU | Browser | Yes | UK-wide |
| Islamophobia UK | Browser | No (anonymous) | UK-wide |
| EASS | Email (SendGrid) | Yes | England, Wales & Scotland |
| Stop Hate UK | Email (SendGrid) | Yes | UK-wide |

### Email Adapter
- New `email_adapter.py` in bridge service
- Sends structured HTML+plain-text incident reports via SendGrid
- Used for organisations that accept reports via email (EASS, Stop Hate UK)
- `adapter_type` field in target config routes to browser or email adapter

### Email Receipts
- New `email_receipt.py` in RAG API
- After successful report submission, sends confirmation email to user
- Includes: reference number, incident summary, next steps, useful links
- Sent from `noreply@mcbx.app` via SendGrid
- Skipped for anonymous targets (no email to send to)

### Anonymised Conversation Logging
- New `conversation_log.py` in RAG API
- Logs to Postgres: topic category, jurisdiction, message count, response time, tokens
- No PII ever written — only classified metadata
- Fire-and-forget (never blocks responses)

### Consumer API Improvements
- `GET /api/v1/privacy-notice` — structured JSON privacy notice (no auth)
- `consent_confirmed: bool` required on submit-report (rejects if false)
- `pii_required: bool` added to report-targets response
- `ConversationTurn.role` documented as `"model"` not `"assistant"` (Gemini convention)

### Privacy & GDPR
- Privacy notice drafted at `docs/privacy-notice.md`
- Enhanced consent screen in Chainlit with data handling explanation
- Cancel support during PII collection
- GDPR compliance section added to reporting roadmap
- 24 organisations in RAG resource directory (5 new: BTP, Muslim Safety Net, British Muslim Trust, Islamophobia UK, Prevent Watch)

---

## Roadmap (Post-MVP)

| Item | Priority | Notes |
|------|----------|-------|
| Email receipt (SendGrid/Resend) | High | Send confirmation + full submission details to user's email |
| Tell MAMA target | High | Add config entry after form analysis |
| Police Scotland target | High | Add config entry, form already analysed in roadmap doc |
| IRU target | Medium | Add config entry after form analysis |
| TPRC registration with NPCC | High | Legitimise server-IP submissions, MCB to lead |
| Submission queue with retry | Low | Requires PII persistence, revisit after email receipt |
| Form change monitoring | Medium | Automated tests that load each form weekly, alert on structure changes |
| Evidence file uploads | Medium | MVP supports evidence URLs only; file upload to forms requires Playwright file chooser handling |
| Dry-run mode | Medium | `POST /submit` with `dry_run: true` fills form but does not click Submit — useful for testing and demos |
| Structured logging | Low | JSON-structured logs with correlation IDs across RAG API → Bridge |

---

## Police.uk Form Field Mapping (MVP Target)

Based on form analysis performed 2026-03-22.

**Form URL:** `https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/`
**Form type:** Multi-step JavaScript wizard (7 steps)

| Step | Fields | Source |
|------|--------|--------|
| 1. Your details | First name, Surname, DOB (D/M/Y), Gender (F/M/Self-describe) | User provides in chat |
| 2. Contact details | Email, Phone, Address | User provides in chat |
| 3. Your role | Victim / Witness / Third party | From conversation context |
| 4. Incident details | What happened, Where, When | From AskAdil intake |
| 5. Evidence | URLs, file uploads, descriptions | Evidence URLs from conversation |
| 6. Suspects | Description of suspect(s) | From conversation if provided |
| 7. Review | Review all + submit | AI agent reviews and submits |

**Terms of Service assessment (2026-03-22):**
- ToS: No explicit prohibition on automated form submission
- Privacy policy: Records IP + browser details for "misuse investigation" — automated submissions from a known service IP are not inherently misuse
- robots.txt: Does NOT block `/ro/` reporting form paths
- Recommendation: Proceed, but accelerate TPRC registration to formally legitimise the approach
