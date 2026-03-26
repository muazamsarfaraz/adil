# Plan 6: Dashboard, Deployment & First Campaign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reporting dashboard, package for deployment, and seed the first campaign with the solicitor directory data.

**Architecture:** Stats endpoints aggregate outreach_events into funnel metrics. CSV export for data portability. Docker multi-stage build for production. First campaign loaded from the existing solicitor-directory-comprehensive.json.

**Tech Stack:** FastAPI, SQLAlchemy (aggregation queries), csv module, Docker, Railway

**Depends on:** Plans 1-5 (project scaffold, data model, campaign/contact CRUD, agent pipeline, webhooks & conversions)

**Spec References:** Sections 4.6, 9, 10, 11, 13

---

## Task 1: Campaign Stats Endpoint

**File:** `app/api/dashboard.py`

Build the `GET /api/v1/outreach/campaigns/{id}/stats` endpoint that aggregates contact statuses and outreach_events into funnel metrics.

- [ ] Create `app/api/dashboard.py` with a FastAPI `APIRouter(prefix="/api/v1/outreach", tags=["dashboard"])`
- [ ] Implement `get_campaign_stats(campaign_id: UUID)` endpoint at `/campaigns/{id}/stats`
- [ ] Query `contacts` table grouped by `status` for the given `campaign_id` to produce counts:
  - `total_contacts` — total count
  - `pending` — status = `pending`
  - `researching` — status = `researching`
  - `emailed` — status = `emailed`
  - `opened` — contacts with at least one `email_opened` event (join to `outreach_events`)
  - `replied` — status = `replied`
  - `converted` — status = `converted`
  - `declined` — status = `declined`
  - `unresponsive` — status = `unresponsive`
  - `bounced` — status = `bounced`
- [ ] Calculate derived rates (guard against division by zero):
  - `open_rate` = opened / emailed (where emailed = contacts who were sent at least one email)
  - `reply_rate` = replied / emailed
  - `conversion_rate` = converted / total_contacts
- [ ] Use SQLAlchemy `func.count`, `case()`, and subqueries for efficient single-pass aggregation
- [ ] Verify campaign exists — return 404 if not found
- [ ] Require API key auth dependency (`get_api_key`)
- [ ] Return `CampaignStats` schema (Task 3)
- [ ] Register router in `app/main.py`

**SQL approach (pseudocode):**
```python
# Counts by status
status_counts = await db.execute(
    select(
        Contact.status,
        func.count(Contact.id)
    )
    .where(Contact.campaign_id == campaign_id)
    .group_by(Contact.status)
)

# Opened count (contacts with email_opened event)
opened_count = await db.execute(
    select(func.count(func.distinct(OutreachEvent.contact_id)))
    .join(Contact, OutreachEvent.contact_id == Contact.id)
    .where(
        Contact.campaign_id == campaign_id,
        OutreachEvent.event_type == "email_opened"
    )
)
```

**Acceptance criteria:**
- `GET /campaigns/{id}/stats` returns all funnel counts and rates
- Rates are floats between 0.0 and 1.0 (rounded to 4 decimal places)
- Returns 404 for non-existent campaign
- Response time < 200ms (per spec Section 13)

---

## Task 2: Campaign Export Endpoint

**File:** `app/api/dashboard.py` (add to existing router)

Build `GET /api/v1/outreach/campaigns/{id}/export` that returns a CSV download of all contacts and their latest event status.

- [ ] Implement `export_campaign(campaign_id: UUID)` endpoint at `/campaigns/{id}/export`
- [ ] Query all contacts for the campaign with their most recent outreach_event (use a lateral subquery or window function)
- [ ] Build CSV columns:
  - `contact_id`, `name`, `email`, `firm_name`, `phone`, `website`, `status`
  - `metadata` (JSON-serialised)
  - `research_data` (JSON-serialised)
  - `last_event_type`, `last_event_date`
  - `total_events` (count of outreach_events per contact)
  - `created_at`, `updated_at`
- [ ] Use Python `csv` module with `io.StringIO` to generate the CSV in memory
- [ ] Return as `StreamingResponse` with headers:
  - `Content-Type: text/csv`
  - `Content-Disposition: attachment; filename="campaign-{slug}-export-{date}.csv"`
- [ ] Require API key auth
- [ ] Verify campaign exists — return 404 if not found
- [ ] Handle large exports efficiently: use `stream_results()` if supported, or paginate the DB query internally

**Acceptance criteria:**
- Downloading the CSV opens correctly in Excel/Google Sheets
- All contacts included with accurate status and event data
- JSON fields are properly escaped in CSV cells
- Filename includes campaign slug and export date

---

## Task 3: Stats Pydantic Schema

**File:** `app/schemas/stats.py`

- [ ] Create `CampaignStats` Pydantic model:
  ```python
  class CampaignStats(BaseModel):
      campaign_id: UUID
      campaign_name: str
      campaign_status: str
      total_contacts: int
      pending: int
      researching: int
      ready: int
      draft_pending: int
      emailed: int
      opened: int
      replied: int
      converted: int
      declined: int
      unresponsive: int
      bounced: int
      open_rate: float
      reply_rate: float
      conversion_rate: float
      last_activity: datetime | None  # most recent outreach_event timestamp
  ```
- [ ] Add `model_config = ConfigDict(from_attributes=True)` for ORM compatibility
- [ ] Add docstrings explaining each field
- [ ] Add validators:
  - Rates must be >= 0.0 and <= 1.0
  - Counts must be >= 0

**Acceptance criteria:**
- Schema validates correctly with sample data
- Serialises to JSON matching the spec Section 4.6 response format

---

## Task 4: Dockerfile (Multi-Stage Build)

**File:** `Dockerfile` (project root)

Build a multi-stage Dockerfile that can run both the FastAPI server and arq worker.

- [ ] **Stage 1 — Builder:**
  ```dockerfile
  FROM python:3.11-slim AS builder
  WORKDIR /build
  COPY pyproject.toml .
  RUN pip install --no-cache-dir --prefix=/install .
  ```
- [ ] **Stage 2 — Runtime:**
  ```dockerfile
  FROM python:3.11-slim AS runtime
  WORKDIR /app
  COPY --from=builder /install /usr/local
  COPY . .
  ```
- [ ] Set environment variables:
  - `PYTHONUNBUFFERED=1`
  - `PYTHONDONTWRITEBYTECODE=1`
- [ ] Create a non-root user for security:
  ```dockerfile
  RUN adduser --disabled-password --no-create-home appuser
  USER appuser
  ```
- [ ] Default `CMD` runs the FastAPI server:
  ```dockerfile
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
  ```
- [ ] Document how to run the arq worker instead (override CMD):
  ```bash
  docker run <image> arq app.workers.settings.WorkerSettings
  ```
- [ ] Add `.dockerignore` to exclude: `.git`, `__pycache__`, `.env`, `*.pyc`, `tests/`, `docs/`, `.venv`
- [ ] Ensure Alembic migrations directory is included in the image

**Acceptance criteria:**
- `docker build .` succeeds without errors
- Image size is under 300MB
- FastAPI starts and responds to health check
- Worker can be started with CMD override

---

## Task 5: docker-compose.yml (Local Dev)

**File:** `docker-compose.yml` (project root)

- [ ] Define three services:
  ```yaml
  services:
    api:
      build: .
      ports:
        - "8001:8001"
      env_file: .env
      depends_on:
        postgres:
          condition: service_healthy
        redis:
          condition: service_healthy
      command: >
        sh -c "alembic upgrade head &&
               uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"
      volumes:
        - .:/app

    worker:
      build: .
      env_file: .env
      depends_on:
        postgres:
          condition: service_healthy
        redis:
          condition: service_healthy
      command: arq app.workers.settings.WorkerSettings

    postgres:
      image: postgres:16-alpine
      environment:
        POSTGRES_DB: outreach
        POSTGRES_USER: outreach
        POSTGRES_PASSWORD: outreach_dev
      ports:
        - "5433:5432"
      volumes:
        - pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U outreach"]
        interval: 5s
        timeout: 5s
        retries: 5

    redis:
      image: redis:7-alpine
      ports:
        - "6380:6379"
      healthcheck:
        test: ["CMD", "redis-cli", "ping"]
        interval: 5s
        timeout: 5s
        retries: 5

  volumes:
    pgdata:
  ```
- [ ] Use non-standard host ports (5433, 6380) to avoid conflicts with local Postgres/Redis
- [ ] API service mounts source code for hot reload during development
- [ ] Worker service does NOT mount volumes (restart required for changes, matching production behaviour — or optionally mount for dev convenience)
- [ ] Add healthchecks for Postgres and Redis with `service_healthy` conditions
- [ ] API service runs Alembic migrations before starting uvicorn

**Acceptance criteria:**
- `docker-compose up` starts all services without errors
- API is reachable at `http://localhost:8001`
- `GET /api/v1/outreach/health` returns healthy status for all dependencies
- Worker connects to Redis and begins polling

---

## Task 6: .env.example

**File:** `.env.example` (project root)

Create a documented environment variable template covering all vars from spec Section 10.

- [ ] Include all required variables with placeholder values and comments:
  ```bash
  # ============================================
  # adil-outreach-engine — Environment Variables
  # ============================================
  # Copy to .env and fill in real values

  # --- Service ---
  OUTREACH_API_KEY=change-me-to-a-secure-random-string
  OUTREACH_PORT=8001

  # --- Database ---
  # For docker-compose local dev:
  DATABASE_URL=postgresql+asyncpg://outreach:outreach_dev@postgres:5432/outreach
  # For direct local dev (non-Docker):
  # DATABASE_URL=postgresql+asyncpg://outreach:outreach_dev@localhost:5433/outreach

  # --- Redis ---
  # For docker-compose local dev:
  REDIS_URL=redis://redis:6379/0
  # For direct local dev (non-Docker):
  # REDIS_URL=redis://localhost:6380/0

  # --- SendGrid ---
  SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxx
  SENDGRID_WEBHOOK_VERIFICATION_KEY=your-verification-key

  # --- Stripe ---
  STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxx
  STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxx

  # --- Cal.com ---
  CAL_API_KEY=cal_xxxxxxxxxxxxxxxxxxxx
  CAL_WEBHOOK_SECRET=your-cal-webhook-secret

  # --- LLM Providers ---
  # Only needed for providers configured in campaign llm_config
  GEMINI_API_KEY=your-gemini-api-key
  ANTHROPIC_API_KEY=your-anthropic-api-key
  OPENAI_API_KEY=your-openai-api-key

  # --- Encryption ---
  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ENCRYPTION_KEY=your-fernet-key

  # --- Optional ---
  # LOG_LEVEL=INFO
  # SENDGRID_DAILY_LIMIT=100
  ```
- [ ] Add a comment at the top noting which vars are required vs optional
- [ ] Ensure `.env` is in `.gitignore`

**Acceptance criteria:**
- All variables from spec Section 10 are present
- Docker-compose and non-Docker connection strings both documented
- Copying to `.env` and filling values is sufficient to run locally

---

## Task 7: README.md

**File:** `README.md` (project root)

- [ ] Project title and one-line description
- [ ] Architecture overview (FastAPI + arq + LangGraph + PostgreSQL + Redis)
- [ ] Prerequisites: Python 3.11+, Docker, Docker Compose
- [ ] Quick start:
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
- [ ] API overview table (all endpoint groups with brief descriptions):
  - Campaign management (`/campaigns`)
  - Contact management (`/campaigns/{id}/contacts`)
  - Outreach control (`/contacts/{id}/research`, `/draft`, `/approve-draft`, `/send`)
  - Webhooks (`/webhooks/sendgrid`, `/webhooks/stripe`, `/webhooks/cal`)
  - Public conversion (`/signup/{slug}`, `/book/{slug}`, `/pay/{slug}`)
  - Dashboard (`/campaigns/{id}/stats`, `/campaigns/{id}/export`, `/health`)
- [ ] Development section:
  - Running without Docker (local Python + Postgres + Redis)
  - Running tests: `pytest`
  - Running migrations: `alembic upgrade head`
  - Adding new migrations: `alembic revision --autogenerate -m "description"`
- [ ] First campaign quickstart:
  - What the seed script does
  - How to review drafts and approve sends
  - How to check stats
- [ ] Environment variables reference (link to `.env.example`)
- [ ] Deployment section (Railway)

**Acceptance criteria:**
- A new developer can go from clone to running service by following the README
- All major API groups documented
- First campaign flow is clearly explained

---

## Task 8: First Campaign Seed Script

**File:** `scripts/seed_solicitor_campaign.py`

Create a script that reads the solicitor directory JSON and seeds the first campaign via the API.

- [ ] Accept CLI arguments:
  - `--api-url` (default: `http://localhost:8001`)
  - `--api-key` (default: reads from `OUTREACH_API_KEY` env var)
  - `--json-path` (default: `../adil-rag-api/docs/plans/solicitor-directory-comprehensive.json`)
  - `--dry-run` (print what would be created without calling API)
  - `--wave` (optional: 1-4, to only seed a specific wave)
- [ ] Read `solicitor-directory-comprehensive.json` and parse the firms array
- [ ] Create the campaign via `POST /api/v1/outreach/campaigns` with:
  ```python
  campaign_data = {
      "name": "Solicitor Directory Outreach - Wave 1",
      "slug": "solicitor-wave1",
      "goal": "signup",
      "templates": {
          "initial": {
              "subject": "AskAdil — Free AI Legal Guidance for British Muslims | Directory Listing",
              "body": TEMPLATE_A  # From outreach-plan.md Template A
          },
          "follow_up_1": {
              "subject": "Re: AskAdil Solicitor Directory — Quick Follow-Up",
              "body": "Assalamu Alaikum {{contact_name}},\n\nI wanted to follow up on my previous email about listing {{firm_name}} in the AskAdil solicitor directory.\n\n{{personalised_intro}}\n\nAs a reminder, listing is completely free and takes just 15 minutes to set up.\n\nWould you be available for a brief call this week?\n\nJazakallah Khair,\nAskAdil Team"
          },
          "follow_up_2": {
              "subject": "Re: AskAdil Directory — Final Note",
              "body": "Hi {{contact_name}},\n\nJust a final note — we'd love to include {{firm_name}} in the AskAdil solicitor directory. If you're interested, you can sign up directly here:\n\n{{signup_link}}\n\nNo obligation, and listing is free.\n\nBest regards,\nAskAdil Team"
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
      "research_instructions": "Visit the firm's website and find: the best contact person for partnership enquiries (ideally a senior partner or business development lead), their key practice areas relevant to British Muslims, any recent news or awards, and their SRA registration status. Summarise personalisation hooks.",
      "compose_instructions": "Write a warm, professional outreach email to a solicitor firm. Use the research data to personalise the opening paragraph. Reference specific details about their firm (awards, specialisms, team members). The tone should be respectful and community-oriented. Use 'Assalamu Alaikum' for Muslim-focused firms.",
      "classify_instructions": "Classify the reply as one of: interested (wants to be listed/learn more), declined (not interested), question (asking for more info), out_of_office (auto-reply), bounce (delivery failure). Extract any specific concerns or questions mentioned.",
      "conversion_config": {
          "type": "signup",
          "signup_fields": [
              {"name": "firm_name", "type": "text", "required": True},
              {"name": "specialisms", "type": "multi_select", "required": True, "options": [
                  "islamic_family_law", "islamic_wills", "islamic_finance",
                  "discrimination", "immigration", "employment", "criminal",
                  "personal_injury", "conveyancing", "commercial"
              ]},
              {"name": "free_consultation", "type": "boolean", "required": True},
              {"name": "legal_aid", "type": "boolean", "required": True},
              {"name": "languages", "type": "multi_select", "required": False, "options": [
                  "English", "Arabic", "Urdu", "Hindi", "Bengali", "Punjabi",
                  "Somali", "Turkish", "Farsi", "French"
              ]},
              {"name": "preferred_referral_method", "type": "select", "required": True, "options": [
                  "email", "phone", "form", "any"
              ]}
          ],
          "confirmation_email": True,
          "webhook_on_conversion": "https://api.askadil.org/api/v1/solicitors"
      },
      "auto_send": False,
      "sender_name": "AskAdil Team",
      "sender_email": "outreach@askadil.org",
      "reply_to": "outreach@askadil.org"
  }
  ```
- [ ] Map each firm from the JSON to a contact object:
  ```python
  def firm_to_contact(firm: dict) -> dict:
      return {
          "name": firm.get("contact_person") or firm["firm_name"],
          "email": firm.get("email", ""),
          "firm_name": firm["firm_name"],
          "phone": firm.get("phone"),
          "website": firm.get("website"),
          "metadata": {
              "specialisms": firm.get("specialisms", []),
              "location": firm.get("location", ""),
              "source": "solicitor-directory-comprehensive.json",
              "sra_number": firm.get("sra_number"),
              "priority": firm.get("priority", "standard"),
              "wave": firm.get("wave", 1),
              "languages": firm.get("languages", []),
              "notes": firm.get("notes", "")
          }
      }
  ```
- [ ] Filter out firms without email addresses (log a warning for each)
- [ ] Bulk import contacts via `POST /api/v1/outreach/campaigns/{id}/contacts/bulk`
- [ ] Print summary: campaign created, contacts imported, contacts skipped (no email)
- [ ] Use `httpx` for API calls with proper error handling
- [ ] Add `if __name__ == "__main__":` with `argparse`

**Acceptance criteria:**
- Script runs successfully against a local instance
- Campaign is created with all templates and config
- All 50 firms from the JSON are imported (minus any without emails)
- Dry run mode prints the plan without making API calls
- Script is idempotent-safe (checks if campaign slug already exists)

---

## Task 9: Alembic Configuration for Production

**Files:** `alembic.ini`, `migrations/env.py`

- [ ] Configure `alembic.ini`:
  - Set `script_location = migrations`
  - Set `sqlalchemy.url` to empty (will be overridden by env.py)
  - Set `file_template` to `%%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(slug)s`
- [ ] Configure `migrations/env.py`:
  - Import `DATABASE_URL` from `app.config`
  - Set `target_metadata` from `app.models` Base metadata
  - Configure async migration support using `run_async_migrations` pattern:
    ```python
    from sqlalchemy.ext.asyncio import async_engine_from_config

    async def run_async_migrations():
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()
    ```
  - Import all models so autogenerate detects them
- [ ] Create `migrations/versions/` directory (empty, with `.gitkeep`)
- [ ] Generate initial migration: `alembic revision --autogenerate -m "initial schema"`
- [ ] Verify migration applies cleanly: `alembic upgrade head`
- [ ] Verify downgrade works: `alembic downgrade -1`
- [ ] Add migration commands to docker-compose API startup (already in Task 5)

**Acceptance criteria:**
- `alembic upgrade head` creates all tables matching the data model in spec Section 3
- `alembic downgrade base` removes all tables
- `alembic revision --autogenerate` correctly detects model changes
- Works with async PostgreSQL connection

---

## Task 10: Railway Deployment Config

**Files:** `railway.toml` (project root)

- [ ] Create `railway.toml` with build and deploy configuration:
  ```toml
  [build]
  builder = "DOCKERFILE"
  dockerfilePath = "Dockerfile"

  [deploy]
  startCommand = "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
  healthcheckPath = "/api/v1/outreach/health"
  healthcheckTimeout = 30
  restartPolicyType = "ON_FAILURE"
  restartPolicyMaxRetries = 3
  ```
- [ ] **Important:** Do NOT set `RAILWAY_DOCKERFILE_PATH` env var (breaks auto-detection per project memory)
- [ ] Document that Railway requires these services:
  - **PostgreSQL plugin** — provides `DATABASE_URL` (will need `+asyncpg` suffix appended in config.py)
  - **Redis plugin** — provides `REDIS_URL`
- [ ] Handle Railway's `PORT` env var in config.py:
  ```python
  # Railway provides PORT; fall back to OUTREACH_PORT for local dev
  port: int = Field(default=8001, alias="PORT")
  ```
- [ ] Document Railway deployment steps in README:
  1. Create new project on Railway
  2. Add PostgreSQL and Redis plugins
  3. Connect GitHub repo
  4. Set environment variables (all from `.env.example` except DATABASE_URL and REDIS_URL which Railway provides)
  5. Deploy
- [ ] Worker deployment: Create a second Railway service from the same repo with start command override:
  ```
  arq app.workers.settings.WorkerSettings
  ```
- [ ] Ensure `config.py` handles Railway's `DATABASE_URL` format (Postgres URL without `+asyncpg`):
  ```python
  @validator("DATABASE_URL", pre=True)
  def fix_database_url(cls, v):
      if v and v.startswith("postgresql://"):
          v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
      return v
  ```

**Acceptance criteria:**
- Railway auto-detects Dockerfile and builds successfully
- Health check endpoint responds within 30 seconds of deploy
- Migrations run automatically on deploy
- Worker service connects to the same Postgres and Redis

---

## Task 11: End-to-End Integration Test

**File:** `tests/test_e2e_campaign.py`

Write a full integration test that exercises the complete campaign lifecycle.

- [ ] Use `pytest-asyncio` and `httpx.AsyncClient` with the FastAPI test app
- [ ] Set up test fixtures:
  - In-memory or test PostgreSQL database
  - `fakeredis` for Redis
  - Apply Alembic migrations to test DB
- [ ] **Test flow:**
  ```python
  async def test_campaign_lifecycle(client: AsyncClient):
      # 1. Create campaign
      response = await client.post("/api/v1/outreach/campaigns", json={
          "name": "Test Campaign",
          "slug": "test-campaign",
          "goal": "signup",
          "templates": {
              "initial": {"subject": "Test", "body": "Hello {{contact_name}}"}
          },
          "cadence": [{"day": 0, "action": "send_initial"}],
          "llm_config": {"research": {"provider": "gemini", "model": "gemini-2.5-flash"}},
          "auto_send": False,
          "sender_name": "Test",
          "sender_email": "test@example.com",
          "reply_to": "test@example.com"
      })
      assert response.status_code == 201
      campaign_id = response.json()["id"]

      # 2. Add contacts
      response = await client.post(
          f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
          json=[
              {"name": "Alice", "email": "alice@example.com", "firm_name": "Alice Law"},
              {"name": "Bob", "email": "bob@example.com", "firm_name": "Bob Legal"},
          ]
      )
      assert response.status_code == 201
      assert response.json()["imported"] == 2

      # 3. Check stats before launch
      response = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/stats")
      assert response.status_code == 200
      stats = response.json()
      assert stats["total_contacts"] == 2
      assert stats["pending"] == 2
      assert stats["emailed"] == 0

      # 4. Launch campaign
      response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch")
      assert response.status_code == 200
      assert response.json()["enqueued"] == 2

      # 5. Verify campaign is active
      response = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}")
      assert response.json()["status"] == "active"

      # 6. Export CSV
      response = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/export")
      assert response.status_code == 200
      assert response.headers["content-type"] == "text/csv; charset=utf-8"
      assert "alice@example.com" in response.text
      assert "bob@example.com" in response.text
  ```
- [ ] Add separate test for stats accuracy after simulating events:
  - Manually insert `outreach_events` records (email_sent, email_opened, reply_received)
  - Update contact statuses accordingly
  - Verify stats endpoint returns correct counts and rates
- [ ] Add test for CSV export column correctness (check header row, data types)
- [ ] Add test for 404 on non-existent campaign stats/export

**Acceptance criteria:**
- Full lifecycle test passes
- Stats are accurate after simulated events
- CSV export contains all expected data
- Tests run in < 30 seconds

---

## Task 12: Final Smoke Test

**Manual verification procedure — no code file, but document the steps.**

- [ ] Run `docker-compose up -d` from project root
- [ ] Wait for all services to be healthy: `docker-compose ps` (all show "healthy")
- [ ] Verify health endpoint:
  ```bash
  curl http://localhost:8001/api/v1/outreach/health
  # Expected: {"status": "healthy", "redis": "connected", "postgres": "connected"}
  ```
- [ ] Run the seed script:
  ```bash
  python scripts/seed_solicitor_campaign.py --api-url http://localhost:8001 --api-key <your-key>
  ```
- [ ] Verify campaign was created:
  ```bash
  curl -H "X-API-Key: <key>" http://localhost:8001/api/v1/outreach/campaigns
  # Expected: list with "Solicitor Directory Outreach - Wave 1"
  ```
- [ ] Verify contacts were imported:
  ```bash
  curl -H "X-API-Key: <key>" "http://localhost:8001/api/v1/outreach/campaigns/{id}/contacts?limit=5"
  # Expected: 50 contacts with firm details
  ```
- [ ] Verify stats endpoint:
  ```bash
  curl -H "X-API-Key: <key>" http://localhost:8001/api/v1/outreach/campaigns/{id}/stats
  # Expected: total_contacts=50, pending=50, all rates=0.0
  ```
- [ ] Verify CSV export:
  ```bash
  curl -H "X-API-Key: <key>" -o export.csv http://localhost:8001/api/v1/outreach/campaigns/{id}/export
  # Open export.csv — should have 50 rows + header
  ```
- [ ] Verify OpenAPI docs are accessible:
  ```bash
  curl http://localhost:8001/docs
  # Expected: Swagger UI loads
  ```
- [ ] Tear down:
  ```bash
  docker-compose down -v
  ```

**Acceptance criteria:**
- All services start and pass health checks
- Seed script creates campaign and imports all contacts
- Stats and export endpoints return correct data
- OpenAPI documentation is complete and accurate
- Clean teardown removes all containers and volumes

---

## File Summary

| Task | File(s) | Type |
|------|---------|------|
| 1 | `app/api/dashboard.py` | New |
| 2 | `app/api/dashboard.py` | Modify (add export endpoint) |
| 3 | `app/schemas/stats.py` | New |
| 4 | `Dockerfile`, `.dockerignore` | New |
| 5 | `docker-compose.yml` | New |
| 6 | `.env.example` | New |
| 7 | `README.md` | New |
| 8 | `scripts/seed_solicitor_campaign.py` | New |
| 9 | `alembic.ini`, `migrations/env.py`, `migrations/versions/.gitkeep` | New |
| 10 | `railway.toml` | New |
| 11 | `tests/test_e2e_campaign.py` | New |
| 12 | (manual verification) | N/A |

## Estimated Effort

| Task | Estimate |
|------|----------|
| Tasks 1-3 (Dashboard + Schema) | 2-3 hours |
| Task 4 (Dockerfile) | 1 hour |
| Task 5 (docker-compose) | 1 hour |
| Task 6 (.env.example) | 30 min |
| Task 7 (README) | 1-2 hours |
| Task 8 (Seed script) | 2-3 hours |
| Task 9 (Alembic) | 1-2 hours |
| Task 10 (Railway config) | 1 hour |
| Task 11 (Integration test) | 2-3 hours |
| Task 12 (Smoke test) | 30 min |
| **Total** | **~12-16 hours** |

## Dependencies Graph

```
Task 3 (Schema) ──→ Task 1 (Stats endpoint) ──→ Task 2 (Export endpoint)
                                                        │
Task 9 (Alembic) ──→ Task 4 (Dockerfile) ──→ Task 5 (docker-compose)
                                                        │
Task 6 (.env.example) ──→ Task 5 (docker-compose)      │
                                                        │
Task 10 (Railway) ──→ (depends on Task 4)               │
                                                        ↓
Task 7 (README) ──→ (depends on Tasks 4-6, 8, 10)      │
                                                        │
Task 8 (Seed script) ──→ (depends on Tasks 1-5)        │
                                                        ↓
Task 11 (Integration test) ──→ (depends on Tasks 1-3, 8)
                                                        ↓
Task 12 (Smoke test) ──→ (depends on ALL previous tasks)
```
