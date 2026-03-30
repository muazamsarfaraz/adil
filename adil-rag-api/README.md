# adil-rag-api

![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)
![Python](https://img.shields.io/badge/python-3.11+-blue)

**AskAdil RAG API -- RAG service for UK discrimination law queries.**

Part of [AskAdil by MCB](https://askadil.org) (Muslim Council of Britain).

---

## What It Does

The RAG API is the backend intelligence layer for AskAdil. It uses Google Gemini with File Search Tool (FST) grounded in a UK legislation corpus to provide accurate, citation-backed legal education. The service handles multi-turn conversations, content analysis, viability assessments, report generation, and solicitor directory lookups.

## Features

| Feature | Description |
|---------|-------------|
| **Multi-turn conversation** | Session-aware legal Q&A with conversation history |
| **Citation extraction** | Specific legislation sections with links to legislation.gov.uk |
| **Viability assessment** | Structured scoring (0-100) with Vento bands and case law precedent |
| **Content analysis** | Extract and analyse content from YouTube, Twitter/X, Facebook, Instagram, and news URLs |
| **Image analysis** | Gemini Flash vision for screenshots and document photos |
| **Report generation** | 5 report types: incident summary, solicitor pack, police/Tell MAMA/Police Scotland guides |
| **Hate crime reporting** | Orchestrates report submission via adil-report-bridge (7 UK targets) |
| **Solicitor directory** | 24 curated firms filterable by jurisdiction, specialism, and location |
| **Jurisdiction detection** | Auto-detect UK jurisdiction from IP via ip-api.com |
| **Anonymised logging** | Conversation metadata to Postgres (no PII) |
| **Email receipts** | Confirmation emails via SendGrid after report submission |

---

## Key Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/v1/query` | Required | Multi-turn legal Q&A with viability scoring + evidence checklist |
| `POST /api/v1/analyze` | Required | Content extraction + legal analysis from URLs |
| `POST /api/v1/query/image` | Required | Image analysis via Gemini Flash vision |
| `POST /api/v1/generate-report` | Required | Report generation (5 types) |
| `POST /api/v1/submit-report` | Required | Submit hate crime report (requires consent) |
| `GET /api/v1/solicitors` | Required | Curated solicitor directory (filterable) |
| `GET /api/v1/report-targets` | Required | Available reporting targets with PII requirements |
| `GET /api/v1/analytics` | Required | Aggregate usage statistics |
| `GET /api/v1/detect-jurisdiction` | None | Auto-detect jurisdiction from IP |
| `GET /api/v1/privacy-notice` | None | Structured JSON privacy notice |
| `GET /health` | None | Liveness probe |
| `GET /stats` | Required | Runtime statistics |

Full interactive API docs available at `/docs` (Swagger/OpenAPI) when the service is running.

---

## Quick Start

```bash
# Create .env
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, FILE_SEARCH_STORE_ID, ADIL_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn app:app --host 0.0.0.0 --port 8080
```

### Prerequisites

- Python 3.11+
- Google Gemini API key
- Gemini File Search Tool store with UK legal corpus
- PostgreSQL (for anonymised conversation logging)
- SendGrid API key (for email receipts)

---

## Testing

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
python -m pytest test_backend.py -v
```

---

## Deployment (Railway)

Deploys as a Docker container on Railway.

```bash
cd adil-rag-api
railway link --project <PROJECT_ID> --environment production --service adil-rag-api
railway up -d
```

The RAG API has no public custom domain -- it is called by adil-frontend via the Railway internal URL.

---

## License

Copyright Muslim Council of Britain. All rights reserved.
