# adil-outreach-engine

AI-powered outreach and conversion platform for AskAdil. Manages multi-step email campaigns with LLM-driven research, personalised drafting, reply classification, and conversion tracking.

## Architecture

- **FastAPI** — async REST API (campaigns, contacts, dashboard, webhooks, public conversion pages)
- **arq** — background task queue for research, compose, send, classify, and follow-up workers
- **LangGraph** — agent pipeline orchestrating LLM calls (Gemini, Claude, GPT)
- **PostgreSQL** — persistent storage (campaigns, contacts, outreach events, conversions)
- **Redis** — task queue broker, rate limiting
- **SendGrid** — transactional email with webhook tracking

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- API keys for SendGrid, Stripe, Cal.com, and at least one LLM provider

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your API keys

# 2. Start all services
docker-compose up -d

# 3. Verify health
curl http://localhost:8001/api/v1/outreach/health

# 4. Seed first campaign (optional)
python scripts/seed_solicitor_campaign.py
```

## API Overview

| Group | Endpoints | Description |
|-------|-----------|-------------|
| Campaigns | `POST/GET/PATCH/DELETE /api/v1/outreach/campaigns` | Campaign CRUD, launch, pause |
| Contacts | `POST/GET/PATCH/DELETE /api/v1/outreach/campaigns/{id}/contacts` | Contact management, bulk import |
| Outreach | `POST /api/v1/outreach/contacts/{id}/research\|draft\|approve-draft\|send` | Trigger pipeline steps |
| Webhooks | `POST /api/v1/outreach/webhooks/sendgrid\|stripe\|cal` | Inbound event processing |
| Conversion | `GET /signup/{slug}`, `/book/{slug}`, `/pay/{slug}` | Public conversion pages |
| Dashboard | `GET /api/v1/outreach/campaigns/{id}/stats\|export` | Funnel metrics, CSV export |
| Health | `GET /api/v1/outreach/health` | Service health check |

## Development

### Running without Docker

```bash
# Create virtualenv and install
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Start Postgres and Redis locally, then:
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# In a separate terminal, start the worker:
arq app.workers.settings.WorkerSettings
```

### Running tests

```bash
pytest
# or with verbose output:
python -m pytest tests/ -v --tb=short
```

### Migrations

```bash
# Apply migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description of changes"

# Rollback one step
alembic downgrade -1
```

## First Campaign Quickstart

1. **Seed the campaign** with the solicitor directory data:
   ```bash
   python scripts/seed_solicitor_campaign.py --api-url http://localhost:8001 --api-key YOUR_KEY
   ```
   This creates a campaign ("Solicitor Directory Outreach - Wave 1") and imports ~50 solicitor contacts.

2. **Review contacts** — all start in `pending` status:
   ```bash
   curl -H "X-API-Key: KEY" http://localhost:8001/api/v1/outreach/campaigns/{id}/contacts
   ```

3. **Launch the campaign** to begin automated research and drafting:
   ```bash
   curl -X POST -H "X-API-Key: KEY" http://localhost:8001/api/v1/outreach/campaigns/{id}/launch
   ```

4. **Check stats**:
   ```bash
   curl -H "X-API-Key: KEY" http://localhost:8001/api/v1/outreach/campaigns/{id}/stats
   ```

5. **Export data** as CSV:
   ```bash
   curl -H "X-API-Key: KEY" -o export.csv http://localhost:8001/api/v1/outreach/campaigns/{id}/export
   ```

## Environment Variables

See [`.env.example`](.env.example) for all configuration options with documentation.

## Deployment (Railway)

1. Create a new project on [Railway](https://railway.app)
2. Add **PostgreSQL** and **Redis** plugins (Railway provides `DATABASE_URL` and `REDIS_URL` automatically)
3. Connect this GitHub repo
4. Set environment variables from `.env.example` (except `DATABASE_URL` and `REDIS_URL` which Railway provides)
5. Deploy — Railway auto-detects the Dockerfile and builds

**Worker service:** Create a second Railway service from the same repo with start command:
```
arq app.workers.settings.WorkerSettings
```

> **Note:** Do NOT set `RAILWAY_DOCKERFILE_PATH` as an env var — it breaks Railway's auto-detection for subdirectory deploys.
