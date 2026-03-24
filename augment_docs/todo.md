# Todo — Project Ad'l (Active Checklist)

## Current Sprint: Major Feature Sprint (2026-03-24)

### Completed (2026-02-19 sprint)
- [x] Multi-turn conversation memory — backend (`models.py`, `rag_service.py`, `app.py`)
- [x] Suggested follow-up questions — system prompt + `_parse_suggested_questions()` parser
- [x] Jurisdiction awareness — system prompt updated (S7)
- [x] `ConversationTurn` model + `conversation_history` field on `QueryRequest` / `AnalyzeContentRequest`
- [x] `suggested_questions` field on `QueryResponse` / `AnalyzeContentResponse`
- [x] `rag_service._build_contents()` — multi-turn Gemini contents builder

### Completed (2026-03-07 sprint)
- [x] Frontend: store conversation history in `cl.user_session` + send with API calls
- [x] Frontend: parse suggested questions + render as Chainlit Action buttons
- [x] Frontend: `@cl.action_callback` handler for suggested question clicks
- [x] Tier 2 escalation / Actionable Next Steps: Section 10 in system prompt with full resource directory
- [x] Content extraction overhaul: Facebook, Twitter/X, Instagram, YouTube cascade patterns
- [x] SSRF protection on all URL fetching
- [x] Input length limits (query 10K, content 50K, turn 20K, history 50 items)
- [x] Prompt injection resistance (Section 0: Integrity & Safety)
- [x] TLS certificate verification re-enabled for yt-dlp
- [x] Error detail leakage fixed (generic 500 messages to clients)
- [x] Thread-safe stats with asyncio.Lock()
- [x] Async Gemini API calls (asyncio.to_thread())
- [x] Parallel URL processing (asyncio.gather(), max 10 URLs)
- [x] Persistent httpx.AsyncClient with connection reuse
- [x] Event loop fix (asyncio.get_running_loop())
- [x] Test suite: 125 tests all passing
- [x] requirements-dev.txt created (pytest, pytest-asyncio, httpx)
- [x] Code quality: duplicate Eweida removed, BAILII URLs fixed, dead code removed, DRY refactors
- [x] Review input validation on all endpoints

### Completed (2026-03-24 sprint)
- [x] Git initialisation with .gitignore
- [x] Ruff linting + mypy type checking (pyproject.toml)
- [x] Jurisdiction selector UI (3 buttons at chat start in Chainlit)
- [x] Report generation models (ReportType, GenerateReportRequest/Response)
- [x] Report generator module (prompt builders + section parser)
- [x] POST /api/v1/generate-report endpoint (incident summary + solicitor pack)
- [x] Image endpoint test coverage
- [x] Final lint pass
- [x] Structured viability scoring — parses VIABILITY_ASSESSMENT block from Gemini into ViabilityAssessment model (score 0-100, Vento band, statutory_footing, case_law_precedent, quantum_potential)
- [x] Dynamic evidence checklist — 3-6 tailored items parsed from EVIDENCE_CHECKLIST block when viability requested
- [x] CI/CD — GitHub repo at muazamsarfaraz/adil (private), GitHub Actions for lint+test
- [x] Analytics endpoint — GET /api/v1/analytics with aggregate stats from Postgres
- [x] Request timing middleware — logs path, method, status, duration_ms
- [x] Secrets audit — clean, no secrets in git
- [x] Playwright E2E tests — 4 tests against live site
- [x] Smart Form Guides — police_uk_guide, tell_mama_guide, police_scotland_guide report types
- [x] Solicitor Directory — GET /api/v1/solicitors with 24 firms, filterable by jurisdiction/specialism/location
- [x] FST Corpus expansion — Scotland Hate Crime Act 2021, FETO 1998, NI Race Relations Order 1997, Scottish case law
- [x] Landing page WCAG 2.2 AA — 21 a11y fixes + accessibility statement
- [x] Pre-commit hooks — ruff lint+format

### Remaining
- [ ] Deploy backend + frontend changes to Railway + verify

## Landing Page (2026-03-07)

- [x] Landing page design + build (`adil-landing/index.html`)
- [x] Hero images generated via `gemini-3-pro-image-preview` (3 concepts)
- [x] Landing page best practices research (7 areas)
- [x] Quick Exit button (safety feature for vulnerable users)
- [x] Accessibility foundations (skip-to-content, semantic HTML, ARIA)
- [x] Deployed `adil-landing` service to Railway (nginx:alpine)
- [x] Railway domain: `adil-landing-production.up.railway.app`
- [ ] Custom domain for landing page (e.g. `landing.askadil.org`)
- [ ] Replace AI-generated images with real editorial photography
- [x] Full WCAG 2.2 AA audit — 21 a11y fixes applied
- [x] Publish accessibility statement page

## Immediate (Infrastructure)

- [x] Recover codebase from Railway deployment
- [x] Verify sync (MD5 checksums, 22/22 files)
- [x] Add `FILE_SEARCH_STORE_ID` + `RAG_API_URL` to `.env`
- [x] Initialise augment_docs/ Memory Bank
- [x] Initialise git repository + `.gitignore`
- [x] Initial commit of recovered codebase

## Quality Gates

- [x] Write unit tests for `rag_service.py` (core logic)
- [x] Write unit tests for `content_extractor.py`
- [x] Write unit tests for `models.py`
- [x] Write integration tests for API endpoints
- [x] Set up Python linting (`ruff check .`)
- [x] Set up Python formatting (`ruff format .`)
- [x] Set up type checking (`mypy .` or `pyright`)
- [x] Write Playwright E2E tests for Chainlit frontend (4 tests)

## Security Hardening

- [x] Tighten CORS (replace `*` with specific origins + `ALLOWED_ORIGINS` env var)
- [x] Add API key authentication (`X-API-Key` header, `secrets.compare_digest()`)
- [x] Add rate limiting to API endpoints (`slowapi`, 30/min query, 60/min general)
- [x] Comprehensive Swagger/OpenAPI documentation with examples
- [x] Frontend sends `X-API-Key` on all backend requests
- [x] Deploy security hardening to Railway (`railway up` + set env vars)
- [x] Custom domain: `askadil.org` (Cloudflare -> Railway CNAME)
- [x] WWW redirect: `www.askadil.org` -> `askadil.org` (301)
- [x] CORS updated for `askadil.org` + `www.askadil.org`
- [x] Chainlit upgraded to v2.9.6 (3 CVEs patched)
- [x] Review input validation on all endpoints
- [x] SSRF protection on all URL fetching
- [x] Prompt injection resistance (Section 0 in system prompt)
- [x] TLS certificate verification re-enabled
- [x] Error detail leakage fixed
- [x] Thread-safe stats
- [x] Audit for exposed secrets in codebase — clean, no secrets in git
- [x] Add request logging / observability — request timing middleware (path, method, status, duration_ms)

## CI/CD

- [x] Link Railway to GitHub for automated deploys — GitHub repo at muazamsarfaraz/adil (private)
- [x] Set up GitHub Actions for lint + test on PR
- [x] Add pre-commit hooks (ruff lint+format)

## Feature Backlog — Jurisdiction (FR4)

- [x] System prompt jurisdiction awareness (S7)
- [x] Jurisdiction selector UI (3 clickable buttons at chat start)
- [x] Jurisdiction stored in session + prepended to every query
- [x] Expand FST corpus: Scotland-specific legislation (Hate Crime Act 2021)
- [x] Expand FST corpus: NI-specific orders (FETO 1998, NI Race Relations Order 1997)
- [ ] Expand FST corpus: Wales-specific PSED regulations

## Feature Backlog — Triage & Escalation (FR5)

- [x] Tier 2 escalation / Actionable Next Steps (Section 10 in system prompt with full resource directory)
- [x] Viability scoring: structured Gemini output -> `ViabilityAssessment` model (score 0-100, Vento band, statutory_footing, case_law_precedent, quantum_potential)
- [x] Evidence Checklist generator (dynamic, 3-6 tailored items parsed from EVIDENCE_CHECKLIST block)
- [ ] Decision Tree: viability score -> tier routing
- [ ] Tier 3: "Request Legal Review" button -> MCB referral (requires MCB infrastructure)
- [ ] Tier 3: Case summary generation from conversation history
- [ ] Lawyer Matchmaker: Pro bono / no-win-no-fee partner matching

## Feature Backlog — Reporting Integration (Roadmap PRD)

See `docs/plans/2026-03-07-reporting-integration-roadmap.md` for full details.

### Tier 1 (No Partnership Required)
- [x] Incident Summary Generator endpoint (`POST /api/v1/generate-report`) — self-service path
- [x] Solicitor Consultation Pack generator — solicitor path (case summary, key dates, legislation, questions)
- [x] Add Muslim solicitor directory links to system prompt resource directory

### Tier 2 (No Partnership Required)
- [x] Smart Form Guides: Police Scotland hate crime form (police_scotland_guide report type)
- [x] Smart Form Guides: Tell MAMA report form (tell_mama_guide report type)
- [x] Smart Form Guides: Police UK guide (police_uk_guide report type)
- [x] Curated Solicitor Directory endpoint (`GET /api/v1/solicitors`) — 24 firms, filterable by jurisdiction/specialism/location

### Tier 3 (Requires Partnerships)
- [ ] Tell MAMA referral integration (API or structured email)
- [ ] IRU referral integration (API or structured email)
- [ ] AML solicitor referral service (case summary -> solicitor with consent)

### Tier 4 (Requires Formal MoUs)
- [ ] Apply for TPRC status with Police Scotland
- [ ] Apply for TPRC status with Tell MAMA
- [ ] ACAS digital gateway (if API becomes available)

### Outreach (MCB-Led)
- [ ] Contact 8 Muslim-community-focus solicitor firms (template in roadmap PRD)
- [ ] Contact AML (amlevents@mail.com) for member directory partnership
- [ ] Contact MLAG at Inner Temple for barrister referral partnership
- [ ] Contact Tell MAMA re: digital Third Party Reporting Centre
- [ ] Contact IRU re: referral source and structured submission

## Feature Backlog — Other (PRD)

- [ ] Tier 2: Advocacy referral system
- [ ] Tier 2: Mediation support / Shura guidance
- [ ] Tier 3: Hub Locator (mosque/community centre database)
- [ ] Tier 3: Safe Space Chat booking system
- [ ] Resolution Library: "Letter before Action" templates
- [ ] Resolution Library: Internal grievance guides

## Recommended Enhancements (Strategic Analysis)

- [ ] Privacy / Amanah: E2E encryption for Evidence Vault (UK GDPR Special Category Data)
- [ ] Vento Calculator: Micro-feature for 2026 inflation-adjusted claim estimation
- [ ] Language Support: Urdu, Arabic, Bengali LLM prompts for Tier 1 info-packets
- [ ] FST Partition Strategy: Folder A (Statutory), Folder B (Precedent), Folder C (Guidelines), Folder D (Jurisdiction-Specific)

---
*Updated: 2026-03-24*
