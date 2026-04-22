# AskAdil Frontend Next.js Rewrite — Design

**Date:** 2026-04-22
**Status:** Draft (post-Gemini review, pre-implementation)
**Scope:** Replace Chainlit UI (`adil-frontend`) with a modern Next.js chat UI adapted from `ai-shamela/frontend`. Backend changes (new streaming endpoint + rate limiting on `adil-rag-api`) are tracked separately in Spec 1.

## Purpose

Replace the existing Chainlit chat interface at `askadil.org` with a Next.js 16 + React 19 application, forking and adapting `E:\dev\mcbx\ai-shamela\frontend`. Maintain full feature parity with the current Chainlit app while delivering a streaming-chat experience, MCB branding, and the v2 path to conversation persistence.

## Constraints

- **Full feature parity (Q1 = A):** jurisdiction selector, suggested questions, image upload, URL extraction, hate-crime report flow, viability scoring, solicitor directory, anonymised logging, multi-turn memory.
- **Streaming responses (Q2 = A):** depends on Spec 1 (new backend `POST /api/v1/query/stream`). Frontend falls back to the existing non-streaming `/api/v1/query` if Spec 1 slips.
- **Deployment C (Q3 = C):** new Railway service at `next.askadil.org` preview subdomain; DNS cutover after stakeholder sign-off.
- **Branding A (Q4 = A):** copy shamela's structure and components, re-skin for AskAdil (MCB green `#14532D`, scales iconography).
- **Entry flow C (Q5 = C):** chat-first — land on `/chat/<new-uuid>`, jurisdiction picker appears as the opening assistant message.
- **Report flow B + final modal (Q6):** inline conversational collection, final review/consent step as a modal. Report state is separate from chat state (no PII in LLM context).
- **Persistence:** v1 is session-only; localStorage-backed saved conversations is v2.
- **Postgres-first:** rate-limit counters, upload metadata, and any future caching live in Postgres. Redis is retained only for arq worker queues (outreach + document-uploader).
- **Storage:** image bytes live on a Railway persistent volume (not S3). Metadata in Postgres, files on disk.

## Architecture

### Services

- **New Next.js service** at `adil-frontend-next/` — Railway service `adil-frontend-next`, domain `next.askadil.org`, cutover to `askadil.org` after sign-off.
- **Chainlit service** (`adil-frontend`) stays live during preview, slept (kept for rollback) post-cutover, deleted after 30 days.

### Next.js architecture (client + server split, stateless proxy)

Chat is a **Client Component** (`"use client"`), but secrets (`RAG_API_KEY`) must stay server-side. We use a **thin stateless proxy**:

```
Browser (Client Component)
       │ fetch, SSE
       ▼
Next.js Route Handlers (server — stateless, no DB)
       │ 1. Zod-validate payload
       │ 2. Extract real client IP from x-forwarded-for
       │ 3. Attach X-API-Key + X-AskAdil-Client-IP
       ▼
adil-rag-api
       │ rate-limit (Postgres), validate client IP header,
       │ enforce SSRF filter on URL extraction,
       │ write upload metadata, process LLM calls
       ▼
(Postgres + Gemini)
```

**The Next.js service is entirely DB-free and stateless.** It holds no `DATABASE_URL`, no rate-limit logic, no upload metadata writes. Its only jobs are: render UI, proxy to backend with the API key attached, and hold image bytes on the Railway volume temporarily.

**Rate limiting lives on the backend** (`adil-rag-api`). To prevent all traffic bucketing under Next.js's single container IP, every proxy request includes an `X-AskAdil-Client-IP` header derived from `x-forwarded-for`. The backend only trusts this header when the request carries a valid `X-API-Key` (i.e. from our frontend).

**All traffic to `adil-rag-api` passes through our own route handlers.** The browser never sees `RAG_API_KEY`.

### Tech stack

| Concern | Library |
|---------|---------|
| Framework | Next.js 16.2.3 (app router) |
| Runtime | React 19.2.4 |
| Language | TypeScript (strict) |
| Styling | Tailwind CSS v4 + `@tailwindcss/typography` |
| Markdown | `react-markdown` + `remark-gfm` + **`rehype-sanitize`** |
| Streaming | `@microsoft/fetch-event-source` (POST + SSE; browser `EventSource` is GET-only) |
| Validation | `zod` (all route handler input) |
| Testing | Playwright + MSW for SSE mocks |
| Container | Multi-stage Dockerfile, `output: 'standalone'` |
| Deploy | Railway with `railway.toml` (`builder = "DOCKERFILE"`) |

### Components inherited from shamela (adapt)

- `components/chat/message.tsx` (markdown + citation buttons `[1]`)
- `components/chat/source-card.tsx` / `sources-panel.tsx`
- `components/chat/searching-indicator.tsx`
- Chat URL pattern `/chat/[id]`

### Components new to AskAdil

- `components/jurisdiction-selector.tsx` — 3-button row. State stored in a **cookie** (not localStorage), so SSR can render the correct initial UI and there is no hydration mismatch.
- `components/chat/viability-card.tsx` — 0-100 score, Vento band, statutory footing ✓, case-law precedent ✓, quantum potential, evidence checklist.
- `components/report/report-flow.tsx` — state machine; collected PII lives in a **separate React state object** and is never appended to `messages[]` or `conversation_history`.
- `components/report/report-target-picker.tsx` — 8-button picker (BMT first).
- `components/report/report-modal.tsx` — final review: structured summary + consent checkbox + Submit/Cancel. Sends payload to `/api/report` (not via chat).
- `components/image-upload.tsx` — drag-and-drop, up to 5 × 10MB. Uploads directly to `/api/upload` which writes to Railway volume.
- `components/url-preview.tsx` — inline preview. URL is sent to `/api/extract-url` (no client-side fetching of user URLs).
- `components/error-boundary.tsx` — React error boundary wrapping `MessageList` to contain mid-stream JSON parse failures.

### Components removed (shamela-only)

hadith, library, book-picker, book-table, genre-badge, hadith-grading, spectrum-bar, tier-selector.

## Routes

```
app/
  layout.tsx                          # Nav, fonts, theme
  page.tsx                            # / → redirect to /chat/<new-uuid>
  chat/[id]/page.tsx                  # Main chat Client Component
  privacy/page.tsx                    # Privacy notice
  globals.css                         # Tailwind + AskAdil tokens
  api/
    health/route.ts                   # Railway healthcheck
    chat/stream/route.ts              # POST → proxies to /api/v1/query/stream (SSE passthrough)
    chat/route.ts                     # POST → proxies to /api/v1/query (non-streaming fallback)
    chat/image/route.ts               # POST → proxies to /api/v1/query/image
    extract-url/route.ts              # POST → proxies to /api/v1/extract-url
    report/route.ts                   # POST → proxies to /api/v1/report/submit (strict rate-limit)
    upload/route.ts                   # POST multipart → writes to /data volume, records in Postgres
    jurisdiction/route.ts             # GET → proxies to /api/v1/detect-jurisdiction
    solicitors/route.ts               # GET → proxies to /api/v1/solicitors
```

### Route behaviour

| Route | Behaviour |
|-------|-----------|
| `/` | Server redirect to `/chat/<new uuid-v4>` |
| `/chat/[id]` | Reads `jurisdiction` cookie SSR-side. If absent → shows picker as first message. If present → unlocks input immediately. |
| `/privacy` | Privacy notice |
| `/api/*` | All authenticated route handlers: Zod-validated, rate-limited, X-API-Key attached server-side |

### State

| Scope | Key | Purpose |
|-------|-----|---------|
| Cookie (HTTP-only false, SameSite=Lax) | `askadil_jurisdiction` | `england_wales` / `scotland` / `northern_ireland` |
| Cookie | `askadil_consent_v1` | Analytics opt-in (if analytics added later) |
| URL query param | `?intent=report&target=bmt` | Deep-links (not sessionStorage — cross-tab safe) |
| React state (Client Component) | `messages[]`, `streaming`, `input`, `sources`, `viability` | Per-conversation chat state |
| React state (isolated, separate tree) | `reportFlow` | PII collection — never mixed with `messages[]` |

## Chat page layout

```
┌─────────────────────────────────────────────┐
│ Nav: Logo · Report · Privacy · Theme toggle │
├─────────────────────────────────────────────┤
│ Message list (scrolls)                      │
│   Assistant (jurisdiction picker if needed) │
│   User: "My employer won't let me…"         │
│   Assistant (streaming):                    │
│     Based on Section 10 [1]…                │
│     [ViabilityCard: 75 · Middle]            │
│     [SourcesPanel]                          │
├─────────────────────────────────────────────┤
│ [📎] [🔗] [Type your message…]        [↑]   │
└─────────────────────────────────────────────┘
```

## Message flow — regular query

1. User types → hits Enter → `Composer` optimistically adds user message to `messages[]`
2. Client calls `fetchEventSource('/api/chat/stream', {method: 'POST', body: ...})`
3. `/api/chat/stream` route handler:
   - Validates body with Zod (jurisdiction enum, query length, message count)
   - Checks rate limit in Postgres (`rate_limit_counters` table, keyed by IP + route)
   - Attaches `X-API-Key` and forwards to `adil-rag-api`
   - Streams SSE response back to client with the same events
4. Client consumes events:
   - `token` → append to current assistant message
   - `source` → append to sources panel
   - `viability` → render `ViabilityCard`
   - `done` → stream complete
   - `error` → shows "Connection dropped — Retry" affordance

### Retry semantics

"Retry" on an errored assistant message:
1. Deletes the partial assistant message from `messages[]`
2. Resends the last user message (same conversation_id, same jurisdiction)
3. Fresh stream attempt begins from scratch

## Message flow — report

**Critical: no PII ever enters `messages[]` or `conversation_history`.** Report state lives in a separate `reportFlow` object.

1. User sends "report" (regular chat message)
2. Assistant detects intent → replies with `ReportTargetPicker` (inline UI, 8 buttons, BMT first)
3. User clicks target → UI transitions to **inline report-collection mode**:
   - A non-chat form component appears inline between chat messages
   - Each field (name, DOB, address, incident, date) is a proper input in `reportFlow` state
   - Visually reads like a conversation (labels as "questions") but data lives in form state
   - `messages[]` shows neutral placeholders like "Collecting incident details…" — never the actual values
4. User completes fields → clicks "Review" → **`ReportModal`** opens
5. Modal shows structured summary (editable), consent checkbox, Cloudflare Turnstile challenge (optional v1, rate-limit-first) — Submit / Cancel
6. Submit → `POST /api/report` → route handler:
   - Zod-validates payload
   - Rate-limits strictly (3/hour/IP — enforces anti-spam)
   - Forwards to `adil-rag-api POST /api/v1/report/submit`
   - Returns reference ID + confirmation
7. On success: modal closes, chat shows "Report submitted — ref XYZ. Confirmation email sent."
8. On failure: modal stays open, shows error, "Retry" / "Cancel".

## API contract (with `adil-rag-api`)

### Existing endpoints used (via Next.js proxy)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/detect-jurisdiction` | IP-based pre-selection |
| `POST /api/v1/query` | Non-streaming fallback |
| `POST /api/v1/query/image` | Vision analysis (non-streaming by design) |
| `POST /api/v1/report/submit` | Submit hate-crime report |
| `POST /api/v1/extract-url` | Extract content from pasted URL |
| `GET /api/v1/solicitors` | Directory lookup |

### New streaming endpoint (Spec 1 scope — prerequisite)

Request (`POST /api/v1/query/stream`, `X-API-Key` required):
```json
{
  "query": "…",
  "conversation_id": "uuid-v4",
  "conversation_history": [{"role": "user|assistant", "content": "…"}],
  "jurisdiction": "england_wales|scotland|northern_ireland",
  "max_sources": 10,
  "include_viability_score": true
}
```

SSE response events:
```
event: token
data: "Based "

event: source
data: {"type":"statute","title":"Equality Act 2010 §10","url":"…","citation":"[1]"}

event: viability
data: {"score":75,"vento_band":"Middle","statutory_footing":true,"case_law_precedent":true,"quantum_potential":"moderate","evidence_checklist":[…]}

event: done
data: {"conversation_id":"…","sources_count":3,"tokens_used":2450}

event: error
data: {"message":"…","code":"RATE_LIMIT|AUTH|INTERNAL"}
```

**SSE JSON safety:** every `JSON.parse` on event data is wrapped in try/catch. Unparseable events are logged and skipped. A React `<ErrorBoundary>` wraps `MessageList` so malformed payloads cannot crash the app tree.

## Rate limiting (backend-only, Postgres)

**Location:** all rate-limiting logic lives in `adil-rag-api` (Spec 1). Next.js does not touch the rate-limit table — it only passes the client IP.

### Client IP propagation

Every Next.js route handler:

1. Reads `x-forwarded-for` (Railway/Cloudflare-provided)
2. Takes the left-most IP (the real client)
3. Falls back to `x-real-ip` or the socket address
4. Sends it to the backend as `X-AskAdil-Client-IP: <ip>`

The backend:
- Rejects the header unless the request carries a valid `X-API-Key` (i.e. the request came from our frontend)
- Uses this IP as the rate-limit bucket key
- Falls back to the socket IP for non-proxied direct calls

### Table and limits (Spec 1 scope — documented here for completeness)

```sql
CREATE TABLE rate_limit_counters (
  bucket_key   TEXT        NOT NULL,
  bucket_start TIMESTAMPTZ NOT NULL,
  count        INT         NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket_key, bucket_start)
);
CREATE INDEX rate_limit_counters_bucket_start_idx ON rate_limit_counters (bucket_start);
```

| Bucket | Window | Limit |
|--------|--------|-------|
| `chat:ip:<addr>` | 1 min | 30 |
| `chat:ip:<addr>` | 1 hour | 200 |
| `report:ip:<addr>` | 1 hour | 3 (strict — anti-spam) |
| `report:ip:<addr>` | 24 hour | 10 |
| `upload:ip:<addr>` | 1 hour | 10 |
| `extract-url:ip:<addr>` | 1 min | 20 |

Fixed-window counter; cleanup runs hourly (48h retention).

## Image upload (Railway volume + backend metadata)

**Security posture:** ignore all client-provided MIME types, filenames, and extensions. Detect file type from **magic bytes** (`file-type` npm package). Store under a server-generated filename. Do not serve uploaded bytes back to the browser in v1 (prevents IDOR on sensitive evidence).

### Volume

- Railway persistent volume mounted at `/data` on `adil-frontend-next`
- Uploads written to `/data/uploads/<uuid>.<ext>` where `<ext>` is derived **only from detected magic bytes** (`.png` / `.jpg` / `.webp`)
- Hourly cleanup removes files where the backend's `uploads` table says `expires_at < now()`

### Upload table (lives on `adil-rag-api`'s Postgres — Spec 1)

```sql
CREATE TABLE uploads (
  id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID         NOT NULL,
  filename        TEXT         NOT NULL,          -- relative path on volume
  content_type    TEXT         NOT NULL,          -- detected via magic bytes only
  size_bytes      INT          NOT NULL,
  storage_host    TEXT         NOT NULL,          -- "adil-frontend-next" in v1
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours')
);
```

Next.js **does not** write to this table. It POSTs metadata to a new backend endpoint `POST /api/v1/uploads/record` (Spec 1 scope).

### Upload request path (60MB max total per request)

1. Browser → `POST /api/upload` (multipart) → Next.js route handler
2. Handler:
   - Reads each file's first 4096 bytes, runs `file-type` detection
   - Rejects unless `image/png`, `image/jpeg`, `image/webp`
   - Rejects if size > 10MB per file or > 5 files
   - Generates `<server-uuid>.<detected-ext>`
   - Writes bytes to `/data/uploads/<uuid>.<detected-ext>`
   - Calls backend `POST /api/v1/uploads/record` with `{conversation_id, filename, content_type, size_bytes}` (Zod-validated server-side too)
   - Returns `[{upload_id, thumb_token?}]` — no public URL, no GET endpoint exposed
3. Browser keeps local `URL.createObjectURL(file)` for preview thumbnails in the chat transcript (no server fetch needed for display)

### Vision call

When the user sends a message with attached uploads:
1. Client POSTs `{query, upload_ids: [...], conversation_id}` to `/api/chat/image`
2. Next.js reads bytes from `/data/uploads/<upload_id>.<ext>`, bundles as multipart, forwards to `adil-rag-api POST /api/v1/query/image` with the API key
3. Backend verifies the upload records exist for this conversation, processes Gemini vision call, returns response

### Why no GET endpoint

Hate crime evidence is sensitive. Serving uploaded files back over HTTP — even at unguessable UUIDs — leaks via Referer, screen-sharing, proxy logs. v1 prevents this entirely: images are displayed client-side from the original `File` blob URL, never re-fetched. If we later need to re-display uploads across refreshes, v2 will add short-lived signed tokens bound to the session cookie.

### `next.config.ts` body size override

```ts
export default {
  output: 'standalone',
  experimental: { serverActions: { bodySizeLimit: '60mb' } },
  // Default fetch route handler body limit raised to 60mb via explicit Next.js config
};
```

## URL extraction (no client-side fetching)

All URL previews go through the backend. Client paste event → `POST /api/extract-url` → proxy to `adil-rag-api POST /api/v1/extract-url`. Never fetch user URLs from the browser (SSRF risk).

**Backend SSRF filter (Spec 1 prerequisite):** `adil-rag-api` must block fetches to RFC1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), and link-local (`169.254.0.0/16` — covers cloud metadata endpoints). Use `ssrf-req-filter` or equivalent.

## Markdown sanitisation

`react-markdown` configured with `rehype-sanitize`:
- Strip `javascript:`, `data:`, `vbscript:` URL schemes
- Remove inline HTML event handlers
- Preserve basic formatting + safe links (http, https, mailto)
- Force `rel="noopener noreferrer"` on all `<a target="_blank">` to prevent tabnabbing

## Environment variables

```
# Frontend service (stateless — no DATABASE_URL)
NEXT_PUBLIC_RAG_API_URL=https://adil-rag-api-production.up.railway.app
RAG_API_KEY=<server-side only, used in app/api/**/route.ts only>
UPLOAD_DIR=/data/uploads
NODE_ENV=production
```

**CI validation rules:**
- Grep for `RAG_API_KEY` in Client Components — any match fails the build. `RAG_API_KEY` must only appear in `app/api/**` route handlers.
- Grep for `DATABASE_URL`, `pg`, `postgres` imports — any match in frontend source fails the build. The frontend is DB-free.

## File structure

```
adil-frontend-next/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    # redirect to /chat/<uuid>
│   ├── globals.css
│   ├── chat/[id]/page.tsx          # "use client" — main chat
│   ├── privacy/page.tsx
│   └── api/                        # Stateless proxies — no DB access
│       ├── health/route.ts
│       ├── chat/stream/route.ts    # SSE proxy, attaches X-AskAdil-Client-IP
│       ├── chat/route.ts           # non-streaming fallback
│       ├── chat/image/route.ts     # reads bytes from /data volume, forwards multipart
│       ├── extract-url/route.ts
│       ├── report/route.ts
│       ├── upload/route.ts         # multipart → Railway volume + backend metadata record
│       ├── jurisdiction/route.ts
│       └── solicitors/route.ts
├── components/
│   ├── nav.tsx
│   ├── jurisdiction-selector.tsx   # reads cookie SSR-side
│   ├── composer.tsx
│   ├── image-upload.tsx
│   ├── url-preview.tsx
│   ├── searching-indicator.tsx
│   ├── error-boundary.tsx          # wraps MessageList
│   ├── chat/
│   │   ├── message-list.tsx
│   │   ├── message.tsx             # rehype-sanitize configured
│   │   ├── source-card.tsx
│   │   ├── sources-panel.tsx
│   │   └── viability-card.tsx
│   └── report/
│       ├── report-flow.tsx         # isolated state — no PII to chat
│       ├── report-target-picker.tsx
│       └── report-modal.tsx        # final confirmation
├── lib/
│   ├── api.ts                      # client-side fetch helpers (same-origin only)
│   ├── stream.ts                   # fetchEventSource wrapper with error/retry
│   ├── types.ts                    # Zod schemas + TS types
│   ├── file-type.ts                # magic-byte detection for uploads
│   ├── uploads.ts                  # Railway volume file writer
│   ├── proxy.ts                    # shared fetch helper (attaches API key + X-AskAdil-Client-IP)
│   ├── client-ip.ts                # extract client IP from request headers
│   ├── jurisdiction.ts             # cookie reader/writer
│   └── sanitize.ts                 # rehype-sanitize config (rel="noopener noreferrer")
├── tests/
│   ├── smoke.spec.ts
│   ├── streaming.spec.ts           # MSW SSE mock
│   ├── report-flow.spec.ts
│   ├── upload.spec.ts
│   └── rate-limit.spec.ts
├── public/
│   ├── logo.svg
│   ├── scales.svg
│   └── favicon.ico
├── Dockerfile
├── railway.toml
├── next.config.ts                  # standalone + body size
├── tailwind.config.ts              # MCB green
├── postcss.config.mjs
├── eslint.config.mjs               # custom rule: ban RAG_API_KEY outside app/api
├── tsconfig.json
├── package.json
├── .env.example
├── .gitignore
└── README.md
```

## Deployment

| Item | Setting |
|------|---------|
| Railway service | `adil-frontend-next` |
| Root directory | `adil-frontend-next` |
| Builder | `DOCKERFILE` (monorepo convention) |
| Port | `${PORT}` |
| Healthcheck | `/api/health` via `railway.toml` |
| Volume | `/data` (persistent, for uploads) |
| Preview domain | `next.askadil.org` |
| Shared Postgres | `adil-rag-api`'s database (tables: `rate_limit_counters`, `uploads`) |

## Cutover plan

1. Build + deploy `adil-frontend-next`, bind `next.askadil.org`
2. Preview sign-off period (~1 week)
3. Add `next.askadil.org` to heartbeat monitor
4. Flip Cloudflare root CNAME → `adil-frontend-next`
5. Sleep old `adil-frontend` (keep 30 days for rollback)
6. After 30 days: delete old service + Chainlit code

## Testing strategy

- **Playwright smoke:** chat loads, jurisdiction picker works, message sends+renders
- **Playwright streaming:** MSW-mocked SSE, verify tokens render, sources attach, viability card
- **Playwright report flow:** mock submit, verify modal, consent required, success/failure
- **Playwright upload:** mock `/api/upload`, verify file preview + size limits
- **Playwright rate-limit:** hit endpoints rapidly, expect 429
- **Manual QA checklist** against preview domain before cutover

## Success criteria

- Full feature parity with Chainlit
- Streaming first-token latency < 2s p50 (requires Spec 1)
- All Playwright suites passing
- No `RAG_API_KEY` string in built Client Components (CI check)
- Heartbeat check green for `next.askadil.org`
- Stakeholder sign-off before cutover

## Out of scope (v2 backlog)

- **Conversation persistence** (localStorage-backed saved chats)
- Account login / SSO
- Multi-language (Arabic, Urdu)
- Push notifications for report status
- Offline mode
- Mobile-native wrapper
- Cloudflare Turnstile on report submit (currently rate-limit only — add Turnstile if we see abuse post-launch)

## Risks

| Risk | Mitigation |
|------|------------|
| Streaming endpoint delivery slips | Frontend falls back to non-streaming `/api/v1/query` |
| Feature parity gap at cutover | 1-week preview + manual QA checklist; Chainlit stays as rollback |
| Report spam abuse | Strict rate-limit (3/hour/IP); Turnstile on roadmap if abuse observed |
| DoW via streaming endpoint | Backend Postgres rate limits (30/min, 200/hour per IP) |
| Rate limits bucket under single Next.js IP | X-AskAdil-Client-IP header from x-forwarded-for; backend trusts only with valid API key |
| PII in LLM context (form flow) | `reportFlow` state isolated from `messages[]`; unit test asserts separation |
| PII pasted directly into chat | Accepted v1 risk; privacy notice warns users; PII detection is v2 scope |
| RAG_API_KEY leak | CI grep for key in client bundles; ESLint rule |
| Mid-stream parse failure | React ErrorBoundary + per-event try/catch |
| SSRF via URL extraction (backend) | Spec 1 prerequisite: `ssrf-req-filter` blocks RFC1918 + 169.254/16 in adil-rag-api |
| XSS via markdown | `rehype-sanitize` strips dangerous schemes/HTML |
| Tabnabbing on citation links | `rel="noopener noreferrer"` forced on all external anchors |
| Jurisdiction enum bypass | Zod schema in every route handler |
| Hydration mismatch | Jurisdiction via cookie (SSR-readable), no localStorage in initial render |
| SessionStorage cross-tab | Replaced with URL query params for all deep-link flows |
| Malicious file upload / path traversal | Magic-byte detection (`file-type`); ignore client filename/MIME; server-generated filenames only |
| IDOR on uploaded evidence | No server-side GET endpoint for uploads in v1; displayed via client-side blob URLs only |
| Volume fills up | 24h TTL on uploads + hourly cleanup cron (backend-driven) |
| Volume growth beyond Railway quota | Monitor volume size in heartbeat; v2 migration path to R2 if >50GB/month sustained |
| Frontend accidentally becomes stateful | CI grep bans `DATABASE_URL`, `pg`, `postgres` in frontend source |
| Cloudflare cutover mistake | Rehearse on `next.askadil.org` first; rollback command prepared |
