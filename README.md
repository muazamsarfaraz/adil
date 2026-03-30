# AskAdil | Educate First, Litigate Second

![Services](https://img.shields.io/badge/services-5-blue)
![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)
![License](https://img.shields.io/badge/license-Proprietary-red)

**Free AI-powered UK discrimination law guidance for British Muslims**

[askadil.org](https://askadil.org) | A Muslim Council of Britain Initiative

---

## What is AskAdil?

AskAdil is a legal education platform that helps British Muslims understand their rights under UK discrimination and hate crime law. It uses AI (Google Gemini) grounded in UK legislation and case law to provide accessible, culturally-sensitive legal guidance.

AskAdil is **not a law firm**. It educates users about their rights, helps them gather evidence, and connects them with the right organisations and solicitors when professional help is needed.

### What it does

- Explains UK discrimination law with specific section citations and links to legislation.gov.uk
- Analyses content from YouTube, Facebook, Twitter/X, Instagram, and news articles for legal issues
- Provides actionable next steps with relevant organisations (Tell MAMA, IRU, ACAS, Citizens Advice, etc.)
- Routes users to the right path: **self-service** for hate crime reporting, **solicitor referral** for workplace claims
- Remembers conversation context for natural multi-turn dialogue
- Covers all four UK jurisdictions: England & Wales, Scotland, Northern Ireland
- **Jurisdiction auto-detection** -- automatically detects user's UK jurisdiction from IP address with confirm/change UI
- **Viability scoring** -- structured assessment (0-100 score, Vento band, statutory footing, case law precedent, quantum potential)
- **Dynamic evidence checklist** -- 3-6 tailored items when viability is assessed
- **Report generation** -- incident summaries, solicitor consultation packs, and smart form guides
- **Solicitor directory** -- 24 curated firms filterable by jurisdiction, specialism, and location
- **Image analysis** -- upload screenshots and document photos for AI-powered legal analysis
- **Analytics** -- aggregate usage statistics from anonymised conversation data

### Legal knowledge base

- **Legislation:** Equality Act 2010, Public Order Act 1986, Online Safety Act 2023, Crime and Disorder Act 1998, Human Rights Act 1998, Employment Rights Act 1996, Racial and Religious Hatred Act 2006, Scotland Hate Crime Act 2021, FETO 1998, NI Race Relations Order 1997
- **Case law:** 9+ landmark cases including Scottish case law (Eweida v UK, JH Walker v Hussain, Azmi v Kirklees, Lee v IFoA, Grainger v Nicholson, Ladele v Islington, Chaplin v Royal Devon, Redfearn v UK, Vento v Chief Constable)
- **Vento bands:** 2025-2026 compensation ranges for injury to feelings claims
- **Jurisdictions:** England & Wales, Scotland, Northern Ireland -- with jurisdiction-specific legislation and case law

---

## Architecture

```
askadil.org (Cloudflare)
    |
    v
+-------------------+       +-------------------+       +------------------+
| adil-frontend     | ----> | adil-rag-api      | ----> | Google Gemini    |
| (Chainlit)        | HTTP  | (FastAPI)         | SDK   | + File Search    |
|                   |       |                   |       | Tool (FST)       |
| - Chat UI         |       | - RAG service     |       |                  |
| - Session memory  |       | - Content extract |       | UK legislation   |
| - Action buttons  |       | - Citation parse  |       | corpus           |
| - PII collection  |       | - Report submit   |       +------------------+
| - Consent screen  |       | - Conv. logging   |
+-------------------+       | - Email receipts  |
                            +-------------------+
                                    |           \
+-------------------+       +-------+-------+    +------------------+
| adil-landing      |       |               |    | adil-report-bridge|
| (nginx)           |  +----v------+  +-----v--+ | (FastAPI +       |
|                   |  | yt-dlp    |  | FXTwitter| | browser-use +   |
| - Landing page    |  | YouTube   |  | API      | | Playwright)     |
| - Static HTML/CSS |  | Facebook  |  | Twitter/X| |                 |
| - Quick Exit      |  | Instagram |  +----------+ | - 5 browser     |
+-------------------+  +-----------+              | - 2 email (SG)  |
                                                   +------------------+
                                                          |
+-------------------+                              +------+------+
| adil-outreach-    |                              |   Postgres  |
| engine            |                              | (anon logs) |
| (FastAPI + arq +  |                              +-------------+
| LangGraph)        |
|                   |
| - AI campaigns    |
| - Email outreach  |
| - Conversions     |
+-------------------+
```

### Services

| Service | Tech | Role | README |
|---------|------|------|--------|
| [**adil-frontend**](adil-frontend/) | Chainlit | Conversational UI, session management, action buttons, PII collection flow | [README](adil-frontend/README.md) |
| [**adil-rag-api**](adil-rag-api/) | FastAPI (Python 3.11) | RAG queries, content extraction, citation parsing, legal analysis, report submission | [README](adil-rag-api/README.md) |
| [**adil-outreach-engine**](adil-outreach-engine/) | FastAPI + arq + LangGraph | AI-powered outreach campaigns, email drafting, reply classification, conversion tracking | [README](adil-outreach-engine/README.md) |
| [**adil-report-bridge**](adil-report-bridge/) | FastAPI + browser-use + Playwright | AI-powered browser automation to submit reports to external portals; email reports via SendGrid | -- |
| **Postgres** | Railway-managed | Anonymised conversation logs + outreach data (no PII in chat logs) | -- |

All services deploy as Docker containers on Railway. The report bridge has no public domain -- it is reachable only by the RAG API via Railway internal networking.

---

## Live URLs

| URL | Service |
|-----|---------|
| [askadil.org](https://askadil.org) | Frontend (Chat UI) |
| [askadil.com](https://askadil.com) | Landing page |

---

## Key Features

### Automated report submission (7 targets)

AskAdil can submit hate crime reports to external portals on behalf of the user, collecting PII in-chat and requiring explicit consent before submission. The report bridge supports:

| Target | Method | PII Required | Coverage |
|--------|--------|-------------|----------|
| Police UK | Browser (browser-use) | Yes | England & Wales |
| Tell MAMA | Browser (browser-use) | Yes | UK-wide |
| Police Scotland | Browser (browser-use) | Yes | Scotland |
| IRU | Browser (browser-use) | Yes | UK-wide |
| Islamophobia UK | Browser (browser-use) | No (anonymous) | UK-wide |
| EASS | Email (SendGrid) | Yes | England, Wales & Scotland |
| Stop Hate UK | Email (SendGrid) | Yes | UK-wide |

On failure, the bridge falls back to a generated Tier 1 incident summary the user can submit manually.

### AI outreach engine

The outreach engine manages multi-step email campaigns with:
- LLM-driven research and personalised email drafting
- Configurable LLM per agent (Gemini, Claude, GPT)
- Dry-run mode for testing without sending real emails
- Reply classification and automated follow-ups
- Conversion tracking via SendGrid, Stripe, and Cal.com webhooks
- Campaign-as-config: define behaviour via configuration, not code

### Self-service vs Solicitor paths

| Scenario | Path | AskAdil role |
|----------|------|-------------|
| Hate crime / Islamophobia | Self-service | Generate report summary for Tell MAMA, IRU, Police |
| Online hate speech | Self-service | Analyse content, generate report |
| General discrimination enquiry | Self-service | Brief user, direct to EASS / Citizens Advice |
| Workplace discrimination | Solicitor | Explain rights, generate consultation pack, find solicitor |
| Compensation claims | Solicitor | Explain Vento bands, generate case summary, find solicitor |
| Complex / multi-issue cases | Solicitor | Triage, generate case summary, find solicitor |

### Security

- API key authentication (`X-API-Key` header)
- Rate limiting (30/min query, 60/min general)
- SSRF protection on all outbound URL fetches
- Input validation (query 10K chars, content 50K, history 50 turns)
- Prompt injection resistance (Section 0: Integrity & Safety)
- TLS verification on all external requests
- Generic error messages to clients (no detail leakage)

---

## Running Locally

### Prerequisites

- Python 3.11+
- Google Gemini API key
- Gemini File Search Tool store with UK legal corpus

### Backend (adil-rag-api)

```bash
cd adil-rag-api
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, FILE_SEARCH_STORE_ID, ADIL_API_KEY
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

API docs available at `http://localhost:8080/docs`

### Frontend (adil-frontend)

```bash
cd adil-frontend
cp .env.example .env
# Edit .env: set RAG_API_URL=http://localhost:8080, ADIL_API_KEY
pip install -r requirements.txt
chainlit run app.py --host 0.0.0.0 --port 8000
```

### Outreach Engine (adil-outreach-engine)

```bash
cd adil-outreach-engine
cp .env.example .env
# Edit .env: set API keys for SendGrid, Stripe, Cal.com, LLM providers
docker-compose up -d
```

See [adil-outreach-engine/RUNBOOK.md](adil-outreach-engine/RUNBOOK.md) for operational procedures.

### Running Tests

```bash
# RAG API (225+ tests)
cd adil-rag-api && python -m pytest test_backend.py -v

# Outreach engine (222 tests)
cd adil-outreach-engine && pytest

# Report bridge (22 tests)
cd adil-report-bridge && python -m pytest tests/ -v

# Frontend E2E (4 tests)
cd adil-frontend && python -m pytest tests/ -v
```

**Total: 470+ tests** across 4 services.

---

## Deployment

All services deploy to Railway as Docker containers:

| Service | Railway URL | Custom Domain |
|---------|-------------|---------------|
| **adil-frontend** | `adil-frontend-production.up.railway.app` | `askadil.org` |
| **adil-rag-api** | `adil-rag-api-production.up.railway.app` | -- |
| **adil-outreach-engine** | API + Worker (2 Railway services) | -- |
| **adil-report-bridge** | Internal only | -- |

Custom domain `askadil.org` is managed via Cloudflare DNS (CNAME to Railway).

### Deployment Notes

- **Deploy from subdirectory:** Always `cd` into the service directory before running `railway up`.
- **Never set `RAILWAY_DOCKERFILE_PATH`** as an env var -- it breaks Railway's auto-detection for subdirectory deploys.
- All services have `railway.toml` with healthcheck configuration.

---

## Documentation

| Document | Location |
|----------|----------|
| Business case & research | `docs/plans/` |
| Outreach engine runbook | [adil-outreach-engine/RUNBOOK.md](adil-outreach-engine/RUNBOOK.md) |
| Reporting integration roadmap | `adil-rag-api/docs/plans/2026-03-07-reporting-integration-roadmap.md` |
| Outreach engine design | `adil-outreach-engine/docs/2026-03-26-outreach-engine-design.md` |
| Privacy notice | `adil-rag-api/docs/privacy-notice.md` |

---

## Project Structure

```
adil/
├── README.md                         # This file (monorepo overview)
├── adil-frontend/                    # Frontend (Chainlit) -- 4 E2E tests
│   ├── app.py                        # Chat handlers, session management
│   ├── public/                       # Theme, logos, branding
│   └── README.md
├── adil-rag-api/                     # Backend (FastAPI) -- 225+ tests
│   ├── app.py                        # Endpoints, auth, rate limiting
│   ├── rag_service.py                # RAG logic, Gemini FST
│   ├── docs/plans/                   # Business docs, roadmaps
│   └── README.md
├── adil-outreach-engine/             # Outreach engine (FastAPI + arq) -- 222 tests
│   ├── app/                          # API, agents, workers, services
│   ├── RUNBOOK.md                    # Operational runbook
│   └── README.md
├── adil-report-bridge/               # Report bridge (internal) -- 22 tests
│   ├── app.py                        # /submit, /health, /targets
│   └── browser_agent.py              # browser-use + Playwright
└── adil-landing/                     # Landing page (nginx) -- WCAG 2.2 AA
    └── index.html                    # Single-page landing
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Google Gemini (gemini-2.5-flash / gemini-2.5-pro / gemini-3-flash-preview) |
| Grounding | Gemini File Search Tool (FST) |
| Backend | FastAPI, Python 3.11 |
| Frontend | Chainlit v2.9.6 |
| Outreach agents | LangGraph + arq (Gemini, Claude, GPT) |
| Report bridge | FastAPI + browser-use + Playwright + Chromium |
| Database | Postgres (Railway-managed) |
| Email | SendGrid |
| Payments | Stripe |
| Bookings | Cal.com |
| Data validation | Pydantic v2 |
| Content extraction | yt-dlp, youtube-transcript-api, BeautifulSoup4, FXTwitter API |
| Rate limiting | slowapi |
| Deployment | Railway (Docker) |
| DNS / CDN | Cloudflare |
| CI/CD | GitHub Actions (lint+test on PR) |
| Linting | Ruff (check + format) |
| E2E testing | Playwright |

---

## Legal Disclaimer

AskAdil is an educational tool, not a law firm. It does not provide legal advice, create solicitor-client relationships, or guarantee any legal outcomes. Users should always consult a qualified solicitor before taking legal action.

---

## License

Copyright Muslim Council of Britain. All rights reserved.
