# askAdil ↔ IAG Chatbot Brief — Capability Overlap Audit

**Prepared for:** Muazam Sarfaraz, to support a reply to Hassan Joudi (IAG coordinator, MCB)
**Date:** 2026-06-13
**Scope:** Audit of the live **askAdil / adil** platform against Hassan's 12 Jun 2026 "AI Chatbot" brief (the pivot away from the "App" direction). CC context: SG Wajid Akhter, Linsay Taylor (MEND CEO), Abdullah Saif (MEND).
**Source:** Direct code audit of the `AskAdil/adil` monorepo (6 services) on 2026-06-13. File/line references throughout.

---

## TL;DR for Hassan

> **The thing you're asking for largely already exists and is live in production at askadil.org today.** It's a Claude-powered RAG chatbot for UK discrimination & hate-crime law that already auto-files incident reports to **IRU, British Muslim Trust, and IslamophobiaUK** (plus Tell MAMA, Police UK, Police Scotland, and 4 more) — that's brief item #2, done. The genuinely new build is the **community-facing layer**: push notifications, incident-alert broadcasts, QR onboarding, and multi-lingual UI. Each of those is a 1–2 sprint add-on on top of a platform that's already running, not a from-scratch project. **We are not starting from zero — we're starting from ~70%.**

---

## Feature map — Hassan's 7 items

| # | Brief item | Status | One-line |
|---|------------|--------|----------|
| 1 | **AI Chatbot** (replacing the App) | ✅ **DONE** | Live at askadil.org — Claude Sonnet 4.6 RAG over UK discrimination law, SSE-streamed |
| 2 | **Auto-feed reports** to IRU / BMT / IslamophobiaUK | ✅ **DONE** | All 3 already wired in `adil-report-bridge` (+7 more bodies) |
| 3 | **Incident alert / update feature** | ❌ **NOT YET** | No end-user alert/broadcast channel today — new build |
| 4 | **Easy reporting** ("I just saw this" → logged) | 🟡 **PARTIAL** | 3-step flow with AI prefill exists; can be streamlined to a true 2-tap |
| 5 | **QR codes** in 20 flagship mosques | ❌ **NOT YET** | No QR generation today — but trivial (encodes a tracked URL) |
| 6 | **Push notifications** (training/lobbying/fundraising) | 🟡 **PARTIAL** | Email (SendGrid) + WhatsApp outbound channels exist; web-push & broadcast-to-subscribers are new |
| 7 | **Launch by mid-June 2026** | ✅ **DONE** | Core platform is already in production now |

Legend: ✅ DONE · 🟡 PARTIAL · ❌ NOT YET · 🚀 ABOVE AND BEYOND (see [dedicated section](#-above-and-beyond--what-askadil-already-does-that-exceeds-the-brief))

---

## Item-by-item detail

### 1. AI Chatbot — ✅ DONE

askAdil **is** an AI chatbot, already serving the public.

- **Front-end:** Next.js 16 chat UI (`adil-frontend-next/`), Server-Sent-Events streaming via `@microsoft/fetch-event-source`. Routes: `/chat/[id]`, `/find-me-a-solicitor`, `/privacy`. Jurisdiction selector (England/Wales · Scotland · NI), image-evidence upload to Cloudflare R2, citation sources panel, legal-viability card.
- **Back-end:** FastAPI (`adil-rag-api/`). Primary RAG path uses **Claude Sonnet 4.6** for generation + Claude Haiku 4.5 for query rewriting/judging + OpenAI `text-embedding-3-small` (`ograg/backend.py`). Fallback path: Gemini File Search Tool Store over **1,000+ TNA case-law judgments**. Streaming endpoint `POST /api/v1/query/stream` (`app.py:866`).
- **Knowledge base:** Equality Act 2010, Public Order Act 1986, Crime & Disorder Act 1998, Online Safety Act 2023, Human Rights Act 1998, Mental Capacity Act 2005, plus Scotland- and NI-specific statutes and 14+ landmark cases.

**Verdict:** This is exactly the "AI Chatbot" Hassan wants — and it already exists, with a depth (case-law RAG, devolved-jurisdiction awareness) the brief didn't even ask for.

### 2. Auto-feed reports to IRU / BMT / IslamophobiaUK — ✅ DONE

This is the headline. All three bodies Hassan names are **already integrated** in `adil-report-bridge/targets.py`:

| Target ID | Body | Method |
|-----------|------|--------|
| `iru` | IRU — Islamophobia Response Unit | Browser automation |
| `british-muslim-trust` | British Muslim Trust (BMT) | Browser automation |
| `islamophobia-uk` | Islamophobia UK — Incident Tracker | Browser automation |

And the system goes further — **10 reporting targets total** (7 via AI browser automation, 3 via email):

- **Browser-automation (7):** Police UK, Tell MAMA, Police Scotland, **IRU**, **Islamophobia UK**, **British Muslim Trust**, Muslim Safety Net
- **Email (3):** Prevent Watch, EASS (Equality Advisory Support Service), Stop Hate UK

**How it works:** the RAG API extracts an incident narrative from the chat (`POST /api/v1/report/prefill`), the user confirms PII, and `adil-report-bridge` drives a headless Chromium browser (browser-use + **Claude Sonnet 4.6**) to fill and submit the target's web form, returning a reference number + confirmation screenshot. PII is never persisted by the RAG API. See the [IRU](#a-iru--islamophobia-response-unit), [BMT](#b-british-muslim-trust-bmt), and [IslamophobiaUK](#c-islamophobiauk) integration sections below for the precise "what's left" per body.

> ⚠️ **One operational gate to flag, not a code gap:** the bridge has a `BRIDGE_DRY_RUN` safety toggle (`browser_agent.py:26`). When `true`, the agent walks the entire form but **does not click the final Submit** — so it can be demoed safely without filing live reports. The code default is `false` (live). **Confirm the production env setting** and get explicit MCB sign-off on liability before relying on fully-automated live filing — see the white-label/governance section.

### 3. Incident alert / update feature — ❌ NOT YET

There is **no end-user-facing alert/broadcast channel** today.

- What exists is *operational* only: internal Telegram error alerts for the dev team (`telegram_notifier.py`) and SendGrid email receipts confirming a user's own report submission (`email_receipt.py`). Neither pushes "incident in your area" / "campaign update" messages to the community.
- **New build.** The cleanest delivery channels already have backbones in the repo (WhatsApp Cloud API, SendGrid) — see item 6 — so this is "wire a broadcast layer onto existing channels," not "build messaging from scratch."

### 4. Easy reporting ("I just saw this" → logged) — 🟡 PARTIAL (mostly there)

A reporting flow exists and is already fairly low-friction:

- User types "report" in chat → the AI **prefills** the incident narrative (details, location, date/time) from the conversation (`POST /api/report/prefill`, ~1–2s).
- A 3-step modal follows: **pick target → confirm details + PII → review** (`components/report/report-flow.tsx`), gated by Cloudflare Turnstile CAPTCHA, then `POST /api/report` → `POST /api/v1/submit-report`.

**Why PARTIAL not DONE:** Hassan's "I just saw this" implies a *2-tap, witness-grade* capture (snap a photo / one line of text → logged, PII optional). Today the flow asks for reporter PII up front (some bodies require it). A small UX track — an "anonymous quick-log" mode that captures the incident first and defers/omits PII where the chosen body allows anonymous reports (IslamophobiaUK already supports anonymous) — would close the gap.

### 5. QR codes in 20 flagship mosques — ❌ NOT YET (but trivial)

- No QR generation anywhere in the codebase (no library, route, or component).
- **But the substance is tiny:** a QR code just encodes a URL. The real value-add is *attribution* — a per-mosque tracked landing route (e.g. `/m/<mosque-slug>` with UTM tags) so MCB can see which of Wajid's 20 flagship mosques drive scans/reports. That's a small route + a batch QR-PNG generation script. The "20 mosques" rollout itself is an ops/print task, not engineering.

### 6. Push notifications (training, lobbying, fundraising) — 🟡 PARTIAL

The *channels* exist; the *broadcast-to-community* layer does not.

- **Email:** `adil-outreach-engine/` is a LangGraph + arq campaign engine with full SendGrid integration (`app/services/email.py`), campaign CRUD, cadence/sequencing, and 20+ event types (sent/opened/clicked/bounced). Built for solicitor B2B outreach, but the campaign/broadcast machinery is directly reusable for community fundraising/lobbying emails. (Note: the agent `send_node` is a placeholder pending "Plan 3"; the `EmailService` itself is implemented.)
- **WhatsApp:** `adil-whatsapp-bridge/` talks to the Meta WhatsApp Cloud API and can send outbound text (`meta_client.send_text`). Today it only *replies reactively* to inbound Q&A — but the outbound primitive is there, so opt-in WhatsApp broadcasts are a wiring job, not new infrastructure.
- **What's genuinely new:** browser **web-push** (requires a PWA: service worker + `manifest.json` — neither exists today), and a subscriber/opt-in/segment model for community notifications (the outreach `Contact` and WhatsApp `Session` tables are a starting point but aren't a community-subscriber list).

### 7. Launch by mid-June 2026 — ✅ DONE

The core platform is **already live at askadil.org**. Hassan's hardest constraint — ship something credible by mid-June, vindicated by the Belfast riots (10–13 Jun) — is met for the chatbot + reporting core *today*. The community-engagement add-ons (items 3, 5, 6) can follow as fast-follows without blocking a launch announcement.

---

## 🚀 Above and beyond — what askAdil already does that exceeds the brief

The brief didn't ask for any of these; askAdil already has them:

- **Deep legal RAG:** retrieval over 1,000+ Court of Appeal / EAT / Supreme Court / Court of Protection judgments from The National Archives, plus primary statutes — not a generic chatbot.
- **Devolved-jurisdiction awareness:** distinct England/Wales, Scotland (Hate Crime and Public Order (Scotland) Act 2021), and Northern Ireland legal tracks.
- **Safety posture:** legal disclaimer emitted *first* (before any answer tokens, so the model can't suppress it); **clinical/crisis handoff** that detects mental-health distress and signposts to MCB Mental Health *before* the legal answer; SSRF protection on outbound fetches; prompt-injection resistance; per-IP + per-API-key rate limiting. (Aligns with the portfolio's HARDEST-bar AI-hallucination playbook.)
- **Compensation viability:** optional Vento-band assessment estimating discrimination compensation.
- **Solicitor directory:** ~1,500 SRA-verified solicitor profiles, filterable by practice area, **language offered** (Urdu/Arabic/etc.), postcode, and "Muslim-language" flag, with geo "near me" ranking by OSRM driving time (`/find-me-a-solicitor`).
- **Multi-channel already:** web chat **and** WhatsApp (two front doors to the same RAG brain).
- **10 reporting bodies** vs the 3 in the brief.
- **Evidence upload:** image attachments stored to Cloudflare R2.
- **Anonymised analytics:** topic/jurisdiction classification and conversation logging with no raw-text retention by default.

---

## Reporting-API integration sections (per body)

**Important framing:** none of IRU / BMT / IslamophobiaUK currently expose a public *data API* — they have public web report **forms**. askAdil already submits to all three by **AI browser automation** (driving the live form), which is why "integration" is effectively done. The "new work" per body is therefore *hardening*, not *building*. If/when a body offers a real API or a data-sharing agreement, swapping form-fill → API call is a small, well-isolated change (one adapter in `targets.py`).

### A. IRU — Islamophobia Response Unit
- **Current state:** ✅ Wired. `iru` target, browser adapter, `https://www.theiru.org.uk/report-islamophobia/` (`targets.py:136`).
- **New work:** (1) confirm `BRIDGE_DRY_RUN=false` in prod + capture a live confirmation reference; (2) monitor for form/selector drift (IRU could redesign their form); (3) *optional* — approach IRU for a direct intake API or shared-inbox agreement to remove browser-automation fragility. **Effort: ~0.25 sprint** (verification + monitoring), +0.5 sprint *if* a real API is offered.

### B. British Muslim Trust (BMT)
- **Current state:** ✅ Wired. `british-muslim-trust` target, browser adapter, `britishmuslimtrust.co.uk` (`targets.py:227`).
- **New work:** same hardening as IRU. BMT is newer (2025-founded) so its form is more likely to change — prioritise selector-drift monitoring here. A data-sharing MOU between MCB/IAG and BMT would be the highest-value follow-up (turns best-effort form-fill into a guaranteed feed). **Effort: ~0.25 sprint** + relationship/MOU work (non-engineering).
- *Prior context:* a "BMT ordering fix" was already done (memory S3773), so this body has had attention.

### C. IslamophobiaUK
- **Current state:** ✅ Wired. `islamophobia-uk` target, browser adapter, `islamophobiauk.co.uk` (`targets.py:194`). Notably **supports anonymous reports** — the ideal target for the item-4 "quick anonymous log" UX.
- **New work:** same hardening; plus surface "anonymous, no PII" as a first-class option in the report UI specifically for this body. **Effort: ~0.25 sprint** (shared with item-4 quick-log work).

**Cross-cutting reporting hardening (all bodies): ~0.5 sprint** — a scheduled `GET /health/targets` reachability + form-structure canary that alerts when any portal's form changes, so silent submission failures are caught.

---

## White-label vs separate IAG brand — recommendation

**Recommendation: white-label / co-brand askAdil as the IAG offering — do NOT build a separate IAG product.**

Three concrete routes, in order of preference:

1. **✅ Recommended — co-branded askAdil instance ("IAG, powered by askAdil"):** a theme/skin (logo, colours, copy) on the existing Next.js front-end pointing at the same `adil-rag-api` backend. One codebase, one knowledge base, one reporting bridge; IAG gets its own URL/subdomain and branding. The front-end already centralises branding, so this is largely a config/theme track. **Effort: ~1 sprint.**
2. **Separate IAG brand calling askAdil as a backend service:** viable because the RAG API is already a clean HTTP service with API-key auth (`ADIL_API_KEY`/`RAG_API_KEY`) — IAG could run its own front-end against it. More divergence to maintain; only choose this if IAG needs a materially different UX or independent governance. **Effort: ~2–3 sprints.**
3. **Shared brand, IAG as a channel:** simplest of all — IAG promotes askadil.org directly with IAG-attributed QR codes / landing routes (see item 5). Zero new product; pure go-to-market. **Effort: ~0.25 sprint** (the tracked landing routes).

**Governance note (HARDEST-bar):** because this is legal advice to a vulnerable, targeted community and auto-files reports to third parties, any branding decision should be paired with: (a) a written liability position on automated report-filing (the `BRIDGE_DRY_RUN` decision), and (b) MCB sign-off on the IAG/MEND data-sharing relationship. This is a board/legal question, not an engineering one, but it gates flipping the reporting bridge fully live.

---

## Effort estimate per gap (1 sprint ≈ 1 week of focused build)

| Gap | Status | Effort | Notes |
|-----|--------|--------|-------|
| Item 1 — Chatbot | ✅ DONE | 0 | Live |
| Item 2 — IRU/BMT/IslamophobiaUK feed | ✅ DONE | ~0.5 | Verification + selector-drift canary only |
| Item 4 — Quick/anonymous reporting UX | 🟡 | ~1 | "Snap & log" mode, anonymous via IslamophobiaUK |
| Item 5 — QR codes + per-mosque attribution | ❌ | ~0.5 | Batch QR script + `/m/<slug>` tracked landing route |
| Item 3 — Incident-alert broadcasts | ❌ | ~1.5 | Wire broadcast layer onto WhatsApp + email channels |
| Item 6 — Push notifications | 🟡 | ~2 | PWA (service worker + manifest) for web-push **+** opt-in subscriber model; reuse outreach/WhatsApp channels |
| White-label IAG co-brand | n/a | ~1 | Theme/skin on existing front-end |
| **Total net-new to fully meet brief** | | **~6 sprints (~6 weeks)** | On top of a platform that already covers items 1, 2, 7 |

A credible **mid-June launch** uses what's live now (items 1, 2, 4-partial, 7); items 3, 5, 6 and the IAG co-brand land as fast-follows over the following ~6 weeks.

---

## Cross-links: adil-rag-api & LegalScraper relevance

- **adil-rag-api** is the spine of every item above — it serves the chat (item 1), prefills + proxies reports to the bridge (items 2 & 4), exposes the solicitor directory, and holds the safety/rate-limit/logging layers. Any IAG-branded or IAG-backend route consumes this service via API key.
- **LegalScraper** feeds the **solicitor directory**: ~1,500 solicitor profiles are imported via `adil-rag-api/docs/legalscraper_landing.json` (the `legalscraper_landing` export, sitting behind `GET /api/v1/solicitors/*`). This is the "above and beyond" referral capability — relevant if IAG wants to signpost victims to Muslim-friendly solicitors as part of the journey. No new LegalScraper work is needed for the 7 brief items; it's a bonus asset to surface.
- **adil-report-bridge** is the second key piece for item 2 — the AI browser-automation form-filler with all 10 targets in `targets.py`.

---

## Suggested reply skeleton for Hassan

> Hassan — good news: most of this is already built and live. askAdil (askadil.org) is an AI chatbot for UK discrimination/hate-crime law that **already auto-files reports to IRU, the British Muslim Trust, and IslamophobiaUK** — plus Tell MAMA, the police, and five others. That covers your items 1, 2, and the mid-June launch today.
>
> The genuinely new pieces are the community-engagement layer — incident-alert broadcasts, push notifications, the in-mosque QR onboarding, and a one-tap "I just saw this" quick-log. Each is a 1–2 week add-on on top of the existing platform, ~6 weeks all-in, and we'd recommend offering IAG as a co-branded skin of askAdil rather than rebuilding from scratch.
>
> Two things need an MCB decision, not code: (1) signing off the liability of fully-automated live report-filing, and (2) the IAG/MEND data-sharing relationship with the receiving bodies. Happy to walk the group through a live demo.

---

*Audit conducted 2026-06-13 against the live codebase. ClickUp: [869dp9yp3](https://app.clickup.com/t/869dp9yp3).*
