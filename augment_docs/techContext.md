# Tech Context — Project Ad'l

## Stack

| Layer | Technology | Version/Notes |
|-------|-----------|---------------|
| **LLM** | Google Gemini | `gemini-2.5-flash` (intake), `gemini-2.5-pro` (complex triage), `gemini-3-flash-preview` (image/vision), `gemini-2.5-flash` (browser-use agent) |
| **Grounding** | Gemini File Search Tool (FST) | Store: `fileSearchStores/project-adil-legal-knowledg-8gl78e375lwz` |
| **Backend** | FastAPI (Python) | Python 3.11-slim Docker |
| **Frontend** | Chainlit | v2.9.6+ (patched CVE-2025-68492, CVE-2026-22218, CVE-2026-22219) with custom Islamic green theme via `public/theme.json` |
| **Report Bridge** | FastAPI + browser-use + Playwright | Python 3.11-slim + Chromium. Internal Railway service only. Supports 5 browser targets + 2 email targets. |
| **Database** | Postgres | Railway-managed. Stores anonymised conversation logs only — no PII. |
| **Email** | SendGrid | Email adapter (HTML+plain-text reports to EASS, Stop Hate UK) + email receipts to users after submission. Sender: `noreply@mcbx.app`. |
| **HTTP Client** | httpx | v0.25.0+ (frontend → backend; RAG API → bridge) |
| **Data Validation** | Pydantic v2 | Request/response models |
| **Web Scraping** | BeautifulSoup4 | Content extraction (OG meta scrape, fallback in cascade) |
| **YouTube** | youtube-transcript-api + yt-dlp | v1.2+ transcript extraction; Shorts/Live URL support; graceful manual-paste fallback |
| **Content Extraction** | yt-dlp | v2025.1.0+ cascade extraction for Facebook, Instagram, Twitter/X video |
| **Geolocation** | ip-api.com | Free IP geolocation API for jurisdiction auto-detection (no API key needed) |
| **Twitter/X API** | FXTwitter | Free API for tweet metadata (text, media) — replaces Nitter |
| **Landing Page** | nginx:alpine | Static HTML/CSS/JS, `envsubst` for `$PORT` |
| **Image Generation** | Gemini | `gemini-3-pro-image-preview` for concept images |
| **Deployment** | Railway | GitHub-linked via `muazamsarfaraz/adil` (private) + CLI upload |
| **Containers** | Docker | Python 3.11-slim (backend/frontend/bridge), nginx:alpine (landing) |
| **CI/CD** | GitHub Actions | Lint (ruff) + test on PR; repo: `muazamsarfaraz/adil` (private) |
| **Pre-commit** | pre-commit | ruff lint + ruff format hooks |
| **Linting** | Ruff | `ruff check .` + `ruff format .` configured in `pyproject.toml` |
| **Type Checking** | mypy | Configured in `pyproject.toml` |

## Environment Variables

### adil-rag-api (Service A)
| Variable | Description | Source |
|----------|-------------|--------|
| `GEMINI_API_KEY` | Google Gemini API key | `.env` |
| `FILE_SEARCH_STORE_ID` | Gemini FST store identifier | `.env` / Railway |
| `ADIL_API_KEY` | API key for backend auth | `.env` / Railway |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (optional override) | Railway |
| `RATE_LIMIT_QUERY` | Rate limit for query endpoints (default: `30/minute`) | Railway |
| `RATE_LIMIT_GENERAL` | Rate limit for general endpoints (default: `60/minute`) | Railway |
| `GEMINI_MODEL_VISION` | Vision model for image analysis (default: `gemini-3-flash-preview`) | `.env` / Railway |
| `MAX_IMAGE_SIZE_MB` | Max image upload size in MB (default: `10`) | `.env` / Railway |
| `PORT` | Server port (default: 8080) | Railway auto-set |

### adil-rag-api additional vars (added 2026-03-22)
| Variable | Description | Source |
|----------|-------------|--------|
| `REPORT_BRIDGE_URL` | Internal Railway URL of the bridge service | Railway |
| `BRIDGE_API_KEY` | Shared secret for RAG API → Bridge auth | Railway |
| `SENDGRID_API_KEY` | SendGrid API key for email receipts | Railway |
| `DATABASE_URL` | Postgres connection string for anonymised logs | Railway |

### adil-frontend (Service B)
| Variable | Description | Source |
|----------|-------------|--------|
| `RAG_API_URL` | Backend API URL (`https://adil-rag-api-production.up.railway.app`) | `.env` / Railway |
| `ADIL_API_KEY` | API key for backend auth (sent as `X-API-Key` header) | `.env` / Railway |
| `PORT` | Server port | Railway auto-set |

### adil-report-bridge (Service D)
| Variable | Description | Source |
|----------|-------------|--------|
| `GOOGLE_API_KEY` | Google API key for Gemini via langchain-google-genai | Railway |
| `GEMINI_MODEL` | Model for browser-use agent (default: `gemini-2.5-flash`) | Railway |
| `BRIDGE_API_KEY` | Shared secret for RAG API → Bridge auth | Railway |
| `SENDGRID_API_KEY` | SendGrid API key for email adapter | Railway |
| `PORT` | Server port (injected by Railway) | Railway auto-set |

### Shared / Other Keys (in root `.env`)
| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini (primary) |
| `OPENAI_API_KEY` | OpenAI (WriteToPower AI email generation) |
| `CLAUDE_API_KEY` | Anthropic Claude |
| `ELEVENLABS_API_KEY` | ElevenLabs (TTS) |
| `RAILWAY_API_KEY` | Railway platform API |
| `CLICKUP_API_KEY` | ClickUp project management |
| `DROPBOX_*` | Dropbox cloud storage (MAIA) |

## Railway Deployment

| Property | Value |
|----------|-------|
| **Project ID** | `3b3ce312-40a1-4fba-9367-6e2939ce4404` |
| **Environment** | `production` (`282ea860-2dad-4d39-a2cf-5ae49832c2c5`) |
| **adil-rag-api Service ID** | `2f4a5050-3d4f-46ca-9b0f-29802d04abe3` |
| **adil-frontend Service ID** | `9368215b-d1aa-47b7-b374-abc9e3195d6b` |
| **adil-landing Service ID** | `26e1d709-4c1d-4f96-9493-89ea46013ccf` |
| **adil-report-bridge Service ID** | (set in Railway dashboard after first deploy) |
| **adil-rag-api Domain** | `adil-rag-api-production.up.railway.app` |
| **adil-frontend Domain (Railway)** | `adil-frontend-production.up.railway.app` |
| **adil-landing Domain (Railway)** | `adil-landing-production.up.railway.app` |
| **adil-report-bridge Domain** | Internal only — no public domain |
| **Deploy Method** | GitHub-linked + CLI upload (`railway up`) |
| **GitHub Repo** | `muazamsarfaraz/adil` (private) |

## Custom Domain

| Property | Value |
|----------|-------|
| **Primary Domain** | `https://askadil.org` |
| **WWW Redirect** | `https://www.askadil.org` → `https://askadil.org` (301) |
| **Registrar / DNS** | Cloudflare |
| **SSL** | Railway-managed (auto-provisioned) |

### DNS Records (Cloudflare)

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| `CNAME` | `@` | `djs6g7x6.up.railway.app` | DNS only (grey cloud) |
| `CNAME` | `www` | `mx3ibc84.up.railway.app` | DNS only (grey cloud) |

### Cloudflare Redirect Rule

- **Rule:** `www to bare`
- **When:** Hostname equals `www.askadil.org`
- **Then:** Dynamic redirect → `concat("https://askadil.org", http.request.uri.path)` (301, preserve query string)

## Deploy Commands

```bash
# Deploy backend (from adil-rag-api directory)
railway link --project 3b3ce312-40a1-4fba-9367-6e2939ce4404 --environment production --service adil-rag-api
railway up -d

# Deploy frontend (from adil-frontend directory)
railway link --project 3b3ce312-40a1-4fba-9367-6e2939ce4404 --environment production --service adil-frontend
railway up -d

# Deploy landing page (from adil-landing directory)
railway link --project 3b3ce312-40a1-4fba-9367-6e2939ce4404 --environment production --service adil-landing
railway up -d
```

## Lint / Test Commands

```bash
# Linting (configured in pyproject.toml)
ruff check .
ruff format --check .
mypy .

# Run full test suite — adil-rag-api (225+ tests)
cd adil-rag-api
python -m pytest test_backend.py -v

# Run specific test class
python -m pytest test_backend.py::TestModelValidation -v

# Run report bridge tests (22 tests)
cd adil-report-bridge
python -m pytest tests/ -v

# Run Playwright E2E tests (4 tests)
cd adil-frontend
python -m pytest tests/ -v

# Test dependencies are in requirements-dev.txt (pytest, pytest-asyncio, httpx)

# Pre-commit hooks (run automatically on git commit)
pre-commit run --all-files
```

**Total test count: 250+** (225+ adil-rag-api, 22 adil-report-bridge, 4 Playwright E2E)

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **No LangChain** | Direct `google-genai` SDK. Gemini FST not supported by LangChain wrappers; simple architecture; fewer dependencies = smaller attack surface. |
| **Gemini 3 Flash for vision** | Image analysis uses `gemini-3-flash-preview` via `Part.from_bytes()`. Separate model from text queries (`gemini-2.5-flash`) to isolate vision capability. Same system prompt and FST tool. |
| **Multi-turn via `contents` list** | Not Gemini Chat API. More control; compatible with FST tool config. Conversation history built by `rag_service._build_contents()`. |
| **Suggested questions via regex** | `app._parse_suggested_questions()` parses "Suggested next steps:" from AI text. Simpler than structured output. |
| **Jurisdiction as session context** | Stored in `cl.user_session`, prepended to queries. Not separate knowledge bases (FST corpus is primarily England & Wales). |

## File Structure

```
adil/
├── .env                          # API keys (DO NOT COMMIT)
├── .gitignore                    # Git ignore rules
├── pyproject.toml                # Ruff + mypy configuration
├── .pre-commit-config.yaml       # Pre-commit hooks (ruff lint+format)
├── .github/
│   └── workflows/                # GitHub Actions CI/CD (lint+test on PR)
├── adil-rag-api/                 # Service A: FastAPI backend
│   ├── app.py                    # FastAPI app, endpoints, _parse_suggested_questions(), timing middleware (~680+ lines)
│   ├── rag_service.py            # RAG logic, _build_contents(), Gemini FST, system prompt, viability parser (~900+ lines)
│   ├── content_extractor.py      # URL/content extraction, cascade pattern (~900 lines)
│   ├── models.py                 # Pydantic models (ConversationTurn, ViabilityAssessment, ImageQueryRequest, ReportType, GenerateReportRequest/Response, etc.)
│   ├── report_generator.py       # Report generation: prompt builders + section parser for 5 report types
│   ├── solicitor_directory.py    # Curated solicitor directory: 24 firms, filterable by jurisdiction/specialism/location
│   ├── email_receipt.py          # SendGrid email receipt after successful report submission
│   ├── conversation_log.py       # Anonymised conversation metadata → Postgres (fire-and-forget)
│   ├── geolocation.py            # IP geolocation via ip-api.com, jurisdiction mapping (England & Wales / Scotland / NI)
│   ├── test_backend.py           # Full test suite — 225+ tests
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt      # Test dependencies (pytest, pytest-asyncio, httpx)
│   ├── railway.toml
│   ├── .dockerignore
│   ├── .env.example
│   └── docs/
│       └── plans/
│           ├── 2026-03-07-actionable-next-steps-design.md
│           ├── 2026-03-07-reporting-integration-roadmap.md   # Reporting portal integration PRD
│           └── muslim-solicitors-seed-database.json          # 24 firms, outreach tracking
├── adil-frontend/                # Service B: Chainlit UI
│   ├── app.py                    # Chainlit handlers (session history, action callbacks, jurisdiction selector)
│   ├── chainlit.md               # Welcome page content
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── requirements.txt
│   ├── railway.toml
│   ├── .env.example
│   ├── tests/                    # Playwright E2E tests (4 tests)
│   ├── .chainlit/
│   │   ├── config.toml           # UI config (theme moved to public/theme.json in v2.x)
│   │   └── translations/
│   │       └── en-US.json
│   └── public/
│       ├── theme.json            # Chainlit 2.x theme (Islamic green, HSL CSS vars)
│       ├── custom.js             # Branding override
│       ├── favicon.svg
│       ├── logo_dark.svg
│       └── logo_light.svg
├── adil-report-bridge/           # Service D: Report bridge (internal only)
│   ├── app.py                    # FastAPI app, /submit, /health, /targets endpoints
│   ├── browser_agent.py          # browser-use integration, runs form submission
│   ├── email_adapter.py          # SendGrid email adapter for EASS, Stop Hate UK
│   ├── targets.py                # Target configuration (7 targets: 5 browser, 2 email)
│   ├── models.py                 # Pydantic request/response models
│   ├── screenshot.py             # Screenshot capture + resize/compress to max 500KB
│   ├── Dockerfile                # Python 3.11-slim + Playwright + Chromium
│   ├── requirements.txt
│   ├── railway.toml
│   └── tests/
│       └── test_targets.py       # Config validation tests (22 tests)
├── adil-landing/                 # Service C: Landing page (nginx)
│   ├── index.html                # Single-page HTML/CSS/JS — WCAG 2.2 AA compliant (~1340+ lines)
│   ├── images/                   # Hero + story card images (AI-generated placeholders)
│   │   ├── hero-concept-1-workplace.jpeg
│   │   ├── hero-concept-2-community.jpeg
│   │   └── hero-concept-3-phone.jpeg
│   ├── nginx.conf.template       # nginx config with ${PORT} substitution
│   ├── nginx.conf                # Static fallback (port 80, for local dev)
│   ├── Dockerfile                # nginx:alpine + envsubst
│   └── railway.toml              # Railway build/deploy config
└── augment_docs/                 # Memory Bank (this directory)
```

## Deployment Notes (CRITICAL — Prevents Regressions)

1. **Deploy from subdirectory:** Always `cd` into the service directory before deploying.
   ```bash
   cd adil-rag-api && railway up --service adil-rag-api
   ```

2. **adil-report-bridge uses Dockerfile** (Playwright + Chromium):
   - NEVER set `RAILWAY_DOCKERFILE_PATH` environment variable — it breaks Railway's auto-detection of the Dockerfile.
   - If Railway uses Railpack instead of Dockerfile for the bridge service, change the builder in Dashboard > Settings > Build.
   - `startCommand` is configured in `adil-report-bridge/railway.toml` to ensure correct startup.

3. **All services have `railway.toml`** with healthcheck configuration.

4. **External APIs:**
   - ip-api.com — free tier, no API key needed, used by `geolocation.py` for jurisdiction auto-detection. Rate limit: 45 req/min.

## All API Endpoints (13)

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/` | GET | No | Service discovery |
| `/health` | GET | No | Liveness probe |
| `/stats` | GET | Yes | Runtime statistics |
| `/api/v1/query` | POST | Yes | Multi-turn legal Q&A with viability scoring + evidence checklist |
| `/api/v1/analyze` | POST | Yes | Content extraction + legal analysis |
| `/api/v1/query/image` | POST | Yes | Image analysis (Gemini Flash vision) |
| `/api/v1/generate-report` | POST | Yes | Report generation (5 types: incident_summary, solicitor_pack, police_uk_guide, tell_mama_guide, police_scotland_guide) |
| `/api/v1/privacy-notice` | GET | No | Privacy policy JSON |
| `/api/v1/report-targets` | GET | Yes | Available reporting targets |
| `/api/v1/submit-report` | POST | Yes | Submit hate crime report via bridge |
| `/api/v1/solicitors` | GET | Yes | Curated solicitor directory (24 firms, filterable) |
| `/api/v1/analytics` | GET | Yes | Anonymised usage analytics |
| `/api/v1/detect-jurisdiction` | GET | No | Auto-detect jurisdiction from IP (via ip-api.com) |

---
*Updated: 2026-03-25*

