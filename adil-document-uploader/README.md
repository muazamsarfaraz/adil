# adil-document-uploader

Case law fetcher and Gemini File Search Tool store uploader for AskAdil.

Fetches UK discrimination/equality case law from The National Archives (TNA) Case Law API, deduplicates against Postgres, and uploads judgment text to the existing Gemini FST store — expanding AskAdil's legal knowledge base.

## Quick Start

```bash
# Copy env and fill in values
cp .env.example .env

# Start services
docker-compose up -d

# Run migrations
alembic upgrade head

# Manual fetch (downloads case law from TNA)
curl -X POST http://localhost:8002/api/v1/fetch -H "X-Admin-Key: $ADMIN_API_KEY"

# Manual upload (pushes pending judgments to Gemini store)
curl -X POST http://localhost:8002/api/v1/upload -H "X-Admin-Key: $ADMIN_API_KEY"

# Check stats
curl http://localhost:8002/api/v1/stats -H "X-Admin-Key: $ADMIN_API_KEY"
```

## Architecture

- **API** (FastAPI) — admin endpoints for manual triggers and judgment browsing
- **Worker** (arq) — scheduled case law pipeline + platform health heartbeat
- **Postgres** — judgment storage, deduplication on neutral_citation
- **Redis** — arq job queue

## Scheduled Jobs

| Job | Cadence | Purpose |
|-----|---------|---------|
| `fetch_case_law` | Daily 03:00 UTC | Pull new judgments from TNA across 5 domains |
| `upload_pending` | Daily 03:30 UTC | Upload pending judgments to Gemini FST store |
| `heartbeat` | Every 6h (00/06/12/18 UTC) | Full health check + keep-alive, always reports to Telegram |
| `heartbeat_alert_only` | Hourly | Same checks, only messages Telegram on failure |

## Platform Heartbeat

The worker runs a heartbeat task that:

1. **Service health checks** — HTTP GET to each configured service (rag-api, frontend, doc-uploader, outreach-engine)
2. **RAG pipeline keep-alive** — Sends a real legal query (`"what is indirect religious discrimination under the Equality Act 2010?"`) to `adil-rag-api/api/v1/query`. This walks the full pipeline: FastAPI → RAGService → Gemini FST retrieval, which keeps the File Search store marked as active AND verifies end-to-end correctness
3. **Judgment stats** — Counts by status pulled from Postgres
4. **Telegram notification** — Formatted report sent to the configured chat via `@askAdil_Healthbot`

Configure via:
- `TELEGRAM_BOT_TOKEN` — bot API token from `@BotFather`
- `TELEGRAM_CHAT_ID` — chat to receive heartbeats
- `RAG_API_URL` — base URL of adil-rag-api (default: production URL)
- `RAG_API_KEY` — API key for the RAG query endpoint
- `HEARTBEAT_TARGETS` — comma-separated `name=url` list of services to check

## Railway Deployment

Two services from the same Dockerfile:
- API service: `SERVICE_ROLE=api` (default)
- Worker service: `SERVICE_ROLE=worker`

## Search Domains

Six predefined legal domains targeting AskAdil's core areas:
1. Religious discrimination (employment)
2. Hate crime / religious hatred
3. Goods & services discrimination
4. Intersectional (race + religion)
5. ECHR / human rights
6. **Mental capacity / deputyship** — Court of Protection (EWCOP), Cheshire West, JB, Re D — supports families asking about LPAs, welfare deputyship, best interests for adults with learning disabilities

## Environment Variables

See `.env.example` for all required variables.
