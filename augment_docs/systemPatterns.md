# System Patterns — Project Ad'l

## Micro-service Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Railway Platform                              │
│  Environment: production                                              │
│  Project: project-adil (3b3ce312-40a1-4fba-9367-...)                  │
├─────────────────────┬──────────────────────┬─────────────────────────┤
│  Service A:         │  Service B:          │  Service C:               │
│  adil-rag-api       │  adil-frontend       │  adil-landing             │
│  (FastAPI)          │  (Chainlit)          │  (nginx:alpine)           │
│                     │                      │                           │
│  Port: 8080         │  Port: $PORT         │  Port: $PORT              │
│  Python 3.11-slim   │  Python 3.11-slim    │  Static HTML/CSS/JS       │
│                     │                      │                           │
│  Endpoints:         │  Handlers:           │  Serves:                  │
│  GET  /health       │  @cl.on_chat_start   │  index.html               │
│  POST /api/v1/query │  @cl.on_message      │  images/                  │
│  POST /api/v1/analyze  (image uploads)     │  Quick Exit button        │
│  POST /api/v1/query/image                  │                           │
├─────────────────────┴──────────────────────┴─────────────────────────┤
│  External:                                                            │
│  - Gemini API (FST + generative)                                      │
│  - Legislation.gov.uk (URL references)                                │
│  - TNA Case Law (URL references)                                      │
│  - YouTube Transcript API + yt-dlp                                    │
│  - FXTwitter API (Twitter/X)                                          │
│  - yt-dlp (Facebook/Instagram/video)                                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Service A: The Ad'l Engine (`adil-rag-api`)

**Role:** Centralised Legal Intelligence & Data Orchestration.

| Module | File | Responsibility |
|--------|------|----------------|
| **App** | `app.py` (~680 lines) | FastAPI app, lifespan, CORS, endpoints, SSRF protection, async processing |
| **RAG Service** | `rag_service.py` (~900 lines) | Gemini FST queries, citation extraction, UK legislation/case law databases, system prompt (Section 0: Integrity, Section 10: Actionable Next Steps, ~200 lines) |
| **Content Extractor** | `content_extractor.py` (~900 lines) | URL detection, cascade extraction (Facebook, Twitter/X, Instagram, YouTube), yt-dlp, FXTwitter API, OG meta scrape |
| **Models** | `models.py` (~320 lines) | Pydantic v2 models (ConversationTurn, ViabilityAssessment, etc.) |
| **Tests** | `test_backend.py` (~1460 lines) | 125 tests: models, API, extraction, system prompt, RAG service, SSRF, security |

### Key Data Structures (rag_service.py)
- `UK_LEGISLATION_URLS` — 5 acts with base URLs (Equality Act 2010, Public Order Act 1986, Online Safety Act 2023, Crime and Disorder Act 1998, Human Rights Act 1998)
- `LEGISLATION_SNIPPETS` — Key sections for each act
- `UK_CASE_LAW` — 9 landmark cases (Eweida, JH Walker, Azmi, Lee v IFoA [pending], Grainger, Ladele, Chaplin, Redfearn, Vento — duplicate Eweida removed)
- `SYSTEM_INSTRUCTION` — ~200 line system prompt including Section 0: Integrity & Safety (prompt injection defense), Sections 1-9: "Educate First, Litigate Second" with Vento bands, Section 10: Actionable Next Steps with full resource directory

## Service C: The Landing Page (`adil-landing`)

**Role:** Public-facing landing page explaining AskAdil to new visitors.

| Component | Details |
|-----------|---------|
| **Server** | nginx:alpine with `envsubst` for Railway's `$PORT` |
| **Content** | Single `index.html` with embedded CSS/JS (~1300 lines) |
| **Images** | 3 AI-generated hero concepts (placeholder — replace with real photography) |
| **Fonts** | DM Serif Display (display), Source Sans 3 (body), Noto Naskh Arabic (Arabic text) |
| **Palette** | Deep Islamic green (#0D3B1E to #22C55E), gold accent (#D4A843), warm off-white (#FAFAF8) |
| **Safety** | Quick Exit button (red, fixed top-right) — replaces browser history on click |
| **Accessibility** | Skip-to-content link, semantic `<main>`, `lang="en"`, ARIA labels |
| **Animations** | CSS fadeInUp/fadeIn keyframes, IntersectionObserver scroll reveals with staggered delays |
| **Responsive** | Mobile breakpoints at 768px and 480px, `clamp()` for fluid typography |

### Landing Page Sections
1. Fixed header with glassmorphism
2. Full-viewport hero with photo background + green overlay + Islamic geometric SVG pattern
3. Social proof bar (7 Acts, 9 Cases, 18 Organisations, 4 Jurisdictions)
4. "People Like You" story cards (3 scenarios with images)
5. How It Works (3 steps) on dark green background
6. Features (4 cards: Legal Education, Content Analysis, Actionable Next Steps, Find a Solicitor)
7. Two Paths (self-service vs solicitor side-by-side cards)
8. Organisations bar (Tell MAMA, Citizens Advice, ACAS, Law Society, EASS, IRU, Stop Hate UK, Police Scotland)
9. CTA section on dark green background
10. Footer with emergency numbers (999, 101, Stop Hate UK 24/7), legal disclaimer, resource links

### Deployment Pattern
- Dockerfile uses `envsubst` to inject Railway's `$PORT` into nginx config at container start
- `nginx.conf.template` with `${PORT}` placeholder → rendered to `/etc/nginx/conf.d/default.conf`
- Healthcheck on `/` — returns `index.html`
- Security headers: X-Frame-Options, X-Content-Type-Options, Referrer-Policy, X-XSS-Protection
- Static asset caching: 7-day expiry with `Cache-Control: public, immutable`
- Gzip compression for HTML, CSS, JS, SVG

## Service B: The Insight Portal (`adil-frontend`)

**Role:** Conversational User Interface & Mentor.

| Stage | Function |
|-------|----------|
| **Stage 1: Education (Ilm)** | Interactive rights modules via chat |
| **Stage 2: Resolution (Naseehah)** | Guiding user through mediation/internal steps |
| **Stage 3: Litigation (Ad'l)** | For high-viability cases, matching with pro bono / no-win-no-fee partner firm |

### Design Patterns
- **Pedagogical Funnel:** Chat always educates before escalating.
- **Multi-Turn Conversation:** Conversation history stored in `cl.user_session` and sent with every API call. Gemini receives full context as multi-turn `contents` list.
- **Jurisdiction-Aware Sessions:** User's jurisdiction stored in session, prepended to every query for jurisdiction-specific guidance.
- **Suggested Follow-Up Questions:** System prompt instructs AI to include 3 contextual follow-up questions. Parsed server-side and rendered as clickable Chainlit Action buttons.
- **URL Detection → Content Analysis:** URLs in messages trigger `/api/v1/analyze` instead of `/api/v1/query`.
- **Viability Keywords:** Detection of compensation/viability terms triggers assessment display with Vento bands.
- **Citation Extraction:** Regex-based parsing for statutory citations (Section X of Act Y) and case law citations.
- **Source Deduplication:** Max 3 sections per act, statutes before case law, configurable max_sources.
- **Actionable Next Steps:** Every post-intake response includes "What You Can Do Now" with 3-5 relevant organisations, selected by AI based on topic, jurisdiction, and severity (Section 10 of system prompt).

## Multi-Turn Conversation Architecture

```
Frontend (Chainlit)                    Backend (FastAPI)                  Gemini API
┌──────────────────┐                  ┌──────────────────┐              ┌──────────────┐
│ cl.user_session:  │                  │ /api/v1/query    │              │              │
│  conversation_    │  POST /query     │                  │  contents=   │ generate_    │
│  history: [       │  {query,         │  Convert history │  [{role,     │ content()    │
│   {role, content} │   conversation_  │  to Gemini       │    parts}]   │              │
│   ...             │   history}       │  format          │              │              │
│  ]                │ ─────────────►   │ ─────────────►   │ ──────────►  │              │
│                   │                  │                  │              │              │
│ After response:   │  ◄───────────── │  ◄───────────── │  ◄────────── │              │
│  Append user msg  │  {answer,        │  Parse suggested │              │              │
│  + AI response    │   suggested_     │  questions from  │              │              │
│  to history       │   questions}     │  answer text     │              │              │
└──────────────────┘                  └──────────────────┘              └──────────────┘
```

### Conversation History Format

**Frontend → Backend (API):**
```json
{"conversation_history": [
  {"role": "user", "content": "What is the Equality Act?"},
  {"role": "model", "content": "The Equality Act 2010 is..."}
]}
```

**Backend → Gemini (SDK):**
```json
{"contents": [
  {"role": "user", "parts": [{"text": "What is the Equality Act?"}]},
  {"role": "model", "parts": [{"text": "The Equality Act 2010 is..."}]},
  {"role": "user", "parts": [{"text": "Does it apply in Scotland?"}]}
]}
```

## Jurisdiction Session Pattern

```
Chat Start → Jurisdiction Selector (Action buttons)
                    │
                    ▼
        cl.user_session.set("jurisdiction", "scotland")
                    │
                    ▼
        Every query prepended: "[User is in Scotland] {question}"
                    │
                    ▼
        System prompt § 7 adjusts: courts, procedures, legislation
```

## Triage & Escalation Pattern

### The Pedagogical Funnel (Logic Flow)

To satisfy **FR1**, the system architecture acts as a "Gatekeeper":

| Stage | AI Action | Output | Trigger |
|-------|-----------|--------|---------|
| **Intake** | Sentiment & Fact extraction via Gemini Flash. | Incident Summary. | Every query |
| **Triage** | Match against Equality Act 2010 triggers. | **Mandatory:** "Know Your Rights" Pack. | Every query |
| **Intervention** | Generate an internal grievance letter template. | **Mandatory:** "Self-Help" first step. | Viability keywords detected |
| **Escalation** | Evaluate evidence strength (The *Ilm* Threshold). | Escalation Card with solicitor/ACAS links. | Viability score > 30 |

### Escalation Card (Tier 2)

When `litigation_mentioned == true` or viability score exceeds threshold, append a structured card:

```markdown
---
🔔 **This situation may benefit from professional support:**
- 📞 [ACAS Early Conciliation](https://www.acas.org.uk/early-conciliation) — Free, required before ET claim (⚠️ 3-month deadline)
- 🔍 [Find a Solicitor](https://solicitors.lawsociety.org.uk/) — Law Society directory (filter: discrimination)
- 🏛️ [Citizens Advice](https://www.citizensadvice.org.uk/) — Free local advice
- 📧 [Equality Advisory Support Service](https://www.equalityadvisoryservice.com/) — Free helpline
```

### Decision Tree: General Grievance vs Litigation-Ready Case

```
User Query
    │
    ├─ Viability Score 0-30 ──► Tier 1: Education + Self-Help
    │
    ├─ Viability Score 31-60 ──► Tier 2: Escalation Card + Evidence Checklist
    │
    ├─ Viability Score 61-100 ──► Tier 2 (strong) + Flag for Tier 3
    │
    └─ User requests human help ──► Tier 3: MCB Referral (future)
```

### Managed RAG with Gemini FST — Partition Strategy

To prevent hallucinated legal advice, the **Gemini File Search Tool (FST)** should be partitioned:

- **Folder A (Statutory):** Legislation.gov.uk (Equality Act, Online Safety Act).
- **Folder B (Precedent):** Latest Employment Tribunal rulings and EAT (Employment Appeal Tribunal) decisions.
- **Folder C (Guidelines):** Vento bands and ACAS Code of Practice.
- **Folder D (Jurisdiction-Specific):** Scotland-specific legislation (Hate Crime Act 2021), NI-specific orders (FETO 1998), Wales-specific PSED regulations.

> **Note on FR3 (Evidence Verification):** The "Checklist for Success" should be a dynamic document. If a user claims workplace discrimination, the AI should specifically ask for "Timestamped screenshots, witness names, or contract clauses."

## Content Extraction Cascade Pattern

All social media/video platforms now use a consistent multi-step fallback cascade:

```
Facebook:   yt-dlp (metadata + subtitles) -> OG meta scrape -> manual fallback
Twitter/X:  FXTwitter API -> yt-dlp (video tweets) -> manual fallback
Instagram:  OG meta scrape -> yt-dlp (with cookies) -> manual fallback
YouTube:    youtube-transcript-api -> yt-dlp -> manual-paste fallback
            (Shorts/Live URL support added)
```

Each step catches failures and falls through to the next. Shared `_get_yt_dlp_options()` method ensures DRY configuration. Facebook regex narrowed to video-like paths. Content-Type checked before webpage scraping.

## Actionable Next Steps Pattern

System prompt Section 10 instructs the AI to include "What You Can Do Now" with 3-5 relevant organisations after every post-intake response. The AI selects from a full resource directory based on topic, jurisdiction, and severity:

- **Hate crime/online abuse:** Tell MAMA, IRU, True Vision, Stop Hate UK
- **Employment:** ACAS, Employment Tribunal, Citizens Advice
- **General discrimination:** EASS, EHRC, Citizens Advice
- **Legal help:** Law Society, Legal Aid
- **Scotland-specific:** Police Scotland, Law Society of Scotland, SLAB
- **Northern Ireland-specific:** Equality Commission NI, Law Society NI, Advice NI

## Self-Service vs Solicitor Path Pattern

AskAdil routes users to different action paths based on case type:

```
User conversation
    │
    ├─ Hate crime / Islamophobia ──► SELF-SERVICE PATH
    │   Tell MAMA, IRU, Police Scotland, True Vision
    │   AskAdil: generate report summary, guide form completion
    │
    ├─ Online hate speech ──► SELF-SERVICE PATH
    │   Tell MAMA, platform reporting
    │   AskAdil: analyse content, generate report
    │
    ├─ Workplace discrimination ──► SOLICITOR PATH
    │   Solicitor -> ACAS EC -> ET1
    │   AskAdil: educate, generate consultation pack, find solicitor
    │
    ├─ Compensation claims ──► SOLICITOR PATH
    │   Solicitor required
    │   AskAdil: explain Vento bands, generate case summary, find solicitor
    │
    └─ General enquiry ──► SELF-SERVICE PATH
        EASS (phone/email), Citizens Advice
        AskAdil: brief user on what to ask
```

Key principle: AskAdil never encourages users to file ET1 claims or navigate ACAS Early Conciliation without a solicitor. The solicitor path generates a "Solicitor Consultation Pack" with case summary, key dates, relevant legislation, and questions to ask.

## Reporting Integration Tiers

```
Tier 1 (now):      Incident Summary Generator — structured copy-paste text
                    Solicitor Consultation Pack — case summary for appointments
                    No partnership required.

Tier 2 (3-6mo):    Smart Form Guides — step-by-step per-organisation
                    Curated Solicitor Directory — consented firms only
                    No partnership required.

Tier 3 (6-12mo):   Referral Partnerships — API/email submission with consent
                    Tell MAMA, IRU, AML solicitor referrals
                    Requires data sharing agreements.

Tier 4 (12-24mo):  Third Party Reporting Centre status
                    Police Scotland, Tell MAMA TPRC
                    Requires formal MoUs.
```

## Muslim Solicitor Directory Pattern

Seed database: `docs/plans/muslim-solicitors-seed-database.json`

- 24 firms across 4 categories: Muslim-community-focus (8), discrimination specialists (8), Scotland (5), NI (3)
- 2 professional bodies: AML, MLAG
- All firms have `outreach_status` and `consent_to_list` tracking fields
- Only firms with `consent_to_list: true` can appear in production
- Future endpoint: `GET /api/v1/solicitors?jurisdiction=&specialism=&location=`

## No LangChain — Direct SDK Pattern

The project uses `google-genai` SDK directly. Multi-turn conversation is handled by building a `contents` list in `rag_service._build_contents()`. Jurisdiction context is prepended to the query string. Suggested questions are parsed from the AI response text via regex in `app._parse_suggested_questions()`. No orchestration framework needed for this architecture.

## Security Policies

- **Authentication:** API key auth via `X-API-Key` header (using `secrets.compare_digest()` for timing-safe comparison). Graceful degradation to open mode if `ADIL_API_KEY` not set (dev mode only).
- **Rate Limiting:** `slowapi` (wrapping `limits` library) — 30/min for query endpoints, 60/min for general endpoints. Configurable via `RATE_LIMIT_QUERY` and `RATE_LIMIT_GENERAL` env vars.
- **CORS:** Tightened from `*` to specific origins list (`https://askadil.org`, `https://www.askadil.org`, Railway production URL, `localhost:*`). Configurable via `ALLOWED_ORIGINS` env var. Restricted methods (`GET`, `POST`, `OPTIONS`) and headers.
- **SSRF Protection:** All URL fetching rejects private IPs (10.x, 172.16-31.x, 192.168.x, 127.x, ::1), internal networks, and non-HTTP/HTTPS schemes.
- **Input Length Limits:** Query 10K chars, content 50K chars, conversation turn 20K chars, history max 50 items.
- **Prompt Injection Resistance:** Section 0: INTEGRITY & SAFETY in system prompt defends against adversarial inputs attempting to override instructions.
- **TLS Verification:** Re-enabled for yt-dlp (was disabled during development).
- **Error Detail Leakage:** Fixed — generic 500 messages returned to clients, details logged server-side only.
- **Thread-Safe Stats:** `asyncio.Lock()` protects shared statistics counters.
- **No hardcoded secrets.** All API keys via environment variables.
- **Input sanitisation:** Pydantic v2 validation on all request models with comprehensive `Field()` descriptions and `json_schema_extra` examples.
- **Error handling:** All endpoints wrapped in try/except with proper HTTP error responses. Generic messages to clients.
- **No silent failures:** Catch blocks log errors.
- **Swagger UI:** Comprehensive OpenAPI documentation with `persistAuthorization=True`, contact info, license, and tag descriptions.
- **Amanah (Trust):** Sensitive legal data = Special Category Data under UK GDPR. Evidence Vault must use E2E encryption.
- **Solicitor referral disclaimer:** AskAdil does not endorse or guarantee any solicitor. Clear disclaimer required on all referrals.

---
*Updated: 2026-03-07*

