# adil-whatsapp-bridge

WhatsApp Cloud API ⇄ adil-rag-api bridge service for AskAdil.

## Endpoints

| Method | Path        | Purpose                                            |
|--------|-------------|----------------------------------------------------|
| GET    | `/webhook`  | Meta subscription verification (echoes `hub.challenge`) |
| POST   | `/webhook`  | Inbound messages from Meta (HMAC-SHA256 verified) |
| GET    | `/health`   | Liveness probe                                     |
| GET    | `/stats`    | Outbound + session counts (operator key)           |

## Architecture

```
WhatsApp user
   ↓
Meta WhatsApp Business Cloud API  (webhook POST, signed)
   ↓
adil-whatsapp-bridge
   ├─ verify_signature(raw_body, X-Hub-Signature-256, META_APP_SECRET)
   ├─ parse_inbound(payload) → list[InboundMessage]
   ├─ Dispatcher.handle(msg):
   │     1. daily cost cap
   │     2. per-phone rate limit (20/min, 200/day)
   │     3. consent gate (privacy notice → YES)
   │     4. jurisdiction gate (1 / 2 / 3)
   │     5. keywords: reset, delete me, report, help
   │     6. else → rag_client.query() → format → Meta send
   ↓
adil-rag-api /api/v1/query  (X-API-Key, conversation_history)
```

State lives in Postgres table `wa_sessions` (one row per phone). History is
JSONB, trimmed to the last 50 turns. 24-hour session TTL is implicit — the
table is the source of truth and rows age out naturally based on
`last_message_at`.

## Files

| File                              | Purpose                                                       |
|-----------------------------------|---------------------------------------------------------------|
| `app.py`                          | FastAPI app, lifespan, /webhook GET+POST, /health, /stats     |
| `meta_client.py`                  | Graph API wrapper + `verify_signature` HMAC                    |
| `rag_client.py`                   | Async POST to `adil-rag-api /api/v1/query`                     |
| `session.py`                      | Postgres CRUD for `wa_sessions` + rate-limit + cost counters   |
| `handler.py`                      | Dispatcher: parse_inbound + onboarding + keyword routing       |
| `formatter.py`                    | Markdown → WhatsApp + length-aware splitter + source render    |
| `db_migrate.py`                   | Idempotent SQL runner (mirrors adil-rag-api)                   |
| `migrations/001_wa_sessions.sql`  | Schema for `wa_sessions` + `wa_outbound_spend`                 |
| `tests/`                          | Unit tests (formatter, signature, parse_inbound, classifiers) |

## Environment

See `.env.example` for the complete list. Required at runtime:

- `META_APP_SECRET`, `META_VERIFY_TOKEN`, `META_PHONE_NUMBER_ID`, `META_ACCESS_TOKEN`
- `RAG_API_URL`, `RAG_API_KEY` (= `ADIL_API_KEY` on the rag-api side)
- `DATABASE_URL` (shared Postgres with adil-rag-api)

Optional:

- `OPERATOR_KEY` — gates `/stats`
- `WA_RATE_PER_MINUTE` (default 20), `WA_RATE_PER_DAY` (default 200)
- `WA_DAILY_COST_CAP_USD` (default 50)
- `PRIVACY_NOTICE_URL` (default https://askadil.org/privacy)

## Deploy

```bash
cd adil-whatsapp-bridge && railway up
```

Then in the Meta dashboard, set the webhook URL to
`https://<railway-domain>/webhook`, verify with `META_VERIFY_TOKEN`, and
subscribe to the `messages` field.

## Status — what's done vs. blocked

**Implemented (this commit):**

- Service scaffolding, Dockerfile, railway.toml
- `/webhook` GET + POST with HMAC-SHA256 verification
- Meta Graph API client (text send, mark_read)
- Postgres session store + migrations + rate limit + cost cap
- Onboarding flow (consent → jurisdiction → Q&A)
- Markdown → WhatsApp formatter + length splitter + sources/viability render
- Keyword routing (`help`, `reset`, `delete me`, `report`)
- Tests: formatter, signature verification, payload parsing, classifiers

**Blocked on humans (not code):**

- Meta Business Verification for MCB (3–10 day Meta legal review)
- Decision: dedicated MCB WhatsApp number vs reuse existing line
- MCB legal sign-off on privacy notice copy at `askadil.org/privacy`
- Railway service provisioning (`railway init` + env vars in the Railway dashboard)

**Future iterations (left as TODOs in code):**

- Image analysis: `handler.py` currently replies "coming soon" on image-only
  messages. Wire to `/api/v1/query/image` once Meta media download
  (`GET /<media-id>`) is added to `meta_client.py`.
- Twilio sandbox: a thin vendor module under a `WA_VENDOR` env switch — only
  needed for Phase A dev. Phase B (Meta direct) is the prod target.
- MSentry probe: needs an internal probe number to send a heartbeat from; once
  available, add a 5-minute cron that texts the probe and watches for echo.
