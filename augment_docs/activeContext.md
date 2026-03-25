# Active Context — Project Ad'l

## Current Sprint Focus

**Major Feature Sprint** (2026-03-25)

21 features implemented across 19+ commits. Git initialisation, CI/CD, viability scoring, evidence checklist, form guides, solicitor directory, analytics, WCAG fixes, corpus expansion, E2E tests, pre-commit hooks, IP-based jurisdiction auto-detection, and Railway deploy fixes.

### Completed this session (2026-03-24) — First batch:
1. ✅ **Git initialisation** — `.gitignore`, initial commit of recovered codebase
2. ✅ **Ruff linting + mypy type checking** — configured in `pyproject.toml`
3. ✅ **Jurisdiction selector UI** — 3 clickable buttons at chat start in Chainlit (England & Wales / Scotland / NI)
4. ✅ **Report generation models** — `ReportType`, `GenerateReportRequest`, `GenerateReportResponse` in models.py
5. ✅ **Report generator module** — `report_generator.py` with prompt builders + section parser
6. ✅ **POST /api/v1/generate-report endpoint** — incident summary + solicitor pack generation
7. ✅ **Image endpoint test coverage** — comprehensive tests for `/api/v1/query/image`
8. ✅ **Final lint pass** — all code passes ruff + mypy

### Completed this session (2026-03-24) — Second batch:
9. ✅ **Structured viability scoring** — parses VIABILITY_ASSESSMENT block from Gemini into `ViabilityAssessment` model (score 0-100, Vento band, statutory_footing, case_law_precedent, quantum_potential)
10. ✅ **Dynamic evidence checklist** — 3-6 tailored items parsed from EVIDENCE_CHECKLIST block when viability requested
11. ✅ **CI/CD** — GitHub repo at `muazamsarfaraz/adil` (private), GitHub Actions for lint+test on PR
12. ✅ **Analytics endpoint** — `GET /api/v1/analytics` with aggregate stats from Postgres
13. ✅ **Request timing middleware** — logs path, method, status, duration_ms
14. ✅ **Secrets audit** — clean, no secrets in git
15. ✅ **Playwright E2E tests** — 4 tests against live site (adil-frontend)
16. ✅ **Smart Form Guides** — `police_uk_guide`, `tell_mama_guide`, `police_scotland_guide` report types
17. ✅ **Solicitor Directory** — `GET /api/v1/solicitors` with 24 firms, filterable by jurisdiction/specialism/location
18. ✅ **FST Corpus expansion** — Scotland Hate Crime Act 2021, FETO 1998, NI Race Relations Order 1997, Scottish case law
19. ✅ **Landing page WCAG 2.2 AA** — 21 a11y fixes + accessibility statement published
20. ✅ **Pre-commit hooks** — ruff lint+format

### Completed this session (2026-03-25):
21. **IP-based jurisdiction auto-detection** — New `geolocation.py` module in adil-rag-api, new `GET /api/v1/detect-jurisdiction` public endpoint (no auth), frontend auto-detects and shows "It looks like you're in X — is that right?" with confirm/change buttons
22. **Railway deploy fix** — `startCommand` added to `adil-report-bridge/railway.toml`. CRITICAL: Never set `RAILWAY_DOCKERFILE_PATH` env vars — they break auto-detection.

### Previous sprint: Image/Screenshot Support (2026-03-08)
- ✅ Image upload support (PNG, JPG, GIF, WebP, max 5 files, 10MB each)
- ✅ Gemini 3 Flash vision — `query_with_images()` in RAG service
- ✅ `POST /api/v1/query/image` endpoint with MIME type and base64 validation
- ✅ Frontend integration — Chainlit `message.elements` handling
- ✅ Deployed to Railway

## Recent Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-24 | GitHub as source of truth | Private repo at `muazamsarfaraz/adil` with GitHub Actions CI/CD for lint+test |
| 2026-03-24 | Pre-commit hooks for code quality | ruff lint+format runs before every commit; catches issues early |
| 2026-03-24 | Structured viability scoring via Gemini | Parse VIABILITY_ASSESSMENT block into typed model rather than free-text; enables programmatic routing |
| 2026-03-24 | Solicitor directory as curated endpoint | `GET /api/v1/solicitors` with 24 firms — filterable by jurisdiction/specialism/location |
| 2026-03-24 | 5 report types in generate-report | incident_summary, solicitor_pack, police_uk_guide, tell_mama_guide, police_scotland_guide |
| 2026-03-24 | WCAG 2.2 AA compliance for landing page | 21 a11y fixes applied + accessibility statement published |
| 2026-03-24 | FST corpus expanded for devolved jurisdictions | Scotland Hate Crime Act 2021, FETO 1998, NI Race Relations Order 1997, Scottish case law |
| 2026-03-25 | IP-based jurisdiction auto-detection | `geolocation.py` + `GET /api/v1/detect-jurisdiction` — auto-detects from IP, frontend shows confirm/change UI |
| 2026-03-25 | NEVER set RAILWAY_DOCKERFILE_PATH env var | Breaks Railway's Dockerfile auto-detection for bridge service |
| 2026-03-07 | Self-service vs solicitor path split | Hate crime reporting = self-service (Tell MAMA, IRU, Police); workplace discrimination = solicitor path (ACAS, ET1). Users should not self-file ET1 claims without legal advice. |
| 2026-03-07 | 4-tier reporting integration strategy | Tier 1: incident summary generator (no partnership needed), Tier 2: smart form guides, Tier 3: referral partnerships (API/email), Tier 4: Third Party Reporting Centre status |
| 2026-02-19 | No LangChain — direct `google-genai` SDK | Gemini FST not supported by LangChain wrappers |
| 2026-02-17 | Custom domain `askadil.org` | Cloudflare -> Railway CNAME |

## Current State

- **Live URL:** ✅ `https://askadil.org` (frontend) / `adil-rag-api-production.up.railway.app` (API)
- **GitHub:** ✅ `muazamsarfaraz/adil` (private) with GitHub Actions CI/CD
- **Git repo:** ✅ Initialised with `.gitignore`
- **Linting:** ✅ Ruff linting + formatting + mypy type checking (pyproject.toml)
- **Pre-commit hooks:** ✅ ruff lint+format
- **Multi-turn memory:** ✅ Backend + frontend complete
- **Suggested questions:** ✅ Backend + frontend complete (Action buttons)
- **Jurisdiction awareness:** ✅ System prompt + UI selector (3 buttons at chat start) + IP-based auto-detection with confirm/change UI
- **Jurisdiction auto-detect:** ✅ `GET /api/v1/detect-jurisdiction` (public, no auth) — `geolocation.py` via ip-api.com
- **Viability scoring:** ✅ Structured `ViabilityAssessment` model (score 0-100, Vento band, statutory_footing, case_law_precedent, quantum_potential)
- **Evidence checklist:** ✅ Dynamic 3-6 tailored items from EVIDENCE_CHECKLIST block
- **Report generation:** ✅ 5 types: incident_summary, solicitor_pack, police_uk_guide, tell_mama_guide, police_scotland_guide
- **Solicitor directory:** ✅ `GET /api/v1/solicitors` — 24 firms, filterable by jurisdiction/specialism/location
- **Analytics:** ✅ `GET /api/v1/analytics` — aggregate stats from Postgres
- **Request timing:** ✅ Middleware logging path, method, status, duration_ms
- **Actionable Next Steps:** ✅ Section 10 in system prompt — full resource directory (24 orgs)
- **Image analysis:** ✅ Gemini 3 Flash multimodal vision (screenshots, document photos)
- **Content extraction:** ✅ Cascade pattern for Facebook, Twitter/X, Instagram, YouTube
- **Security:** ✅ SSRF, input limits, prompt injection, TLS, error leakage, thread-safe stats, secrets audit clean
- **Performance:** ✅ Async Gemini calls, parallel URL processing, persistent httpx client
- **API Security:** ✅ API key auth, rate limiting, tightened CORS
- **Test suite:** ✅ 250+ tests (225+ adil-rag-api, 22 adil-report-bridge, 4 Playwright E2E)
- **FST corpus:** ✅ Expanded with Scotland Hate Crime Act 2021, FETO 1998, NI Race Relations Order 1997, Scottish case law
- **Landing page:** ✅ WCAG 2.2 AA compliant (21 fixes) + accessibility statement
- **Reporting roadmap:** ✅ PRD written (`docs/plans/2026-03-07-reporting-integration-roadmap.md`)
- **Solicitor database:** ✅ Seed database created — outreach pending
- **Chainlit:** ✅ v2.9.6 (CVEs patched)

## Blockers / Risks

- Solicitor database requires outreach and consent before production use.
- Tier 3+ reporting integrations require partnership agreements with organisations.
- Wales-specific PSED regulations not yet in FST corpus.
- Placeholder hero images still need replacement with real editorial photography.
- **CRITICAL Railway deployment caveat:** NEVER set `RAILWAY_DOCKERFILE_PATH` env var on adil-report-bridge — it breaks Railway's Dockerfile auto-detection. If Railway uses Railpack instead of Dockerfile, change builder in Dashboard > Settings > Build.
- Deploy from subdirectory: `cd adil-rag-api && railway up --service adil-rag-api`

## Next Steps (Immediate)

1. **Deploy to Railway** — Push all 2026-03-24 sprint changes to production
2. **Custom domain for landing page** — Point domain (e.g. `landing.askadil.org` or swap as main `askadil.org`) via Cloudflare
3. **Replace placeholder images** — Commission real editorial photography from a British Muslim photographer
4. **MCB outreach:** Contact 8 Muslim-community-focus solicitor firms (template in roadmap PRD)
5. **MCB outreach:** Contact AML (amlevents@mail.com) for member directory partnership
6. **Wales FST corpus** — Expand with Wales-specific PSED regulations
7. **Decision Tree** — viability score -> tier routing (Tier 3 escalation)
8. **Tier 3: Case summary generation** from conversation history for MCB referral

---
*Updated: 2026-03-25*
