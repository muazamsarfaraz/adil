# QA test guide — adil-outreach-engine + local mailbox

This is the hand-off doc for the **AskAdil team** to validate the outreach engine end-to-end against a local docker-mailserver stack — no SendGrid keys, no real emails, no production risk.

## What's new in this build

| Change | Why |
|---|---|
| **Pluggable email transport** | `EMAIL_TRANSPORT=smtp` swaps SendGrid for any SMTP server (e.g. the local mailbox stack). Production default is still `sendgrid`. No application code changed. |
| **Idempotency race fix** | Concurrent workers processing the same `(contact, cadence_step)` now serialise on a Redis lock and re-check the DB inside it. Eliminates the double-send window. |
| **`List-Unsubscribe` header** | Required by Gmail/Outlook 2024 for senders >5k/day; good practice for all. Both `mailto:` and `https://` forms emitted, plus `List-Unsubscribe-Post: List-Unsubscribe=One-Click` when a URL is configured. |
| **Integration tests are opt-in** | Default `pytest` runs only deterministic unit tests (222 pass). Real-world tests (LLM, scraper, SMTP) run with `pytest --run-integration`. |

## 1. Run the unit tests

```powershell
cd E:\dev\mcbx\adil\adil-outreach-engine
python -m pytest -q
```

**Expected:** `222 passed, 23 skipped, 0 failed`. (23 skipped = integration tests, opt-in below.)

## 2. Bring up the local mailbox stack

If it's not already running:

```powershell
docker compose -f E:\dev\experiments\mailbox\compose.yml up -d
# wait for healthy:
docker inspect -f "{{.State.Health.Status}}" mailserver
```

Confirm the roster (who you can authenticate as):

```powershell
Get-Content E:\dev\experiments\mailbox\data\config\roster.yaml
```

Pick any two agents from different domains, e.g. `ceo@alpha.test` (sender) and `founder@beta.test` (recipient). Default password for all agents: `agentpass`.

## 3. Run the integration tests

```powershell
python -m pytest tests/integration/test_smtp_transport.py -v --run-integration
```

**Expected:** 5 tests pass, ~10s.

What each test proves:
- `test_smtp_transport_delivers_to_mailbox` — `EmailService` with `EMAIL_TRANSPORT=smtp` actually delivers.
- `test_smtp_transport_preserves_threading_headers` — `In-Reply-To` + `References` survive transport.
- `test_smtp_transport_custom_args_become_x_headers` — `contact_id` / `campaign_id` arrive as `X-Custom-*` headers (visible to the mailbox event log).
- `test_smtp_transport_writes_list_unsubscribe_header` — `List-Unsubscribe` + `List-Unsubscribe-Post` headers land on the message.
- `test_smtp_transport_bad_auth_raises_permanent_error` — wrong password raises `SendGridPermanentError` (preserved exception name, so `tasks.py` retry logic still works).

## 4. Run a real campaign against mailbox

This is the headline test: a full outreach flow with real LLM drafts, real SMTP delivery, real IMAP inspection.

**Create `.env` at the project root:**

```dotenv
# Switch the engine to local SMTP
EMAIL_TRANSPORT=smtp
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USERNAME=ceo@alpha.test
SMTP_PASSWORD=agentpass
SMTP_USE_STARTTLS=true
SMTP_VERIFY_CERTS=false

# LLM (required for the engine — pick one provider)
ANTHROPIC_API_KEY=sk-ant-...
# OR
# GEMINI_API_KEY=...
# OPENAI_API_KEY=...

# Postgres / Redis (your usual local config)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/outreach
REDIS_URL=redis://localhost:6379

# Public URL for unsubscribe links — anything will do for testing
PUBLIC_BASE_URL=http://localhost:8001

# SendGrid key not needed when EMAIL_TRANSPORT=smtp, but keep blank
SENDGRID_API_KEY=
```

**Spin up the workers + app:**

```powershell
# Terminal 1 — arq worker
python -m arq app.workers.worker.WorkerSettings

# Terminal 2 — API
uvicorn app.main:app --reload --port 8001

# Terminal 3 — mailbox TUI to watch conversations live
cd E:\dev\experiments\mailbox
python -m tui
```

**Send a test contact through the pipeline** (using existing tooling):

```powershell
# Use the existing test script
python scripts/test_send_to_self.py
```

Or POST manually:

```powershell
$body = @{
    campaign_id = "<your campaign id>"
    email = "founder@beta.test"
    name = "Test Founder"
} | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri "http://localhost:8001/api/v1/outreach/contacts" `
    -Headers @{ "X-API-Key" = "change-me-in-production"; "Content-Type" = "application/json" } `
    -Body $body
```

**What to verify:**

1. **TUI thread list** (port nothing — runs in terminal) shows a new thread within 5–10 seconds of approval.
2. **Click the thread** — you see the actual LLM-drafted email rendered.
3. **Reply from `founder@beta.test`** via any IMAP client (or the mailbox runner if you've started it):
   ```powershell
   python E:\dev\experiments\mailbox\scripts\seed.py founder@beta.test ceo@alpha.test "Re: <subject>" "Thanks, sounds interesting!"
   ```
4. **Trigger the inbound webhook** — adil currently reads replies via SendGrid inbound parse, so for full reply flow testing the LMTP→HTTP bridge is needed (roadmap). For now, you can `POST /api/v1/webhooks/sendgrid` with a synthesised payload mimicking SendGrid's format.
5. **Inspect the message headers in the TUI** — confirm `List-Unsubscribe`, `In-Reply-To` (for follow-ups), `X-Custom-contact_id`, `X-Custom-campaign_id` are all present.

## 5. Reset between runs

```powershell
# Wipe all mailbox inboxes
python E:\dev\experiments\mailbox\scripts\wipe.py

# Optional: clear adil's events for a contact
psql $env:DATABASE_URL -c "DELETE FROM outreach_events WHERE contact_id = '<id>';"
```

## 6. Switch back to SendGrid for production

Remove `EMAIL_TRANSPORT=smtp` (or set it to `sendgrid`) and provide `SENDGRID_API_KEY`. Restart workers. Zero code change.

## Known limitations (not fixed in this build — see ROADMAP)

| Limitation | Impact for QA | Roadmap |
|---|---|---|
| **Inbound replies require SendGrid webhook format** | Full reply-classification flow needs a synthesised payload or the LMTP→HTTP bridge. Outbound is fully testable. | mailbox ROADMAP #1 |
| **Cadence follow-ups fire-and-forget on Redis** | If Redis dies between send and next-step schedule, follow-ups are lost. Watch for Redis stability during long campaigns. | Future |
| **Webhook signature verification is config-toggle** | `sendgrid_webhook_verify_enabled` can be disabled. Always keep it `True` in any environment reachable from outside localhost. | Future |
| **Dry-run bypasses the SendGrid rate limiter** | Dry-run mode doesn't throttle (by design — it's for testing). Don't infer rate-limit behaviour from dry-run runs. | Future |
| **LLM classifier drifts on edge cases** | `test_classify_node_real_llm` currently fails (LLM returns `question` for some "yes interested" phrasings). Real bug worth investigating in the classifier prompt. | Open |
| **Scraper smoke test depends on external sites** | `test_scrape_aramas` failing means a target site changed, not necessarily that the scraper is broken. Re-pin the test target. | Open |

## Sign-off checklist for AskAdil team

- [ ] `python -m pytest -q` → 222 passed, 0 failed
- [ ] `python -m pytest --run-integration tests/integration/test_smtp_transport.py` → 5 passed
- [ ] Full real-campaign run end-to-end (section 4) lands a real LLM-drafted message in the mailbox TUI
- [ ] Threading: a follow-up at cadence_step=1 shows `In-Reply-To` matching the initial send's Message-ID
- [ ] `List-Unsubscribe` header visible on every outbound message in the TUI
- [ ] Switching `EMAIL_TRANSPORT` back to `sendgrid` (with valid key) still works against a SendGrid staging account
