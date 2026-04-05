# adil-document-uploader — Design Spec

**Date:** 2026-04-04
**Status:** Draft
**Author:** Muazam + Claude

## Purpose

A FastAPI microservice that fetches UK case law from The National Archives (TNA) Case Law API, stores judgment metadata in Postgres for deduplication and audit, and uploads clean judgment text to the existing Gemini File Search Tool (FST) Store — expanding AskAdil's legal knowledge base.

## Constraints

- **Single Gemini FST Store** — always append to the existing `FILE_SEARCH_STORE_ID`, never create new stores.
- **No bulk computational licence yet** — prototype operates within standard Open Justice Licence (individual searches, <1,000 req/5 min). Will apply for bulk licence separately.
- **Employment Tribunal (ET) gap** — TNA does not host first-instance ET decisions (they're on gov.uk). Out of scope for v1.
- **Railway deployment** — follows the monorepo microservice pattern with `railway.toml`.

## Architecture

### Services (Railway)

| Service | Role | Port |
|---------|------|------|
| `adil-document-uploader` | FastAPI admin API | 8002 |
| `adil-document-uploader-worker` | arq worker (fetch + upload scheduler) | — |
| Postgres | Judgment storage + dedup | 5432 |
| Redis | arq job queue | 6379 |

Single Dockerfile with `SERVICE_ROLE` env var (same pattern as `adil-outreach-engine`):
- `SERVICE_ROLE=api` → runs alembic migrations + uvicorn
- `SERVICE_ROLE=worker` → runs arq worker

### Data Flow

```
TNA Atom API  ──fetch──>  Postgres (judgments)  ──upload──>  Gemini FST Store
                              │
                         dedup on neutral_citation
```

**Fetch cycle** (daily 03:00 UTC via arq cron):
1. Worker iterates predefined search queries against `GET https://caselaw.nationalarchives.gov.uk/atom.xml`
2. Follow `rel="next"` pagination links until results exhausted or rate limit approached
3. For each Atom entry, check if `neutral_citation` exists in Postgres
4. If new: fetch full judgment via `GET /{tna_uri}/data.xml`
5. Parse Akoma Ntoso XML → extract clean plain text (strip XML tags, preserve paragraph structure), parties, date, court
6. Insert into DB with status `pending`
7. Rate limiting: async semaphore, max 150 req/min (safe buffer under the 1,000/5min TNA limit)

**Upload cycle** (runs after fetch):
1. Query judgments with status `pending`
2. Prepend metadata header to clean text:
   ```
   CITATION: [2023] EAT 45
   CASE: Smith v Employer Ltd
   COURT: Employment Appeal Tribunal
   DATE: 2023-06-15
   SOURCE: https://caselaw.nationalarchives.gov.uk/eat/2023/45
   ---
   [judgment text]
   ```
3. Upload to Gemini FST Store via `genai.Client.files.upload()` + associate with store
4. On success: set status `uploaded`, store `gemini_file_id`
5. On failure: set status `failed`, store reason in `error_message` column, retry on next cycle

## Search Domains

Five predefined domains targeting AskAdil's core legal areas:

| Domain | TNA Queries | Courts |
|--------|-------------|--------|
| Religious discrimination (employment) | `"religious discrimination"`, `"Equality Act" religion belief` | `eat`, `ewca/civ` |
| Hate crime / religious hatred | `"religiously aggravated"`, `"religious hatred"`, `"racially aggravated"` | `ewca/crim`, `ewhc/admin` |
| Goods & services discrimination | `"discrimination" "provision of services"`, `"Equality Act" "section 29"` | `ewca/civ`, `ewhc/admin` |
| Intersectional (race + religion) | `"race discrimination" Muslim`, `"ethnic origin" discrimination` | `eat`, `ewca/civ` |
| ECHR / human rights | `"Article 9" religion`, `"Article 14" discrimination` | `uksc`, `ewca/civ` |

Queries are stored as config in `app/config.py`, not hard-coded in tasks — easy to add new domains later.

## Database Schema

### `judgments` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `neutral_citation` | VARCHAR(100) | Unique, e.g. `[2023] EAT 45` |
| `tna_uri` | VARCHAR(200) | e.g. `eat/2023/45` |
| `tna_url` | VARCHAR(500) | Full URL back to TNA |
| `court` | VARCHAR(50) | e.g. `eat`, `ewca/civ` |
| `case_name` | VARCHAR(500) | Parties, e.g. `Smith v Employer Ltd` |
| `judgment_date` | DATE | Date of judgment |
| `search_domain` | VARCHAR(100) | Which of our 5 domains matched |
| `search_query` | VARCHAR(500) | The exact query that found it |
| `raw_xml` | TEXT | Original Akoma Ntoso XML |
| `clean_text` | TEXT | Extracted plain text |
| `status` | ENUM | `pending`, `uploaded`, `skipped`, `failed` |
| `gemini_file_id` | VARCHAR(200) | Set after successful upload |
| `error_message` | TEXT | Last error reason (for failed fetches/uploads) |
| `fetched_at` | TIMESTAMP | When we downloaded from TNA |
| `uploaded_at` | TIMESTAMP | When we pushed to Gemini |
| `created_at` | TIMESTAMP | Row creation |
| `updated_at` | TIMESTAMP | Last modification |

Index on `(neutral_citation)` unique, `(status)`, `(search_domain)`, `(court)`.

## API Endpoints

All behind `ADMIN_API_KEY` header auth except `/health` (unauthenticated for Railway health checks).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check (Railway, no auth) |
| `GET` | `/api/v1/judgments` | List judgments (filter by status, domain, court; paginated) |
| `GET` | `/api/v1/judgments/{id}` | Single judgment detail with source links |
| `POST` | `/api/v1/fetch` | Manually trigger fetch cycle |
| `POST` | `/api/v1/upload` | Manually trigger upload of pending judgments |
| `GET` | `/api/v1/stats` | Counts by status, domain, court |

## Tech Stack

| Concern | Library |
|---------|---------|
| Web framework | FastAPI + uvicorn |
| Task queue / scheduler | arq + Redis |
| ORM / DB | SQLAlchemy async + asyncpg + Postgres |
| Migrations | Alembic |
| HTTP client | httpx (async) |
| XML parsing | lxml |
| Gemini uploads | google-genai |
| Config | pydantic-settings |
| Auth | API key dependency (same pattern as other services) |

## Project Structure

```
adil-document-uploader/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app, lifespan, CORS
│   ├── config.py              # Settings + search domain definitions
│   ├── database.py            # async SQLAlchemy engine + session
│   ├── auth/
│   │   ├── __init__.py
│   │   └── api_key.py         # ADMIN_API_KEY header dependency
│   ├── models/
│   │   ├── __init__.py
│   │   └── judgment.py        # SQLAlchemy Judgment model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── judgment.py        # Pydantic request/response schemas
│   ├── api/
│   │   ├── __init__.py
│   │   ├── judgments.py        # GET /judgments, GET /judgments/{id}
│   │   └── admin.py           # POST /fetch, POST /upload, GET /stats
│   ├── services/
│   │   ├── __init__.py
│   │   ├── tna_client.py      # TNA Atom API client (search + download)
│   │   ├── xml_parser.py      # Akoma Ntoso XML → clean text + metadata
│   │   └── gemini_uploader.py # Upload text to Gemini FST store
│   └── workers/
│       ├── __init__.py
│       ├── settings.py         # arq WorkerSettings + cron schedule
│       └── tasks.py            # fetch_case_law, upload_pending tasks
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_tna_client.py
│   ├── test_xml_parser.py
│   ├── test_gemini_uploader.py
│   ├── test_judgments_api.py
│   └── test_workers.py
├── alembic.ini
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── railway.toml
├── .env.example
├── .dockerignore
└── README.md
```

## Environment Variables

```
# TNA API (no auth needed)
TNA_BASE_URL=https://caselaw.nationalarchives.gov.uk

# Gemini
GEMINI_API_KEY=your_key
FILE_SEARCH_STORE_ID=fileSearchStores/project-adil-legal-knowledg-8gl78e375lwz

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/document_uploader

# Redis
REDIS_URL=redis://localhost:6379

# Auth
ADMIN_API_KEY=your_admin_key

# Service
PORT=8002
SERVICE_ROLE=api
```

## Future Scope (not v1)

- gov.uk Employment Tribunal scraper (separate source, different HTML format)
- HUDOC (ECHR) integration for European human rights case law
- Approval workflow UI before upload (currently auto-uploads all fetched judgments)
- Bulk computational analysis licence (enables higher volume fetching)
- Webhook to notify adil-rag-api when new documents are added to the store
