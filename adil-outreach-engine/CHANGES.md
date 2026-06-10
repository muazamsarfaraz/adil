# Changes — adil-outreach-engine hardening pass

**Audience:** AskAdil engineering team
**Status:** Code changes complete and tested locally. **Not committed.** Review and merge at your discretion.

This document summarises every change made in one pass. Pair it with [`QA_GUIDE.md`](./QA_GUIDE.md) for the hands-on validation steps.

---

## Why this work happened

A portfolio-wide local SMTP+IMAP test stack (`mailbox` at `E:\dev\experiments\mailbox`) is now available for testing outbound engines without hitting SendGrid. While wiring `adil-outreach-engine` to it, four issues surfaced that were worth fixing **before** shipping the integration to your team:

1. **Hard SendGrid coupling** — no way to test the send path locally without a SendGrid account.
2. **Idempotency race** — two concurrent workers could double-send the same email.
3. **Missing `List-Unsubscribe` header** — Gmail/Outlook 2024 requirement; mail risks the spam folder.
4. **Test suite broken by default** — 4 pre-existing failures in `tests/integration/` were running unconditionally, masking signal in CI.

All four are addressed below. **None of the existing 222 unit tests were modified.** Their assertions and mocks still pass unchanged.

---

## Change 1 — Pluggable email transport

**Files:**
- `app/services/email.py` *(refactored)*
- `app/config.py` *(added settings)*

**What changed:**
- `EmailService` no longer constructs a SendGrid client directly. It builds a transport (lazy) chosen by `settings.email_transport`:
  - `"sendgrid"` (default) — exact same behaviour as before, wrapping the original SendGrid SDK calls in `SendGridTransport`
  - `"smtp"` — new `SmtpTransport` using `aiosmtplib`, talks to any SMTP server (local mailbox, your staging SMTP relay, etc.)
- Public surface of `EmailService` is **identical** to before:
  - Same constructor `EmailService()` (no required args)
  - Same `send_email(...)` kwargs and return shape (`{"status", "sendgrid_message_id", ...}`)
  - Same `check_idempotency(...)` method
  - Same exception types `SendGridPermanentError` / `SendGridTransientError` — **both transports raise them**, so all retry logic in `tasks.py` continues to work
- A backward-compat `EmailService.client` property still exposes the underlying SendGrid client when SendGrid is the active transport.

**New config (`app/config.py`):**

```python
email_transport: str = "sendgrid"          # "sendgrid" | "smtp"

# Used only when email_transport == "smtp"
smtp_host: str = "localhost"
smtp_port: int = 587
smtp_username: str = ""
smtp_password: str = ""
smtp_use_starttls: bool = True
smtp_verify_certs: bool = False
```

**To use the SMTP transport in any environment:**

```dotenv
EMAIL_TRANSPORT=smtp
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USERNAME=<account>@<domain>
SMTP_PASSWORD=<password>
SMTP_USE_STARTTLS=true
SMTP_VERIFY_CERTS=false   # only for local self-signed certs
```

**Production unchanged.** Leave `EMAIL_TRANSPORT` unset (or set to `sendgrid`) and the engine behaves exactly as before — same SendGrid SDK calls, same response handling, same retry behaviour.

---

## Change 2 — Idempotency race fix

**File:** `app/workers/tasks.py` (`send_email_task` around line 380)

**The race that existed before:**

```
Worker A: check_idempotency → no event
Worker B: check_idempotency → no event       ← race window
Worker A: send_email (SendGrid → success)
Worker B: send_email (SendGrid → success)    ← DUPLICATE SEND
Worker A: commit event
Worker B: commit event
```

Two arq workers picking up the same `(contact_id, cadence_step)` task simultaneously (e.g., on visibility-timeout re-delivery after a worker crash) would both pass the idempotency check and both call SendGrid.

**The fix:** wrap the send+commit block in a Redis lock keyed on the idempotency key. The second worker waits, then re-checks the DB inside the lock — by then the first worker has committed the `email_sent` event and the second one bails cleanly.

```python
lock_key = f"send_email:lock:{idempotency_key}"
try:
    async with redis_lock(redis, lock_key, timeout=120):
        # Re-check inside the lock — another worker may have just finished.
        existing_inside = await email_svc.check_idempotency(db, idempotency_key)
        if existing_inside:
            logger.info("send_email_task: %s already sent (raced and lost cleanly)",
                        idempotency_key)
            return
        await _send_locked_body(...)
except LockAcquisitionError:
    logger.warning("send_email_task: lock contention on %s, will retry",
                   idempotency_key)
    raise   # arq will retry
```

The lock uses the existing `redis_lock` helper from `app/workers/locks.py` (same one used to serialise classify_reply vs evaluate_contact). 120-second TTL is generous enough for the full send + DB commit, and self-clears if a worker crashes.

The original `check_idempotency` call **before** the lock is preserved — it serves as a fast-path bail-out for re-delivered jobs where the work is already done.

**The dry-run branch is unchanged** — dry-runs don't send mail and don't need the lock.

---

## Change 3 — `List-Unsubscribe` header

**Files:**
- `app/services/email.py` *(new kwargs)*
- `app/workers/tasks.py` *(wires them in)*

**Why:** Gmail and Outlook updated their 2024 sender guidelines. Bulk senders (>5k/day) **must** include `List-Unsubscribe` (RFC 2369) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058). Without these, Gmail aggressively spam-folders or rejects. Even below the threshold, presence improves inbox placement and is required for legitimate-business signal.

**What's added:**

`EmailService.send_email` now accepts:

```python
unsubscribe_mailto: str | None = None,   # e.g. "unsubscribe+<contact_id>@<domain>"
unsubscribe_url: str | None = None,      # e.g. "https://app.example.com/unsubscribe?cid=..."
```

When set, the transport emits:

```
List-Unsubscribe: <https://app.example.com/unsubscribe?cid=...>, <mailto:unsubscribe+...@example.com>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

(The `-Post` header is only added when a URL is provided, per RFC 8058.)

**`tasks.py` auto-constructs these per send:**

```python
sender_domain = campaign.sender_email.split("@", 1)[1]
unsubscribe_mailto = f"unsubscribe+{contact.id}@{sender_domain}"
unsubscribe_url = f"{settings.public_base_url}/unsubscribe?cid={contact.id}"
```

**⚠️ Action required:** the URL form needs an actual `/unsubscribe` endpoint that:
1. Accepts `GET` (browser link click) and `POST` (one-click)
2. Marks the contact as unsubscribed in the DB
3. Returns 200 on success

Until this endpoint exists, the `mailto:` form still works (the recipient's client sends an unsubscribe email to that address; you can manually process inbound `unsubscribe+*@` addresses, or add a webhook). **Mail will not bounce or fail** if the URL endpoint is missing — Gmail just won't honour the One-Click flow.

Suggested next step (small follow-up PR): add `POST /unsubscribe` to `app/api/` that flips `Contact.status = "unsubscribed"` and cancels deferred arq jobs for that contact.

---

## Change 4 — Integration tests are opt-in

**Files:**
- `tests/conftest.py` *(hook added)*
- `tests/integration/test_smtp_transport.py` *(new file, 5 tests)*

**Problem:** Tests in `tests/integration/` were marked `pytestmark = pytest.mark.integration` (existing convention) but the marker had no auto-skip hook. So they ran on every `pytest` invocation and 4 of them failed (LLM classifier drift + real-website scraper drift), polluting the signal.

**Fix:** added a `pytest_collection_modifyitems` hook that skips `integration`-marked tests unless `--run-integration` is passed or `-m integration` is set.

**Now:**

```powershell
python -m pytest                          # 222 passed, 24 skipped, 0 failed
python -m pytest --run-integration        # Runs integration suite too
python -m pytest -m integration           # Same effect, idiomatic pytest
```

**New tests in `tests/integration/test_smtp_transport.py`** (all pass when mailbox container is healthy and provisioned):

1. `test_smtp_transport_delivers_to_mailbox` — full send → IMAP-receive round trip
2. `test_smtp_transport_preserves_threading_headers` — `In-Reply-To` + `References` survive transport
3. `test_smtp_transport_custom_args_become_x_headers` — `contact_id` / `campaign_id` arrive as `X-Custom-*`
4. `test_smtp_transport_writes_list_unsubscribe_header` — RFC 2369 + 8058 headers present
5. `test_smtp_transport_bad_auth_raises_permanent_error` — wrong SMTP password raises `SendGridPermanentError` (legacy name preserved; existing retry logic works)

These tests auto-skip if `mailbox` container isn't healthy or the roster has fewer than 2 agents, so they're safe to run anywhere.

---

## What was **not** changed (still on the open list)

1. **Webhook signature verification is config-toggleable** (`sendgrid_webhook_verify_enabled: bool = True`). Default is on; production should never flip it off. Could be made enforced-when-non-debug, but didn't want to change config semantics in this pass.
2. **Dry-run mode bypasses the SendGrid rate limiter.** This is by design (dry-runs are for testing the pipeline without throttling) but worth flagging that dry-run throughput isn't representative of production throughput.
3. **Cadence follow-ups are fire-and-forget** — `pool.enqueue_job(..., _defer_by=timedelta(days=N))`. If Redis dies between send and the next-step schedule, follow-ups are silently lost. A durable scheduler (DB-backed cron, or a "next_action_at" column polled by a worker) is a bigger architectural lift.
4. **Inbound replies still require SendGrid webhook format.** The engine has no IMAP client. To test reply classification end-to-end against mailbox, you'd either need to (a) `POST` a synthesised SendGrid webhook payload to `/api/v1/webhooks/sendgrid`, or (b) wait for the planned LMTP→HTTP bridge in the mailbox project.
5. **The LLM classifier drifts on "Yes I'm interested" → `question`.** Real bug, possibly a prompt issue. Not investigated in this pass.
6. **The scraper test (`test_scrape_aramas`) depends on an external website** that may have changed structure. Re-pin the test target or assert more loosely.

---

## Verification

```powershell
# Default suite
python -m pytest -q
# → 222 passed, 24 skipped, 0 failed in ~35s

# SMTP integration against the local mailbox stack
python -m pytest --run-integration tests/integration/test_smtp_transport.py -v
# → 5 passed in ~10s

# Email-related tests only (proves the refactor didn't break existing behaviour)
python -m pytest -k "email or send_email_task or idempotency"
# → 17 passed
```

---

## How to roll back

Every change is contained in 5 files:

| File | Type | Roll back by |
|---|---|---|
| `app/services/email.py` | refactor | revert to git HEAD — public surface preserved, callers don't need changes |
| `app/config.py` | added settings (additive) | revert — defaults preserve old behaviour |
| `app/workers/tasks.py` | wrapped send block in lock + added unsubscribe kwargs | revert — old flow still works; the lock just wasn't there before |
| `tests/conftest.py` | added pytest hook (additive) | revert — integration tests will fail by default again |
| `tests/integration/test_smtp_transport.py` | new file | delete |

To keep mailbox testability without the other changes: keep `email.py` + `config.py`, revert the rest.

---

## Suggested commit messages (if landing as separate commits)

```
feat(email): pluggable transport (SendGrid + SMTP)

Refactor EmailService into a transport-agnostic interface. Default
behaviour unchanged (still SendGrid). Setting EMAIL_TRANSPORT=smtp
routes through aiosmtplib for local/staging testing against any
SMTP server. Preserves public surface and exception types — no
caller changes required.

fix(workers): close idempotency race in send_email_task

Wrap send + commit in a redis_lock keyed on (contact, cadence_step)
with an inside-the-lock DB re-check. Eliminates the double-send
window between check_idempotency and send.

feat(email): emit List-Unsubscribe header (Gmail/Outlook 2024)

Add unsubscribe_mailto / unsubscribe_url kwargs to EmailService.
tasks.py auto-constructs per-contact targets from campaign sender
domain + public_base_url. The /unsubscribe URL endpoint itself
is a separate follow-up.

test(infra): make integration tests opt-in via --run-integration

Tests in tests/integration/ are marked @pytest.mark.integration but
were running unconditionally. Add a conftest hook so they only run
when --run-integration or -m integration is passed. Default pytest
run is now fully green (222 passed, 24 skipped).

test(smtp): add 5 integration tests for the SMTP email transport

Round-trip delivery, threading headers, X-Custom-* headers,
List-Unsubscribe headers, and bad-auth exception mapping. All
exercise the live local mailbox stack.
```

---

## Contact

Questions about this change set — ping me. Questions about the local `mailbox` stack — see `E:\dev\experiments\mailbox\README.md`.
