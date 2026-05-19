# adil-document-uploader

Fetches UK case law from The National Archives (TNA) and uploads to the Gemini File Search
Tool Store used by adil-rag-api for RAG. Runs as both an API service and a background worker.

## Deploy

**Deploy from the repo root, NOT from this directory.** Use the wrapper scripts:

```bash
# from anywhere
./adil-document-uploader/deploy.sh                                 # api service
./adil-document-uploader/deploy.sh adil-document-uploader-worker   # worker service
```

```powershell
# Windows
./adil-document-uploader/deploy.ps1
./adil-document-uploader/deploy.ps1 adil-document-uploader-worker
```

The wrapper `cd`s to the repo root before invoking `railway up --service <name>`.

### Why the root-of-repo gotcha

Running `railway up` from inside `adil-document-uploader/` wraps the upload
bundle in a subdirectory named after the folder. With `rootDirectory=/` the
build can't find the Dockerfile; with `rootDirectory=adil-document-uploader`
Railway prepends the path to itself
(`adil-document-uploader/adil-document-uploader/Dockerfile`) and the build
fails with **"Dockerfile does not exist"**.

The service instance is configured (via Railway API) with:
- `rootDirectory = adil-document-uploader`
- `railwayConfigFile = adil-document-uploader/railway.toml`
- `builder = DOCKERFILE` (via `railway.toml`)

So the bundle must be the **repo root** so Railway can resolve
`<bundle>/adil-document-uploader/Dockerfile`. Same pattern as `adil-report-bridge`.

Two Railway services share this codebase: one with `SERVICE_ROLE=api`
(`adil-document-uploader`), one with `SERVICE_ROLE=worker`
(`adil-document-uploader-worker`). Both are deployed via the same wrapper.

## Endpoints (API mode)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | none | Liveness probe |
| GET | `/api/v1/judgments` | admin key | List judgments (paginated, filterable) |
| GET | `/api/v1/judgments/{id}` | admin key | Judgment details |
| POST | `/api/v1/fetch` | admin key | Trigger TNA fetch cycle |
| POST | `/api/v1/upload` | admin key | Upload pending judgments to Gemini FST |
| GET | `/api/v1/stats` | admin key | Judgment counts by status/domain/court |

## Environment Variables

| Var | Required | Description |
|-----|----------|-------------|
| `DATABASE_URL` | Yes | Postgres connection string |
| `ADMIN_API_KEY` | Yes | Admin endpoint auth |
| `GEMINI_API_KEY` | Yes | Google Gemini key |
| `FILE_SEARCH_STORE_ID` | Yes | Single FST store — always append, never create new |
| `REDIS_URL` | Yes | arq task queue (default: redis://localhost:6379) |
| `TNA_BASE_URL` | No | Default: https://caselaw.nationalarchives.gov.uk |
| `TNA_MAX_REQUESTS_PER_MINUTE` | No | Default: 150 |
| `TELEGRAM_BOT_TOKEN` | No | Heartbeat notifications |
| `TELEGRAM_CHAT_ID` | No | Target chat |
| `RAG_API_URL` | No | Keep-alive queries to RAG API |
| `RAG_API_KEY` | No | Auth for keep-alive queries |
| `PORT` | No | Default: 8002 |
| `SERVICE_ROLE` | Yes | `api` or `worker` |

## FST Rule

**There is exactly one File Search Tool Store.** Always use `FILE_SEARCH_STORE_ID`.
Never create a new store — it breaks the RAG pipeline.

## Worker Tasks (arq)

- `fetch_case_law()` — Discovers new TNA judgments across configured search domains
- `upload_pending()` — Uploads fetched judgment PDFs/XMLs to Gemini FST
- `fetch_acts()` — Fetches UK Acts (CLML XML) from legislation.gov.uk, parses
  Sections + Subsections into the local `acts` / `act_sections` /
  `act_subsections` tables, and (when `RAG_API_DATABASE_URL` is set AND
  `ontology_node` exists) mirrors `Statute` / `Section` / `Subsection` nodes
  into rag-api's ontology via raw asyncpg. Monthly cron, 1st @ 05:00 UTC.
  Seed list lives in `app/services/acts_seed.py`.

Search domains: religious discrimination, hate crime, goods/services discrimination,
intersectional discrimination, ECHR human rights, mental capacity/deputyship.

## Hourly Cleanup

Rate-limit counters and expired upload records are purged on an hourly cron via arq.
