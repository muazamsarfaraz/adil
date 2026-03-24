# Active Context — Project Ad'l

## Current Sprint Focus

**Image/Screenshot Support** (2026-03-08)

Added multimodal image upload support using Gemini 3 Flash for evidence analysis and document photo processing.

### Completed this session (2026-03-08):
1. ✅ **Image upload support** — Users can upload screenshots/photos (PNG, JPG, GIF, WebP, max 5 files, 10MB each) for legal analysis
2. ✅ **Gemini 3 Flash vision** — `query_with_images()` in RAG service using `Part.from_bytes()` with same legal system prompt and FST
3. ✅ **New endpoint** — `POST /api/v1/query/image` with MIME type and base64 validation
4. ✅ **Frontend integration** — Chainlit `message.elements` handling, base64 encoding, size/type validation
5. ✅ **Deployed to Railway** — Both `adil-rag-api` and `adil-frontend` redeployed with `GEMINI_MODEL_VISION` env var set

### Previous sprint: Landing Page & Deployment (2026-03-07)

### Completed that session:
1. ✅ **Landing page built** — Full production HTML/CSS/JS at `adil-landing/index.html` with editorial warmth aesthetic (DM Serif Display + Source Sans 3, deep green + gold palette)
2. ✅ **Hero images generated** — 3 photorealistic concepts via Gemini (workplace, community, phone) used as placeholders
3. ✅ **Landing page research** — 7-area research report on best practices for social impact legal-tech landing pages
4. ✅ **Quick Exit button** — Safety feature for vulnerable users (replaces browser history on exit)
5. ✅ **Accessibility foundations** — Skip-to-content link, semantic `<main>`, warm backgrounds, ARIA labels
6. ✅ **Deployed to Railway** — New `adil-landing` service (nginx:alpine), live at `adil-landing-production.up.railway.app`

### Previously completed (2026-03-07):
7. ✅ **Reporting Integration Roadmap PRD** — 4-tier phased approach to integrating with UK reporting portals
8. ✅ **Self-service vs Solicitor path split** — Hate crime = self-service; workplace discrimination = solicitor path
9. ✅ **Muslim Solicitor Seed Database** — 24 firms + 2 professional bodies researched
10. ✅ **Portal field research** — Form field analysis for IRU, Tell MAMA, Police Scotland, Met Police, ACAS, ET1, EASS, EHRC
11. ✅ **Outreach plan** — Template email for MCB to contact solicitor firms

### Previously completed (2026-03-07):
6. ✅ **Actionable Next Steps** — Section 10 in system prompt with full resource directory
7. ✅ **Content extraction overhaul** — Facebook, Twitter/X, Instagram, YouTube cascade patterns
8. ✅ **Security hardening** — SSRF, input limits, prompt injection defense, TLS, error leakage, thread-safe stats
9. ✅ **Test suite** — 125 tests all passing
10. 📋 **Jurisdiction selector UI** — Planned: clickable buttons at chat start

## Recent Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-07 | Self-service vs solicitor path split | Hate crime reporting = self-service (Tell MAMA, IRU, Police); workplace discrimination = solicitor path (ACAS, ET1). Users should not self-file ET1 claims without legal advice. |
| 2026-03-07 | Muslim Solicitor seed database (outreach-first) | 24 firms researched but NOT listed in production. All must be contacted for consent before listing. Stored in `docs/plans/muslim-solicitors-seed-database.json`. |
| 2026-03-07 | 4-tier reporting integration strategy | Tier 1: incident summary generator (no partnership needed), Tier 2: smart form guides, Tier 3: referral partnerships (API/email), Tier 4: Third Party Reporting Centre status |
| 2026-03-07 | AML as key partnership target | Association of Muslim Lawyers could provide verified solicitor directory by specialism and region |
| 2026-03-07 | Actionable Next Steps (Section 10 in system prompt) | Every post-intake response includes "What You Can Do Now" with relevant organisations |
| 2026-03-07 | Content extraction cascade pattern | Consistent multi-step fallback for all platforms |
| 2026-03-07 | SSRF protection on all URL fetching | Rejects private IPs, internal networks, non-HTTP schemes |
| 2026-03-07 | 125-test suite with requirements-dev.txt | pytest + pytest-asyncio + httpx; covers models, API, extraction, security, RAG |
| 2026-02-19 | No LangChain — direct `google-genai` SDK | Gemini FST not supported by LangChain wrappers |
| 2026-02-19 | 3-tier triage architecture defined | Tier 1 (self-help, current), Tier 2 (escalation cards, done), Tier 3 (MCB referral, future) |
| 2026-02-17 | Custom domain `askadil.org` | Cloudflare -> Railway CNAME |

## Current State

- **Live URL:** ✅ `https://askadil.org` (custom domain on Cloudflare -> Railway)
- **Multi-turn memory:** ✅ Backend + frontend complete
- **Suggested questions:** ✅ Backend + frontend complete (Action buttons)
- **Jurisdiction awareness:** ✅ System prompt updated — UI selector not yet built
- **Actionable Next Steps:** ✅ Section 10 in system prompt — full resource directory
- **Image analysis:** ✅ Gemini 3 Flash multimodal vision (screenshots, document photos)
- **Content extraction:** ✅ Cascade pattern for Facebook, Twitter/X, Instagram, YouTube
- **Security:** ✅ SSRF, input limits, prompt injection, TLS, error leakage, thread-safe stats
- **Performance:** ✅ Async Gemini calls, parallel URL processing, persistent httpx client
- **API Security:** ✅ API key auth, rate limiting, tightened CORS
- **Test suite:** ✅ 125 tests passing (pytest)
- **Reporting roadmap:** ✅ PRD written (`docs/plans/2026-03-07-reporting-integration-roadmap.md`)
- **Solicitor database:** ✅ Seed database created (`docs/plans/muslim-solicitors-seed-database.json`) — outreach pending
- **Landing page:** ✅ Deployed to Railway (`adil-landing-production.up.railway.app`) — nginx:alpine, editorial warmth design, quick exit button
- **Chainlit:** ✅ v2.9.6 (CVEs patched)
- **Git repo:** ❌ Not initialised yet
- **Linting:** ❌ No linting configured

## Blockers / Risks

- No version control — local changes are untracked.
- Gemini FST corpus is primarily England & Wales — Scotland/NI-specific case law gaps.
- Solicitor database requires outreach and consent before production use.
- Tier 3+ reporting integrations require partnership agreements with organisations.
- No linting or type checking configured yet.

## Next Steps (Immediate)

1. **Custom domain for landing page** — Point domain (e.g. `landing.askadil.org` or swap as main `askadil.org`) via Cloudflare
2. **Replace placeholder images** — Commission real editorial photography from a British Muslim photographer
3. **MCB outreach:** Contact 8 Muslim-community-focus solicitor firms (template in roadmap PRD)
4. **MCB outreach:** Contact AML (amlevents@mail.com) for member directory partnership
5. Build jurisdiction selector UI (clickable buttons at chat start)
6. Implement Tier 1: Incident Summary Generator + Solicitor Consultation Pack endpoints
7. Initialise git repo + first commit
8. Set up linting (ruff) and type checking (mypy)

---
*Updated: 2026-03-08*
