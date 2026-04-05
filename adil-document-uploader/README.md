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
- **Worker** (arq) — scheduled daily fetch at 03:00 UTC + upload at 03:30 UTC
- **Postgres** — judgment storage, deduplication on neutral_citation
- **Redis** — arq job queue

## Railway Deployment

Two services from the same Dockerfile:
- API service: `SERVICE_ROLE=api` (default)
- Worker service: `SERVICE_ROLE=worker`

## Search Domains

Five predefined legal domains targeting AskAdil's core areas:
1. Religious discrimination (employment)
2. Hate crime / religious hatred
3. Goods & services discrimination
4. Intersectional (race + religion)
5. ECHR / human rights

## Environment Variables

See `.env.example` for all required variables.
