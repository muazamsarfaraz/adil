# adil-outreach-engine

![Tests](https://img.shields.io/badge/tests-222%20passing-brightgreen)
![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)
![Python](https://img.shields.io/badge/python-3.11+-blue)

**AI-powered outreach and conversion platform for AskAdil by MCB (Muslim Council of Britain).**

Manages multi-step email campaigns with LLM-driven research, personalised drafting, reply classification, and conversion tracking.

---

## Architecture

| Component | Role |
|-----------|------|
| **FastAPI** | Async REST API (campaigns, contacts, dashboard, webhooks, public conversion pages) |
| **arq** | Background task queue for research, compose, send, classify, and follow-up workers |
| **LangGraph** | Agent pipeline orchestrating LLM calls (Gemini, Claude, GPT) |
| **PostgreSQL** | Persistent storage (campaigns, contacts, outreach events, conversions) |
| **Redis** | Task queue broker, rate limiting |
| **SendGrid** | Transactional email with webhook tracking |
| **Stripe** | Payment conversion tracking |
| **Cal.com** | Booking conversion tracking |

## Key Features

- **Dry-run mode** -- test full pipeline without sending real emails
- **Email preview** -- review and approve AI-drafted emails before sending
- **Configurable LLM per agent** -- use Gemini for research, Claude for drafting, etc.
- **Campaign-as-config** -- define campaign behaviour via configuration, not code
- **Webhook-driven tracking** -- SendGrid, Stripe, and Cal.com events update contact status automatically
- **Public conversion pages** -- branded signup, booking, and payment pages per campaign

---

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

For operational procedures, see [RUNBOOK.md](RUNBOOK.md).

## API Documentation

Interactive Swagger/OpenAPI docs are available at `/docs` when the service is running.

### Endpoint Overview

| Group | Endpoints | Description |
|-------|-----------|-------------|
| Campaigns | `POST/GET/PATCH/DELETE /api/v1/outreach/campaigns` | Campaign CRUD, launch, pause |
| Contacts | `POST/GET/PATCH/DELETE /api/v1/outreach/campaigns/{id}/contacts` | Contact management, bulk import |
| Outreach | `POST /api/v1/outreach/contacts/{id}/research\|draft\|approve-draft\|send` | Trigger pipeline steps |
| Webhooks | `POST /api/v1/outreach/webhooks/sendgrid\|stripe\|cal` | Inbound event processing |
| Conversion | `GET /signup/{slug}`, `/book/{slug}`, `/pay/{slug}` | Public conversion pages |
| Dashboard | `GET /api/v1/outreach/campaigns/{id}/stats\|export` | Funnel metrics, CSV export |
| Health | `GET /api/v1/outreach/health` | Service health check |

---

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

### Running Tests

```bash
pytest
# or with verbose output:
python -m pytest tests/ -v --tb=short
```

222 tests passing across unit, integration, and E2E suites.

### Migrations

```bash
alembic upgrade head                                  # Apply migrations
alembic revision --autogenerate -m "description"      # Create new migration
alembic downgrade -1                                  # Rollback one step
```

---

## Environment Variables

See [`.env.example`](.env.example) for all configuration options with documentation.

---

## Project Structure

```
adil-outreach-engine/
├── app/
│   ├── main.py                  # FastAPI application entry point
│   ├── config.py                # Pydantic settings
│   ├── database.py              # Async SQLAlchemy engine
│   ├── rate_limit.py            # slowapi rate limiter
│   ├── api/                     # Route handlers
│   │   ├── campaigns.py         # Campaign CRUD + launch/pause
│   │   ├── contacts.py          # Contact management + bulk import
│   │   ├── dashboard.py         # Stats + CSV export
│   │   ├── outreach.py          # Pipeline step triggers
│   │   ├── public.py            # Public conversion pages
│   │   ├── webhooks.py          # SendGrid/Stripe/Cal webhooks
│   │   └── conversion_webhooks.py
│   ├── agents/                  # LangGraph agent pipeline
│   │   ├── graph.py             # Pipeline graph definition
│   │   ├── llm.py               # LLM provider factory
│   │   ├── state.py             # Agent state schema
│   │   ├── checkpoints.py       # Checkpoint persistence
│   │   ├── nodes/               # Pipeline steps
│   │   │   ├── research.py      # Web research + SRA lookup
│   │   │   ├── compose.py       # Email drafting
│   │   │   ├── send.py          # Email dispatch via SendGrid
│   │   │   ├── classify.py      # Reply classification
│   │   │   └── evaluate.py      # Goal evaluation
│   │   └── tools/               # Agent tools
│   │       ├── scraper.py       # Web scraping
│   │       ├── sra.py           # SRA API lookup
│   │       └── web_search.py    # Web search
│   ├── auth/                    # API key + webhook verification
│   ├── models/                  # SQLAlchemy models
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── services/                # Business logic
│   │   ├── email.py             # SendGrid email service
│   │   ├── stripe.py            # Stripe integration
│   │   ├── cal.py               # Cal.com integration
│   │   ├── conversion.py        # Conversion tracking
│   │   ├── bounce.py            # Bounce handling
│   │   ├── events.py            # Event logging
│   │   └── goal_evaluator.py    # Campaign goal evaluation
│   └── workers/                 # arq background workers
│       ├── settings.py          # Worker configuration
│       ├── tasks.py             # Task definitions
│       ├── locks.py             # Distributed locking
│       └── rate_limiter.py      # Worker rate limiting
├── alembic/                     # Database migrations
├── tests/                       # 222 tests
├── scripts/                     # Seed scripts + utilities
├── docs/                        # Design docs + plans
├── docker-compose.yml           # Local dev stack
├── Dockerfile                   # API container
├── Dockerfile.worker            # Worker container
├── RUNBOOK.md                   # Operational runbook
├── pyproject.toml               # Package + tool config
└── railway.toml                 # Railway deploy config
```

---

## Deployment (Railway)

The service deploys as two Railway services from the same repo:

| Service | Start Command | Purpose |
|---------|--------------|---------|
| **API** | `uvicorn app.main:app` (auto-detected from Dockerfile) | REST API |
| **Worker** | `arq app.workers.settings.WorkerSettings` | Background task processing |

### Setup

1. Create a new project on [Railway](https://railway.app)
2. Add **PostgreSQL** and **Redis** plugins (Railway provides `DATABASE_URL` and `REDIS_URL` automatically)
3. Connect this GitHub repo
4. Set environment variables from `.env.example` (except `DATABASE_URL` and `REDIS_URL` which Railway provides)
5. Deploy -- Railway auto-detects the Dockerfile and builds

> **Note:** Do NOT set `RAILWAY_DOCKERFILE_PATH` as an env var -- it breaks Railway's auto-detection for subdirectory deploys.

---

## License

Copyright Muslim Council of Britain. All rights reserved.
