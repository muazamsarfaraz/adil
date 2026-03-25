# Progress — Project Ad'l

## Completed

| Date | Task | Notes |
|------|------|-------|
| 2026-02-16 | Codebase recovery from Railway | 22/22 files extracted via SSH, MD5-verified |
| 2026-02-16 | Environment variables secured | `FILE_SEARCH_STORE_ID` + `RAG_API_URL` added to `.env` |
| 2026-02-16 | Sync verification | All files byte-for-byte match deployed containers |
| 2026-02-16 | Memory Bank initialised | `augment_docs/` created with full project documentation |
| 2026-02-16 | Strategic analysis & roadmap added | PRD review integrated into productContext.md, systemPatterns.md, todo.md |
| 2026-02-16 | API key authentication | `X-API-Key` header with `secrets.compare_digest()`, graceful dev-mode fallback |
| 2026-02-16 | Rate limiting | `slowapi` — 30/min query, 60/min general (configurable via env vars) |
| 2026-02-16 | CORS tightened | From `*` to specific origins list + `ALLOWED_ORIGINS` env var |
| 2026-02-16 | Comprehensive Swagger docs | OpenAPI tags, examples, contact, license, `persistAuthorization` |
| 2026-02-16 | Pydantic model documentation | `json_schema_extra` examples on all request/response models |
| 2026-02-16 | Frontend auth integration | `adil-frontend/app.py` sends `X-API-Key` on all backend calls |
| 2026-02-17 | Security hardening deployed | Both services redeployed; auth verified (401 without key, 200 with key) |
| 2026-02-17 | Custom domain `askadil.org` | Connected on Cloudflare, CNAME -> Railway, SSL auto-provisioned |
| 2026-02-17 | WWW redirect | `www.askadil.org` -> `askadil.org` (301 via Cloudflare redirect rule) |
| 2026-02-17 | CORS updated for custom domain | `https://askadil.org` + `https://www.askadil.org` added to allowed origins |
| 2026-02-17 | Chainlit upgraded to v2.9.6 | Patches 3 critical CVEs (auth bypass, file read, SSRF). Theme migrated to `public/theme.json`. Deployed & healthcheck passed |
| 2026-02-19 | Multi-turn conversation memory (backend) | `ConversationTurn` model, `conversation_history` on requests, `_build_contents()` in rag_service, forwarded in app.py endpoints |
| 2026-02-19 | Suggested follow-up questions (backend) | System prompt S8 instructs 3 questions; `_parse_suggested_questions()` regex parser; `suggested_questions` field on responses |
| 2026-02-19 | Jurisdiction awareness (system prompt) | System prompt S7 with England & Wales, Scotland, NI, Wales-specific duties |
| 2026-02-19 | PRD updated with FR4-FR7 | Jurisdiction (FR4), triage/escalation (FR5), conversation memory (FR6), suggested questions (FR7) |
| 2026-02-19 | Triage architecture defined | 3-tier escalation: Tier 1 (self-help), Tier 2 (escalation cards), Tier 3 (MCB referral) |
| 2026-02-19 | No LangChain decision documented | Direct `google-genai` SDK — FST compatibility, simplicity, security |

### 2026-03-07 — Content Extraction, Actionable Next Steps, Security & Tests

| Date | Task | Notes |
|------|------|-------|
| 2026-03-07 | Content extraction overhaul | Facebook: yt-dlp cascade (metadata + subtitles) -> OG meta scrape -> manual fallback. Twitter/X: FXTwitter API -> yt-dlp (video) -> manual fallback. Instagram: OG meta scrape -> yt-dlp (with cookies) -> manual fallback. YouTube: Shorts/Live URL support, graceful manual-paste fallback. All platforms use consistent cascade pattern. |
| 2026-03-07 | Actionable Next Steps (Section 10 in system prompt) | Every post-intake response includes "What You Can Do Now" with 3-5 relevant organisations. Full resource directory: Tell MAMA, IRU, True Vision, Stop Hate UK, EASS, Citizens Advice, ACAS, Law Society, Legal Aid, Employment Tribunal, EHRC. Scotland-specific: Police Scotland, Law Society of Scotland, SLAB. NI-specific: Equality Commission NI, Law Society NI, Advice NI. AI selects based on topic, jurisdiction, severity. |
| 2026-03-07 | Prompt injection resistance | Section 0: INTEGRITY & SAFETY in system prompt |
| 2026-03-07 | SSRF protection | All URL fetching rejects private IPs, internal networks, non-HTTP schemes |
| 2026-03-07 | Error detail leakage fixed | Generic 500 messages to clients; details logged server-side only |
| 2026-03-07 | TLS certificate verification re-enabled | For yt-dlp (was disabled during development) |
| 2026-03-07 | Input length limits | Query 10K chars, content 50K, conversation turn 20K, history max 50 items |
| 2026-03-07 | Thread-safe stats | `asyncio.Lock()` protects shared statistics counters |
| 2026-03-07 | Async Gemini API calls | `asyncio.to_thread()` — no longer blocks event loop |
| 2026-03-07 | Parallel URL processing | `asyncio.gather()` with max 10 URLs |
| 2026-03-07 | Persistent httpx.AsyncClient | Connection reuse across requests |
| 2026-03-07 | Event loop fix | `asyncio.get_event_loop()` replaced with `asyncio.get_running_loop()` |
| 2026-03-07 | Frontend conversation history + suggested questions | Complete and working (was in progress) |
| 2026-03-07 | Code quality cleanup | Duplicate Eweida case removed, BAILII URLs fixed (National Archives fallback), Lee v IFoA marked pending, duplicate ContentType mapping consolidated to dict, litigation keyword check extracted to shared helper, shared yt-dlp options method (DRY), dead ProcessedContent class removed from models.py, ECHR cases correct jurisdiction label, missing act patterns added to extract_legal_metadata, Gemini response.text safety for blocked responses, Content-Type check before webpage scraping, Facebook regex narrowed to video-like paths |
| 2026-03-07 | Test suite: 125 tests (all passing) | Model validation, _parse_suggested_questions, _build_contents, API endpoint contracts, API security, Facebook/Twitter/Instagram extraction, system prompt resource directory (14 tests), system prompt integrity, RAG service citation/legislation/case law, SSRF protection, URL detection, YouTube fallback, process_message |
| 2026-03-07 | requirements-dev.txt created | pytest>=7.0.0, pytest-asyncio>=0.21.0, httpx>=0.25.0 |
| 2026-03-07 | yt-dlp dependency added | `yt-dlp>=2025.1.0` in requirements.txt |
| 2026-03-07 | Actionable next steps design doc | `docs/plans/2026-03-07-actionable-next-steps-design.md` |

### 2026-03-07 — Reporting Integration Roadmap & Solicitor Database

| Date | Task | Notes |
|------|------|-------|
| 2026-03-07 | Reporting Integration Roadmap PRD | `docs/plans/2026-03-07-reporting-integration-roadmap.md` — 4-tier phased integration with UK reporting portals. Covers IRU, Tell MAMA, Police Scotland, Met Police, True Vision, ACAS, ET1, EASS, EHRC. Self-service vs solicitor path split. |
| 2026-03-07 | Portal field research | Detailed form field analysis: IRU (15 fields, 33% mappable), Tell MAMA (10 fields, 50% mappable), Police Scotland (19 fields, 37% mappable but all narrative fields mappable), Met Police (JS form, varies by force), ACAS EC (multi-step wizard), ET1 (requires ACAS certificate), EASS (phone/email only), EHRC (no individual form, routes to EASS) |
| 2026-03-07 | Muslim Solicitor Seed Database | `docs/plans/muslim-solicitors-seed-database.json` — 24 firms (8 Muslim-community-focus, 8 discrimination specialists, 5 Scotland, 3 NI) + 2 professional bodies (AML, MLAG) + 4 general directories. All `outreach_status: "not_contacted"`. |
| 2026-03-07 | Self-service vs Solicitor path design | Hate crime/online hate = self-service (Tell MAMA, IRU, Police). Workplace discrimination/compensation = solicitor path (ACAS -> ET1 via solicitor). Clear routing in roadmap. |
| 2026-03-07 | Solicitor outreach plan | Template email for MCB to contact firms. 3-phase approach: introductory contact -> data collection from consenting firms -> professional body partnerships (AML, MLAG). |
| 2026-03-07 | Find a Muslim Solicitor feature design | Immediate: generic Law Society links. After outreach: curated directory with consent. Long-term: referral service with case summary handoff. |

### 2026-03-07 — Landing Page & Deployment

| Date | Task | Notes |
|------|------|-------|
| 2026-03-07 | Landing page built | `adil-landing/index.html` — single-page HTML/CSS/JS with editorial warmth aesthetic. DM Serif Display + Source Sans 3 fonts, deep Islamic green (#0D3B1E) + gold (#D4A843) palette, Noto Naskh Arabic for Arabic text. |
| 2026-03-07 | Hero images generated | 3 photorealistic concepts via `gemini-3-pro-image-preview` (workplace hijabi, community centre, phone on bench). AI-generated placeholders — replace with real photography before launch. |
| 2026-03-07 | Landing page sections | Hero with photo + green overlay, social proof bar (7 Acts / 9 Cases / 18 Orgs / 4 Jurisdictions), "People Like You" story cards (3), How It Works (3 steps), Features (4 cards), Two Paths (self-service vs solicitor), Organisations bar, CTA, footer with emergency numbers + legal disclaimer. |
| 2026-03-07 | Quick Exit button | Red fixed-position safety button (top-right). Replaces browser history on click so back button goes to Google. Critical for users researching hate crime/discrimination. |
| 2026-03-07 | Accessibility foundations | Skip-to-content link, semantic `<main>` wrapper, `lang="en"`, ARIA labels on quick exit, warm off-white background (#FAFAF8). |
| 2026-03-07 | Landing page research | 7-area research report: hero best practices, social proof, legal-tech competitive landscape, Muslim community photography, color psychology, CTA optimization, UK accessibility requirements. |
| 2026-03-07 | Deployed adil-landing to Railway | New service: nginx:alpine with `envsubst` for `$PORT`. Live at `adil-landing-production.up.railway.app`. Dockerfile + nginx.conf.template + railway.toml. |

### 2026-03-08 — Image/Screenshot Support (Gemini 3 Flash Vision)

| Date | Task | Notes |
|------|------|-------|
| 2026-03-08 | Image upload support | Users can upload 1-5 images (PNG, JPG, GIF, WebP, max 10MB each) alongside optional text questions. Chainlit `[features.spontaneous_file_upload]` config added. Frontend reads `message.elements`, validates MIME type + file size, base64-encodes, sends to backend. |
| 2026-03-08 | `POST /api/v1/query/image` endpoint | New FastAPI endpoint accepting `ImageQueryRequest` (1-5 base64 images + optional text + conversation history). Validates MIME types and base64 data (returns 400 for invalid). Returns same `QueryResponse` as `/api/v1/query`. |
| 2026-03-08 | `query_with_images()` in RAG service | Multimodal query method using `gemini-3-flash-preview`. Builds image parts via `google.genai.types.Part.from_bytes()`. Same `SYSTEM_INSTRUCTION` and File Search Tool as text queries. Same citation extraction and source building pipeline. |
| 2026-03-08 | New Pydantic models | `ImageData` (mime_type + base64 data), `ImageQueryRequest` (images + optional query + viability + history), `ALLOWED_IMAGE_MIMES` constant, `IMAGE` added to `ContentType` enum. |
| 2026-03-08 | Environment config | `GEMINI_MODEL_VISION` (default: `gemini-3-flash-preview`), `MAX_IMAGE_SIZE_MB` (default: 10). Added to `.env.example` and Railway. |
| 2026-03-08 | Deployed to Railway | Both `adil-rag-api` and `adil-frontend` redeployed via `railway up`. `GEMINI_MODEL_VISION` env var set on backend service. Both deployments STATUS: SUCCESS. |

### 2026-03-22/23/24 — Report Bridge, Email, Logging & Privacy

| Date | Task | Notes |
|------|------|-------|
| 2026-03-22 | Report bridge design spec approved | `docs/superpowers/specs/2026-03-22-report-bridge-design.md` — FastAPI + browser-use + Playwright. MVP target: Police UK only. |
| 2026-03-22 | adil-report-bridge service built | New Railway service. Deployed internally (no public domain). Supports browser-use agent with Gemini Flash for form automation. Concurrency semaphore (max 1). Non-root Chromium. |
| 2026-03-22 | Police UK target implemented | Browser adapter. 7-step multi-step form. PII pass-through, never logged. |
| 2026-03-23 | Additional browser targets added | Tell MAMA, Police Scotland, IRU — browser adapter with per-target config. Total: 4 browser targets. |
| 2026-03-23 | Islamophobia UK target added | Browser adapter, anonymous (no PII required). 5th browser target. |
| 2026-03-23 | Email adapter (`email_adapter.py`) | New adapter type in bridge: sends structured HTML+plain-text reports via SendGrid. Routed by `adapter_type` in target config. |
| 2026-03-23 | EASS + Stop Hate UK email targets | 2 email targets added. Total: 7 targets (5 browser, 2 email). |
| 2026-03-23 | `pii_required: bool` on report-targets response | Frontend uses this to skip PII collection for anonymous targets (Islamophobia UK). |
| 2026-03-23 | `consent_confirmed: bool` on submit-report | submit-report endpoint rejects requests where `consent_confirmed` is false. GDPR compliance. |
| 2026-03-23 | Email receipts (`email_receipt.py`) | New module in RAG API. After successful submission, sends confirmation email from `noreply@mcbx.app` via SendGrid. Includes reference number, summary, next steps, useful links. Skipped for anonymous targets. |
| 2026-03-23 | Anonymised conversation logging (`conversation_log.py`) | New module in RAG API. Logs topic category, jurisdiction, message count, response time, tokens to Postgres. No PII. Fire-and-forget. |
| 2026-03-23 | Postgres service added to Railway | Stores only anonymised conversation metadata. `DATABASE_URL` env var on RAG API. |
| 2026-03-24 | `GET /api/v1/privacy-notice` endpoint | Public (no auth) structured JSON privacy notice. Machine-readable for consuming services. |
| 2026-03-24 | Privacy notice document | `docs/privacy-notice.md` — covers all 7 targets, email receipts, anonymised analytics, SendGrid as third party. |
| 2026-03-24 | Enhanced consent screen in Chainlit | Data handling explanation shown before PII collection. Cancel support added during PII flow. |
| 2026-03-24 | `ConversationTurn.role` documented | Clarified as `"model"` (Gemini convention), not `"assistant"`. Consumer API docs updated. |
| 2026-03-24 | Resource directory expanded to 24 orgs | 5 new orgs added: BTP, Muslim Safety Net, British Muslim Trust, Islamophobia UK, Prevent Watch. |
| 2026-03-24 | Documentation updated | README.md, techContext.md, privacy-notice.md, report-bridge spec all updated to reflect current state. |

### 2026-03-24 — Major Feature Sprint (19 features, 17 commits)

| Date | Task | Notes |
|------|------|-------|
| 2026-03-24 | Git initialisation | `.gitignore` + initial commit of recovered codebase |
| 2026-03-24 | Ruff linting + mypy type checking | Configured in `pyproject.toml`. All code passes. |
| 2026-03-24 | Jurisdiction selector UI | 3 clickable buttons at chat start in Chainlit (England & Wales / Scotland / NI) |
| 2026-03-24 | Report generation models | `ReportType` enum, `GenerateReportRequest`, `GenerateReportResponse` in models.py |
| 2026-03-24 | Report generator module | `report_generator.py` — prompt builders + section parser for 5 report types |
| 2026-03-24 | POST /api/v1/generate-report endpoint | Incident summary + solicitor pack + 3 smart form guides |
| 2026-03-24 | Image endpoint test coverage | Comprehensive tests for `/api/v1/query/image` |
| 2026-03-24 | Final lint pass | All code passes ruff check + ruff format + mypy |
| 2026-03-24 | Structured viability scoring | Parses VIABILITY_ASSESSMENT block from Gemini into `ViabilityAssessment` model (score 0-100, Vento band, statutory_footing, case_law_precedent, quantum_potential) |
| 2026-03-24 | Dynamic evidence checklist | 3-6 tailored items parsed from EVIDENCE_CHECKLIST block when viability requested |
| 2026-03-24 | CI/CD | GitHub repo at `muazamsarfaraz/adil` (private), GitHub Actions for lint+test on PR |
| 2026-03-24 | Analytics endpoint | `GET /api/v1/analytics` with aggregate stats from Postgres |
| 2026-03-24 | Request timing middleware | Logs path, method, status, duration_ms for all requests |
| 2026-03-24 | Secrets audit | Clean — no secrets found in git |
| 2026-03-24 | Playwright E2E tests | 4 tests against live site in adil-frontend |
| 2026-03-24 | Smart Form Guides | `police_uk_guide`, `tell_mama_guide`, `police_scotland_guide` report types added to generate-report |
| 2026-03-24 | Solicitor Directory | `GET /api/v1/solicitors` — 24 firms, filterable by jurisdiction/specialism/location via `solicitor_directory.py` |
| 2026-03-24 | FST Corpus expansion | Scotland Hate Crime Act 2021, FETO 1998, NI Race Relations Order 1997, Scottish case law added to knowledge base |
| 2026-03-24 | Landing page WCAG 2.2 AA | 21 a11y fixes applied + accessibility statement published |
| 2026-03-24 | Pre-commit hooks | ruff lint+format runs automatically before every commit |

### 2026-03-25 — IP-based Jurisdiction Auto-Detection & Deploy Fix

| Date | Task | Notes |
|------|------|-------|
| 2026-03-25 | IP-based jurisdiction auto-detection | New `geolocation.py` module in adil-rag-api. Uses ip-api.com to map IP to UK jurisdiction. New `GET /api/v1/detect-jurisdiction` public endpoint (no auth). |
| 2026-03-25 | Frontend auto-detect UX | Frontend calls detect-jurisdiction on chat start, shows "It looks like you're in X — is that right?" with confirm/change buttons. Seamless fallback to manual selector. |
| 2026-03-25 | Railway deploy fix | `startCommand` added to `adil-report-bridge/railway.toml`. CRITICAL: NEVER set `RAILWAY_DOCKERFILE_PATH` env var — it breaks Railway's auto-detection of Dockerfile. |

**Test counts after sprint:** adil-rag-api 225+, adil-report-bridge 22, adil-frontend 4 Playwright E2E = **250+ total**

## In Progress

| Task | Status | Notes |
|------|--------|-------|
| Deploy 2026-03-25 sprint to Railway | 📋 Pending | Push all changes to production |
| Landing page custom domain | 📋 Pending | Assign `landing.askadil.org` or swap as main domain via Cloudflare |
| Replace placeholder images | 📋 Pending | Commission real editorial photography from British Muslim photographer |
| Solicitor firm outreach | 📋 Awaiting MCB | 24 firms identified, template email ready. MCB to lead outreach. |
| AML partnership | 📋 Awaiting MCB | Contact amlevents@mail.com for member directory sharing |

## Backlog

| Task | Priority | Notes |
|------|----------|-------|
| Wales FST corpus expansion | Medium | Wales-specific PSED regulations not yet in corpus |
| Decision Tree: viability -> tier routing | Medium | Route by viability score to appropriate tier |
| Tier 3: Case summary generation | Medium | From conversation history for MCB referral |
| Tier 3: "Request Legal Review" button | Low | Requires MCB infrastructure |
| Tier 3: Referral Partnerships | Low | Requires partner agreements (Tell MAMA, IRU, AML) |
| Tier 3: Solicitor Referral Service | Low | Send case summary to solicitor with user consent |
| Tier 4: Third Party Reporting Centre | Low | Apply for TPRC status with Police Scotland, Tell MAMA |
| Hub Locator database | Low | PRD defined but not implemented |
| Letter before Action templates | Low | PRD defined but not implemented |
| Vento Calculator | Low | 2026 inflation-adjusted claim estimation |
| Language Support | Low | Urdu, Arabic, Bengali LLM prompts |

---
*Updated: 2026-03-25*
