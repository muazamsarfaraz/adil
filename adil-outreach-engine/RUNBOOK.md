# Adil Outreach Engine — Production Run Guide

Step-by-step operational guide for running the solicitor outreach campaign.

## Setup

```bash
# Set these in your shell for the session
export BASE="https://adil-outreach-engine-production.up.railway.app"  # or http://localhost:8001
export API_KEY="your-api-key-here"
```

---

## Pre-Flight Checks

### 1. Verify API is healthy

```bash
curl -s "$BASE/api/v1/outreach/health" | python -m json.tool
```

Expected: `"status": "healthy"` and `"postgres": "ok"`.

### 2. Verify worker is running

```bash
railway service adil-outreach-worker && railway logs --num 20
```

Look for: `Worker started` or `Listening for tasks` messages. No crash loops.

### 3. Verify Redis connected

```bash
railway service adil-outreach-worker && railway logs --num 50 | grep -i redis
```

Look for: `Redis connected` or similar. No `ConnectionRefused` errors.

### 4. Verify Postgres has tables

```bash
curl -s "$BASE/api/v1/outreach/health" | python -m json.tool
```

The health check runs `SELECT 1` against Postgres. If `"postgres": "ok"`, tables are accessible.

You can also verify by listing campaigns (should return empty or existing data):

```bash
curl -s -H "X-API-Key: $API_KEY" "$BASE/api/v1/outreach/campaigns" | python -m json.tool
```

---

## Phase 1: Dry-Run Test (5 firms)

This sends no real emails. The engine runs research + compose but marks emails as "dry_run".

### 1.1 Create a dry-run campaign

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dry Run Test - 5 Firms",
    "slug": "dry-run-test-5",
    "goal": "signup",
    "dry_run": true,
    "auto_send": true,
    "sender_name": "AskAdil Team",
    "sender_email": "outreach@askadil.org",
    "reply_to": "outreach@askadil.org",
    "templates": {
      "initial": {
        "subject": "AskAdil — Free AI Legal Guidance for British Muslims | Directory Listing",
        "body": "Assalamu Alaikum {{contact_name}},\n\n{{personalised_intro}}\n\nI'\''m reaching out from AskAdil, a free AI-powered legal guidance platform designed specifically for the British Muslim community. We'\''re building a trusted solicitor directory to connect our users with qualified legal professionals.\n\nWe'\''d love to include {{firm_name}} in our directory. Listing is completely free and takes just 15 minutes to set up.\n\nBenefits include:\n- Direct referrals from users seeking legal help in your practice areas\n- Enhanced online visibility within the Muslim community\n- A profile showcasing your specialisms and languages spoken\n\nWould you be available for a brief call this week to discuss?\n\nJazakallah Khair,\nAskAdil Team"
      }
    },
    "cadence": [{"day": 0, "action": "send_initial"}],
    "llm_config": {
      "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
      "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
      "classify": {"provider": "gemini", "model": "gemini-2.5-flash"}
    },
    "research_instructions": "Visit the firm'\''s website and find: the best contact person for partnership enquiries, their key practice areas relevant to British Muslims, any recent news or awards, and their SRA registration status. Summarise personalisation hooks.",
    "compose_instructions": "Write a warm, professional outreach email to a solicitor firm. Use the research data to personalise the opening paragraph. Reference specific details about their firm. The tone should be respectful and community-oriented. Use '\''Assalamu Alaikum'\'' for Muslim-focused firms."
  }' | python -m json.tool
```

Save the campaign ID:

```bash
export CAMPAIGN_ID="<paste campaign id from response>"
```

### 1.2 Bulk-add 5 test firms

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/contacts/bulk" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contacts": [
      {
        "name": "I Will Solicitors",
        "email": "info@iwillsolicitors.com",
        "firm_name": "I Will Solicitors",
        "website": "https://iwillsolicitors.com",
        "metadata": {"location": "Birmingham", "source": "dry-run-test"}
      },
      {
        "name": "Aramas Solicitors",
        "email": "info@aramassolicitors.co.uk",
        "firm_name": "Aramas Solicitors",
        "website": "https://aramassolicitors.co.uk",
        "metadata": {"location": "London", "source": "dry-run-test"}
      },
      {
        "name": "Landau Law Solicitors",
        "email": "info@landaulaw.co.uk",
        "firm_name": "Landau Law Solicitors",
        "website": "https://www.landaulaw.co.uk",
        "metadata": {"location": "London", "source": "dry-run-test"}
      },
      {
        "name": "White Horse Solicitors",
        "email": "info@whitehorsesolicitors.co.uk",
        "firm_name": "White Horse Solicitors",
        "website": "https://whitehorsesolicitors.co.uk",
        "metadata": {"location": "Leeds", "source": "dry-run-test"}
      },
      {
        "name": "Kesar & Co Solicitors",
        "email": "info@kesarandco.com",
        "firm_name": "Kesar & Co Solicitors",
        "website": "https://www.kesarandco.com",
        "metadata": {"location": "London", "source": "dry-run-test"}
      }
    ]
  }' | python -m json.tool
```

### 1.3 Launch the campaign

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/launch" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 1.4 Poll until all contacts are processed

```bash
# Check stats — repeat every 30-60 seconds until all 5 are in "emailed" or "draft_ready"
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/stats" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 1.5 List all contacts and review drafts

```bash
# List contacts
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/contacts" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

For each contact, preview the generated email:

```bash
# Replace CONTACT_ID with each contact's ID
export CONTACT_ID="<contact-id>"

curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID/email-preview" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 1.6 Quality checklist

For each of the 5 emails, verify:

- [ ] Opening line references something SPECIFIC about the firm (not generic)
- [ ] If the firm has a niche specialism, it is mentioned
- [ ] No placeholder text like `[Your Name]` or `{{variable}}`
- [ ] Tone is warm and professional
- [ ] Under 200 words
- [ ] Correct firm name throughout
- [ ] Sign-off uses the sender name, not a placeholder

---

## Phase 2: Send to Yourself

This sends a REAL email via SendGrid to your own inbox to verify delivery and formatting.

### 2.1 Create a real campaign (auto_send=false)

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Self-Test - Real Email",
    "slug": "self-test-real",
    "goal": "signup",
    "dry_run": false,
    "auto_send": false,
    "sender_name": "AskAdil Team",
    "sender_email": "outreach@askadil.org",
    "reply_to": "outreach@askadil.org",
    "templates": {
      "initial": {
        "subject": "AskAdil — Free AI Legal Guidance for British Muslims | Directory Listing",
        "body": "Assalamu Alaikum {{contact_name}},\n\n{{personalised_intro}}\n\nI'\''m reaching out from AskAdil, a free AI-powered legal guidance platform designed specifically for the British Muslim community. We'\''re building a trusted solicitor directory to connect our users with qualified legal professionals.\n\nWe'\''d love to include {{firm_name}} in our directory. Listing is completely free and takes just 15 minutes to set up.\n\nBenefits include:\n- Direct referrals from users seeking legal help in your practice areas\n- Enhanced online visibility within the Muslim community\n- A profile showcasing your specialisms and languages spoken\n\nWould you be available for a brief call this week to discuss?\n\nJazakallah Khair,\nAskAdil Team"
      }
    },
    "cadence": [{"day": 0, "action": "send_initial"}],
    "llm_config": {
      "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
      "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
      "classify": {"provider": "gemini", "model": "gemini-2.5-flash"}
    },
    "research_instructions": "Visit the firm'\''s website and find: the best contact person, their key practice areas, any recent news or awards, and their SRA registration status.",
    "compose_instructions": "Write a warm, professional outreach email. Use the research data to personalise the opening paragraph. Reference specific details about the firm."
  }' | python -m json.tool
```

```bash
export CAMPAIGN_ID="<paste campaign id>"
```

### 2.2 Add yourself as a contact

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/contacts" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Your Name",
    "email": "your-email@example.com",
    "firm_name": "Test Firm LLP",
    "website": "https://example.com",
    "metadata": {"location": "London", "source": "self-test"}
  }' | python -m json.tool
```

```bash
export CONTACT_ID="<paste contact id>"
```

### 2.3 Launch and wait for draft

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/launch" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

Poll until the contact reaches `draft_ready` status:

```bash
curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 2.4 Preview the draft

```bash
curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID/email-preview" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 2.5 Approve the draft (this sends the real email)

```bash
curl -s -X POST "$BASE/api/v1/outreach/contacts/$CONTACT_ID/approve-draft" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 2.6 Check your inbox

Verify:

- [ ] Email arrived in inbox (not spam)
- [ ] From address shows correctly (outreach@askadil.org)
- [ ] Reply-to is correct (outreach@askadil.org)
- [ ] Subject line is clean, no encoding issues
- [ ] Body formatting is correct (line breaks, no HTML artifacts)
- [ ] Links work (if any)
- [ ] Sender name displays correctly

---

## Phase 3: Send to 3 Friendly Contacts

Same as Phase 2, but with 3 real people you know who have agreed to receive a test email.

### 3.1 Create campaign

Same as Phase 2 step 2.1 but with slug `"friendly-test-3"`.

### 3.2 Add 3 contacts

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/contacts/bulk" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contacts": [
      {
        "name": "Friend 1 Name",
        "email": "friend1@example.com",
        "firm_name": "Friend 1 Firm",
        "website": "https://friend1firm.com",
        "metadata": {"location": "London", "source": "friendly-test"}
      },
      {
        "name": "Friend 2 Name",
        "email": "friend2@example.com",
        "firm_name": "Friend 2 Firm",
        "website": "https://friend2firm.com",
        "metadata": {"location": "Birmingham", "source": "friendly-test"}
      },
      {
        "name": "Friend 3 Name",
        "email": "friend3@example.com",
        "firm_name": "Friend 3 Firm",
        "website": "https://friend3firm.com",
        "metadata": {"location": "Manchester", "source": "friendly-test"}
      }
    ]
  }' | python -m json.tool
```

### 3.3 Launch, review drafts, approve one at a time

```bash
# Launch
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/launch" \
  -H "X-API-Key: $API_KEY" | python -m json.tool

# Poll stats until all 3 are draft_ready
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/stats" \
  -H "X-API-Key: $API_KEY" | python -m json.tool

# Preview each draft (repeat for each CONTACT_ID)
curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID/email-preview" \
  -H "X-API-Key: $API_KEY" | python -m json.tool

# Approve each draft one at a time
curl -s -X POST "$BASE/api/v1/outreach/contacts/$CONTACT_ID/approve-draft" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 3.4 Verify inbound parse

- Ask your friends to reply to the email
- Check that the reply is received via SendGrid Inbound Parse webhook
- Verify the classify agent correctly categorises the reply

```bash
# Check contact detail for reply classification
curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

---

## Phase 4: Full 50-Firm Campaign

### 4.1 Create the production campaign

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Solicitor Directory Outreach - Wave 1",
    "slug": "solicitor-wave1",
    "goal": "signup",
    "dry_run": false,
    "auto_send": false,
    "sender_name": "AskAdil Team",
    "sender_email": "outreach@askadil.org",
    "reply_to": "outreach@askadil.org",
    "templates": {
      "initial": {
        "subject": "AskAdil — Free AI Legal Guidance for British Muslims | Directory Listing",
        "body": "Assalamu Alaikum {{contact_name}},\n\n{{personalised_intro}}\n\nI'\''m reaching out from AskAdil, a free AI-powered legal guidance platform designed specifically for the British Muslim community. We'\''re building a trusted solicitor directory to connect our users with qualified legal professionals.\n\nWe'\''d love to include {{firm_name}} in our directory. Listing is completely free and takes just 15 minutes to set up.\n\nBenefits include:\n- Direct referrals from users seeking legal help in your practice areas\n- Enhanced online visibility within the Muslim community\n- A profile showcasing your specialisms and languages spoken\n\nWould you be available for a brief call this week to discuss?\n\nJazakallah Khair,\nAskAdil Team"
      },
      "follow_up_1": {
        "subject": "Re: AskAdil Solicitor Directory — Quick Follow-Up",
        "body": "Assalamu Alaikum {{contact_name}},\n\nI wanted to follow up on my previous email about listing {{firm_name}} in the AskAdil solicitor directory.\n\n{{personalised_intro}}\n\nAs a reminder, listing is completely free and takes just 15 minutes to set up.\n\nWould you be available for a brief call this week?\n\nJazakallah Khair,\nAskAdil Team"
      },
      "follow_up_2": {
        "subject": "Re: AskAdil Directory — Final Note",
        "body": "Hi {{contact_name}},\n\nJust a final note — we'\''d love to include {{firm_name}} in the AskAdil solicitor directory. If you'\''re interested, you can sign up directly here:\n\n{{signup_link}}\n\nNo obligation, and listing is free.\n\nBest regards,\nAskAdil Team"
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
    "research_instructions": "Visit the firm'\''s website and find: the best contact person for partnership enquiries (ideally a senior partner or business development lead), their key practice areas relevant to British Muslims, any recent news or awards, and their SRA registration status. Summarise personalisation hooks.",
    "compose_instructions": "Write a warm, professional outreach email to a solicitor firm. Use the research data to personalise the opening paragraph. Reference specific details about their firm (awards, specialisms, team members). The tone should be respectful and community-oriented. Use '\''Assalamu Alaikum'\'' for Muslim-focused firms."
  }' | python -m json.tool
```

```bash
export CAMPAIGN_ID="<paste campaign id>"
```

### 4.2 Import all firms from the solicitor directory

```bash
python scripts/seed_solicitor_campaign.py \
  --api-url "$BASE" \
  --api-key "$API_KEY" \
  --wave 1
```

Or for a dry-run preview first:

```bash
python scripts/seed_solicitor_campaign.py --dry-run
```

> **Note:** If the seed script creates its own campaign, you can skip step 4.1 and use the campaign ID it outputs instead.

### 4.3 Launch the campaign

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/launch" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 4.4 Review EVERY draft

List all contacts and check their status:

```bash
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/contacts?limit=100" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

For each contact in `draft_ready` status, preview the email:

```bash
curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID/email-preview" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 4.5 Approve one at a time

Only approve after reading the preview:

```bash
curl -s -X POST "$BASE/api/v1/outreach/contacts/$CONTACT_ID/approve-draft" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### 4.6 Monitor campaign stats

```bash
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/stats" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

---

## Monitoring & Troubleshooting

### Check worker logs

```bash
railway service adil-outreach-worker && railway logs
```

### Check API logs

```bash
railway service adil-outreach-engine && railway logs
```

### Check campaign stats

```bash
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/stats" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### Retry a failed contact

```bash
curl -s -X POST "$BASE/api/v1/outreach/contacts/$CONTACT_ID/retry" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### Pause a campaign

```bash
curl -s -X POST "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/pause" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### View a specific contact's full detail

```bash
curl -s "$BASE/api/v1/outreach/contacts/$CONTACT_ID" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### Export campaign data

```bash
curl -s "$BASE/api/v1/outreach/campaigns/$CAMPAIGN_ID/stats" \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

### Common errors and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Wrong or missing API key | Check `$API_KEY` is set correctly |
| `404 Campaign not found` | Wrong campaign ID | Run `curl -s -H "X-API-Key: $API_KEY" "$BASE/api/v1/outreach/campaigns"` to list all |
| `"postgres": "error"` in health check | Database connection failed | Check `DATABASE_URL` env var in Railway; verify Postgres service is running |
| Worker not processing contacts | Worker crashed or Redis disconnected | Check worker logs: `railway service adil-outreach-worker && railway logs` |
| Email not arriving | SendGrid API key invalid or domain not verified | Check `SENDGRID_API_KEY` env var; verify sender domain in SendGrid dashboard |
| `Tool 'scrape_website' encountered an error` | Website blocked scraping or timed out | Normal — the agent will continue with other tools. Check worker logs for details |
| Draft quality is poor / generic | Research didn't find enough data | Check the research data via contact detail endpoint; consider adding more research_instructions |
| `LLM unavailable` | API key for LLM provider is missing or invalid | Check `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` env vars |
| Contact stuck in `researching` status | Worker task timed out | Retry the contact: `POST /contacts/{id}/retry` |

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY` | Yes | API key for authenticating requests to the outreach engine |
| `DATABASE_URL` | Yes | PostgreSQL connection string (format: `postgresql+asyncpg://user:pass@host:port/db`) |
| `REDIS_URL` | Yes | Redis connection string for the task queue (format: `redis://host:port/db`) |
| `SENDGRID_API_KEY` | Yes | SendGrid API key for sending emails (starts with `SG.`) |
| `GEMINI_API_KEY` | Yes* | Google Gemini API key (used for research and classify agents) |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key (used for compose agent) |
| `OPENAI_API_KEY` | No | OpenAI API key (only if using OpenAI models in llm_config) |
| `STRIPE_SECRET_KEY` | No | Stripe secret key for payment processing |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook signing secret |
| `CAL_API_KEY` | No | Cal.com API key for booking integration |
| `CAL_WEBHOOK_SECRET` | No | Cal.com webhook signing secret |
| `PORT` | No | API server port (default: 8001) |
| `DEBUG` | No | Enable debug mode (default: false) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `PUBLIC_BASE_URL` | No | Public-facing URL for the API (used in generated links) |

*Required for the default LLM configuration. Only the providers referenced in your campaign's `llm_config` need their API keys set.

> **Important:** Never set `RAILWAY_DOCKERFILE_PATH` as an environment variable — it breaks Railway's auto-detection for subdirectory deploys.
