# AskAdil | Educate First, Litigate Second

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

### Legal knowledge base

- **Legislation:** Equality Act 2010, Public Order Act 1986, Online Safety Act 2023, Crime and Disorder Act 1998, Human Rights Act 1998, Employment Rights Act 1996, Racial and Religious Hatred Act 2006
- **Case law:** 9 landmark cases (Eweida v UK, JH Walker v Hussain, Azmi v Kirklees, Lee v IFoA, Grainger v Nicholson, Ladele v Islington, Chaplin v Royal Devon, Redfearn v UK, Vento v Chief Constable)
- **Vento bands:** 2025-2026 compensation ranges for injury to feelings claims

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
                                                   +------+------+
                                                   |   Postgres  |
                                                   | (anon logs) |
                                                   +-------------+
```

### Four services

| Service | Tech | Role |
|---------|------|------|
| **adil-rag-api** | FastAPI (Python 3.11) | Backend: RAG queries, content extraction, citation parsing, legal analysis, report submission orchestration |
| **adil-frontend** | Chainlit | Frontend: conversational UI, session management, action buttons, PII collection flow |
| **adil-report-bridge** | FastAPI + browser-use + Playwright | Internal bridge: AI-powered browser automation to submit reports to external portals; also sends email reports via SendGrid |
| **Postgres** | Railway-managed | Anonymised conversation log (topic, jurisdiction, message count, response time, tokens — no PII) |

All four deploy as Docker containers on Railway. The report bridge has no public domain — it is reachable only by the RAG API via Railway internal networking.

---

## Key features

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

### Email receipts

After a successful report submission, AskAdil sends the user a confirmation email from `noreply@mcbx.app` via SendGrid. The email includes the reference number, incident summary, next steps, and useful links. Skipped for anonymous targets (no email to send to).

### Anonymised conversation logging

Every conversation logs anonymised metadata to Postgres: topic category, jurisdiction, message count, response time, and token usage. No PII is ever written. Fire-and-forget — never blocks responses.

### Privacy notice

A machine-readable privacy notice is available at `GET /api/v1/privacy-notice` (no auth required). The human-readable version is at `docs/privacy-notice.md`.

### Actionable next steps

Every response includes a "What You Can Do Now" section with 3-5 organisations selected by the AI based on:
- **Topic:** hate crime, workplace, online, services
- **Jurisdiction:** England/Wales, Scotland, NI
- **Severity:** urgent situations lead with emergency numbers

24 organisations across 7 categories including Tell MAMA, IRU, Police, EASS, ACAS, Citizens Advice, Law Society, Employment Tribunal, and jurisdiction-specific equivalents.

### Content extraction

Paste any URL and AskAdil extracts the content and analyses it for legal issues:
- **YouTube** — transcripts via youtube-transcript-api, fallback to yt-dlp
- **Facebook** — video metadata via yt-dlp, OG meta scrape fallback
- **Twitter/X** — tweet text via FXTwitter API, video via yt-dlp
- **Instagram** — OG meta scrape, yt-dlp fallback
- **News articles** — full text extraction via BeautifulSoup4

### Multi-turn conversation

Conversation history is maintained per session. The AI remembers what you've told it and builds on previous context. Suggested follow-up questions appear as clickable buttons.

### Security

- API key authentication (`X-API-Key` header)
- Rate limiting (30/min query, 60/min general)
- SSRF protection on all outbound URL fetches
- Input validation (query 10K chars, content 50K, history 50 turns)
- Prompt injection resistance (Section 0: Integrity & Safety)
- TLS verification on all external requests
- Generic error messages to clients (no detail leakage)

---

## Self-service vs Solicitor paths

AskAdil routes users to the appropriate action path:

| Scenario | Path | AskAdil role |
|----------|------|-------------|
| Hate crime / Islamophobia | Self-service | Generate report summary for Tell MAMA, IRU, Police |
| Online hate speech | Self-service | Analyse content, generate report |
| General discrimination enquiry | Self-service | Brief user, direct to EASS / Citizens Advice |
| Workplace discrimination | Solicitor | Explain rights, generate consultation pack, find solicitor |
| Compensation claims | Solicitor | Explain Vento bands, generate case summary, find solicitor |
| Complex / multi-issue cases | Solicitor | Triage, generate case summary, find solicitor |

For solicitor-path cases, AskAdil generates a **Solicitor Consultation Pack** with the case summary, key dates, relevant legislation, and questions to ask at the first appointment.

---

## Reporting integration roadmap

A 4-tier phased approach to integrating with UK reporting portals:

| Tier | Timeline | What | Partnership needed? |
|------|----------|------|-------------------|
| **1** | Immediate | Incident Summary Generator + Solicitor Consultation Pack | No |
| **2** | 3-6 months | Smart Form Guides (step-by-step for each organisation's form) | No |
| **3** | 6-12 months | Referral Partnerships (API/email submission with consent) | Yes |
| **4** | 12-24 months | Third Party Reporting Centre status with Police Scotland / Tell MAMA | Yes |

See `docs/plans/2026-03-07-reporting-integration-roadmap.md` for full details including form field analysis for IRU, Tell MAMA, Police Scotland, ACAS, ET1, and others.

### Consumer API — key endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/v1/query` | Required | Main RAG query; `ConversationTurn.role` is `"model"` (Gemini convention, not `"assistant"`) |
| `GET /api/v1/report-targets` | Required | Returns available targets; includes `pii_required: bool` per target |
| `POST /api/v1/submit-report` | Required | Submits report; requires `consent_confirmed: true` (rejected if false) |
| `GET /api/v1/privacy-notice` | None | Structured JSON privacy notice |

### Find a Muslim Solicitor

A seed database of 24 solicitor firms (8 Muslim-community-focus, 8 discrimination specialists, 5 Scotland, 3 NI) has been researched for a future "Find a Muslim Solicitor" feature. All firms require outreach and consent before listing.

See `docs/plans/muslim-solicitors-seed-database.json` for the full database.

---

## Running locally

### Prerequisites

- Python 3.11+
- Google Gemini API key
- Gemini File Search Tool store with UK legal corpus

### Backend (adil-rag-api)

```bash
cd adil-rag-api

# Create .env
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, FILE_SEARCH_STORE_ID, ADIL_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn app:app --host 0.0.0.0 --port 8080
```

API docs available at `http://localhost:8080/docs`

### Frontend (adil-frontend)

```bash
cd adil-frontend

# Create .env
cp .env.example .env
# Edit .env: set RAG_API_URL=http://localhost:8080, ADIL_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run
chainlit run app.py --host 0.0.0.0 --port 8000
```

### Running tests

```bash
cd adil-rag-api

# Install test dependencies
pip install -r requirements-dev.txt

# Run all 125 tests
python -m pytest test_backend.py -v
```

---

## Deployment

All three services deploy to Railway as Docker containers:

```bash
# Backend
cd adil-rag-api
railway link --project <PROJECT_ID> --environment production --service adil-rag-api
railway up -d

# Frontend (Chat UI)
cd adil-frontend
railway link --project <PROJECT_ID> --environment production --service adil-frontend
railway up -d

# Landing page
cd adil-landing
railway link --project <PROJECT_ID> --environment production --service adil-landing
railway up -d
```

### Domains

| Service | Railway URL | Custom domain |
|---------|-------------|---------------|
| **adil-rag-api** | `adil-rag-api-production.up.railway.app` | — |
| **adil-frontend** | `adil-frontend-production.up.railway.app` | `askadil.org` |
| **adil-landing** | `adil-landing-production.up.railway.app` | — (pending) |

Custom domain `askadil.org` is managed via Cloudflare DNS (CNAME to Railway).

---

## Project structure

```
adil/
├── README.md
├── .env                              # API keys (DO NOT COMMIT)
├── adil-rag-api/                     # Backend (FastAPI)
│   ├── app.py                        # Endpoints, auth, rate limiting
│   ├── rag_service.py                # RAG logic, Gemini FST, system prompt
│   ├── content_extractor.py          # URL/content extraction
│   ├── models.py                     # Pydantic request/response models
│   ├── test_backend.py               # 125 tests
│   ├── requirements.txt
│   ├── requirements-dev.txt          # Test dependencies
│   ├── Dockerfile
│   └── docs/plans/
│       ├── 2026-03-07-actionable-next-steps-design.md
│       ├── 2026-03-07-reporting-integration-roadmap.md
│       └── muslim-solicitors-seed-database.json
├── adil-frontend/                    # Frontend (Chainlit)
│   ├── app.py                        # Chat handlers, session management
│   ├── chainlit.md                   # Welcome page
│   ├── Dockerfile
│   └── public/                       # Theme, logos, branding
├── adil-landing/                     # Landing page (nginx)
│   ├── index.html                    # Single-page landing (HTML/CSS/JS)
│   ├── images/                       # Hero + story card images
│   ├── nginx.conf.template           # nginx config with $PORT substitution
│   ├── Dockerfile                    # nginx:alpine with envsubst
│   └── railway.toml                  # Railway build/deploy config
└── augment_docs/                     # Project documentation
    ├── activeContext.md
    ├── productContext.md
    ├── progress.md
    ├── systemPatterns.md
    ├── techContext.md
    └── todo.md
```

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| LLM | Google Gemini (gemini-2.5-flash / gemini-2.5-pro) |
| Grounding | Gemini File Search Tool (FST) |
| Backend | FastAPI, Python 3.11 |
| Frontend | Chainlit v2.9.6 |
| Report bridge | FastAPI + browser-use + Playwright + Chromium |
| Database | Postgres (Railway-managed, anonymised logs only) |
| Email | SendGrid (email adapter + email receipts) |
| Data validation | Pydantic v2 |
| Content extraction | yt-dlp, youtube-transcript-api, BeautifulSoup4, FXTwitter API |
| HTTP client | httpx (async, persistent connections) |
| Rate limiting | slowapi |
| Landing page | nginx (Alpine), static HTML/CSS/JS |
| Deployment | Railway (Docker) |
| DNS / CDN | Cloudflare |

---

## Legal disclaimer

AskAdil is an educational tool, not a law firm. It does not provide legal advice, create solicitor-client relationships, or guarantee any legal outcomes. Users should always consult a qualified solicitor before taking legal action.

---

## License

Copyright Muslim Council of Britain. All rights reserved.
