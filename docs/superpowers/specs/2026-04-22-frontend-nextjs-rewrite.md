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
- **Storage:** image bytes live in **Cloudflare R2** (S3-compatible). Client uploads directly via short-lived presigned URL; lifecycle rule deletes objects after 24h. Frontend and backend remain horizontally scalable.
- **Bot protection:** **Cloudflare Turnstile** guards the final report submit step (v1). Prevents hate-crime report spam from rotating IPs.

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

**The Next.js service is entirely DB-free and stateless.** It holds no `DATABASE_URL`, no rate-limit logic, no upload metadata writes, and no local file storage. Its only jobs are: render UI, proxy to backend with the API key attached, and mint short-lived R2 presigned PUT URLs for the client.

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

**Retry backoff discipline (to prevent retry storms):**
- Automatic retry **only** on network errors or HTTP 5xx
- On HTTP 429: respect `Retry-After` header; no automatic retry, surface to user
- On HTTP 4xx (except 429): no retry; surface error
- Exponential backoff with jitter: `min(baseMs * 2^attempt, 30000) + random(0, 1000)`; base = 500ms; max 3 attempts
- Retries are client-initiated only — no silent auto-retry without user click

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
5. Modal shows structured summary (editable), consent checkbox, and a **Cloudflare Turnstile widget** (v1 requirement) — Submit / Cancel
6. Submit → client sends `{payload, turnstile_token}` to `/api/report`:
   - Zod-validates payload shape
   - Verifies Turnstile token server-side via `https://challenges.cloudflare.com/turnstile/v0/siteverify` with the server secret; rejects with 403 if invalid
   - Attaches `X-AskAdil-Client-IP` and forwards to `adil-rag-api POST /api/v1/report/submit`
   - Backend applies rate limit (3/hour/IP) as a belt-and-braces layer
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

### Client IP propagation (CF-Connecting-IP, not X-Forwarded-For)

`X-Forwarded-For` is trivially spoofable from the left. Cloudflare sits in front of both services and sets a non-spoofable header: `CF-Connecting-IP`. Use that.

Every Next.js route handler:

1. **Preferred:** `CF-Connecting-IP` header (Cloudflare-set, cannot be forged by the client)
2. **Fallback:** parse `X-Forwarded-For` from the **right-most** entry (last trusted proxy)
3. **Last resort:** the socket peer address

Forwards to the backend as `X-AskAdil-Client-IP: <ip>`.

The backend:
- **Rejects any request without `X-API-Key` with HTTP 401** — no socket-IP fallback, no anonymous path
- Only trusts `X-AskAdil-Client-IP` when the request carries a valid `X-API-Key`
- Uses this IP as the rate-limit bucket key

All direct-to-backend access is blocked at the Railway network level (internal private network). The backend is not exposed to the public internet.

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

## Image upload (Cloudflare R2 with presigned URLs)

**Security posture:**
- Client-provided MIME types, filenames, and extensions are untrusted and ignored
- Validation happens on the **presign** request, before any URL is issued
- Object keys are server-generated UUIDs, never user-controlled
- Files are never read by path from a user-supplied string (no LFI vector)
- R2 lifecycle rule deletes objects 24 hours after creation — no manual cleanup job needed

### R2 setup

- Bucket: `adil-uploads-prod` (private, no public reads)
- Lifecycle rule: `Expiration.Days = 1`
- Object key pattern: `uploads/<conversation-id>/<server-generated-uuid>.<ext>`
- Credentials:
  - **Frontend** (`R2_FRONTEND_ACCESS_KEY_ID` / `..._SECRET`): scoped to `PutObject` on the upload prefix only (used to sign PUT URLs)
  - **Backend** (`R2_BACKEND_ACCESS_KEY_ID` / `..._SECRET`): `GetObject` + `DeleteObject` (for Gemini vision calls)

### Upload table (lives on `adil-rag-api`'s Postgres — Spec 1)

```sql
CREATE TABLE uploads (
  id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID         NOT NULL,
  object_key      TEXT         NOT NULL,          -- R2 key: "uploads/<conv>/<uuid>.<ext>"
  content_type    TEXT         NOT NULL,          -- validated against enum
  size_bytes      INT          NOT NULL,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours')
);
CREATE INDEX uploads_conversation_id_idx ON uploads (conversation_id);
```

Next.js does not write directly to Postgres. Metadata records are created by the backend on `POST /api/v1/uploads/record`.

### Upload flow (client → R2 direct, no Next.js body parsing)

1. Client → `POST /api/upload/presign` with `{conversation_id, content_type, size_bytes}`
2. Next.js handler:
   - Zod-validates: `conversation_id` is UUID, `content_type` ∈ {`image/png`, `image/jpeg`, `image/webp`}, `size_bytes` ≤ 10MB
   - Generates server-side `upload_id` (UUID) and derives `ext` from validated `content_type`
   - Builds object key `uploads/<conversation_id>/<upload_id>.<ext>`
   - Calls backend `POST /api/v1/uploads/record` with metadata (backend validates + inserts into Postgres)
   - Mints R2 presigned PUT URL via `@aws-sdk/s3-request-presigner` (expires in 5 min, `Content-Type` + `Content-Length` pinned to match the client's stated values)
   - Returns `{upload_id, presigned_url, expires_at}`
3. Client PUTs the file bytes directly to R2 using the presigned URL — **no bytes pass through Next.js**
4. Client displays local blob thumbnail (`URL.createObjectURL(file)`) in the chat transcript

**Body size constraint:** because all uploads go directly to R2, Next.js never parses image bytes. The default 4MB API route body limit stays in force for all other endpoints. No global override needed.

### Vision call

When the user sends a message with attached uploads:
1. Client POSTs `{query, upload_ids: [uuid1, uuid2, …], conversation_id}` to `/api/chat/image`
2. Next.js handler:
   - Zod-validates: every `upload_id` is `z.string().uuid()`, `conversation_id` is UUID
   - Forwards `{query, upload_ids, conversation_id}` to `adil-rag-api POST /api/v1/query/image` — no file paths constructed from user input
3. Backend:
   - Looks up each `upload_id` in the `uploads` table, verifies `conversation_id` matches (prevents cross-conversation attach attacks)
   - Rejects the request if any upload is missing or doesn't belong to the conversation
   - Fetches bytes from R2 using its credentials
   - Runs Gemini vision call
   - Returns response

### Why no client-facing GET on uploads

Hate crime evidence is sensitive. Serving uploaded files back over HTTP — even at unguessable UUIDs — leaks via Referer, screen-sharing, proxy logs. v1 displays uploads from the client-side blob URL only; no server GET exists. If later required (e.g. to re-display across refreshes), v2 will issue short-lived R2 signed GET URLs bound to the session cookie.

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
# Backend connection (server-side only)
NEXT_PUBLIC_RAG_API_URL=https://adil-rag-api-production.up.railway.app   # internal private URL in prod
RAG_API_KEY=<server-side only, app/api/**/route.ts only>

# Cloudflare R2 (server-side only — PutObject scope)
R2_ACCOUNT_ID=<cloudflare account>
R2_BUCKET=adil-uploads-prod
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_FRONTEND_ACCESS_KEY_ID=<presign-scoped>
R2_FRONTEND_SECRET_ACCESS_KEY=<presign-scoped>

# Cloudflare Turnstile (report submit)
NEXT_PUBLIC_TURNSTILE_SITE_KEY=<public site key>
TURNSTILE_SECRET=<server-side only>

NODE_ENV=production
```

**CI validation rules:**
- Grep for `RAG_API_KEY`, `TURNSTILE_SECRET`, `R2_FRONTEND_SECRET_ACCESS_KEY` in Client Components — any match fails the build. Secrets must only appear in `app/api/**` route handlers.
- Grep for `DATABASE_URL`, `pg`, `postgres` imports — any match in frontend source fails the build. The frontend is DB-free.
- Grep for `process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY` outside client components — warn (site key is public but should stay client-only for clarity).

## File structure

```
adil-frontend-next/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    # redirect to /chat/<uuid>
│   ├── globals.css
│   ├── chat/[id]/page.tsx          # "use client" — main chat
│   ├── privacy/page.tsx
│   └── api/                        # Stateless proxies — no DB access, no file storage
│       ├── health/route.ts
│       ├── chat/stream/route.ts    # SSE proxy, attaches X-AskAdil-Client-IP
│       ├── chat/route.ts           # non-streaming fallback
│       ├── chat/image/route.ts     # forwards {query, upload_ids} — no byte handling
│       ├── extract-url/route.ts
│       ├── report/route.ts         # Turnstile verify + backend proxy
│       ├── upload/presign/route.ts # mints R2 presigned PUT URL; records metadata via backend
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
│   ├── stream.ts                   # fetchEventSource wrapper + exponential backoff (respects Retry-After)
│   ├── types.ts                    # Zod schemas + TS types
│   ├── r2.ts                       # R2 S3 client + presigned URL minter
│   ├── turnstile.ts                # server-side Turnstile token verifier
│   ├── proxy.ts                    # shared fetch helper (attaches API key + X-AskAdil-Client-IP)
│   ├── client-ip.ts                # extract client IP: CF-Connecting-IP → rightmost XFF → socket
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
| Volume | None (stateless — uploads go to Cloudflare R2) |
| Storage | Cloudflare R2 bucket `adil-uploads-prod` (24h lifecycle) |
| Bot protection | Cloudflare Turnstile on `/api/report` |
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
- Server-side image display (signed R2 GET URLs bound to session)
- PII detection / redaction in free-text chat
- Account login / SSO
- Multi-language (Arabic, Urdu)
- Push notifications for report status
- Offline mode
- Mobile-native wrapper

## Risks

| Risk | Mitigation |
|------|------------|
| Streaming endpoint delivery slips | Frontend falls back to non-streaming `/api/v1/query` |
| Feature parity gap at cutover | 1-week preview + manual QA checklist; Chainlit stays as rollback |
| Report spam / drowning attack | Cloudflare Turnstile on report submit + backend rate-limit (3/hour/IP) + Turnstile token verified server-side |
| DoW via streaming endpoint | Backend Postgres rate limits (30/min, 200/hour per IP); Cloudflare WAF as front line if sustained DDoS |
| Rate-limit bypass via XFF spoofing | Use `CF-Connecting-IP` (Cloudflare non-spoofable); XFF parsed right-to-left as fallback only |
| Rate limits bucket under single Next.js IP | `X-AskAdil-Client-IP` header; backend trusts only with valid API key |
| LFI via upload_ids in chat/image | Every upload_id Zod-validated as UUID; no file path construction from user input; backend fetches from R2 by validated object key |
| PII in LLM context (form flow) | `reportFlow` state isolated from `messages[]`; unit test asserts separation |
| PII pasted directly into chat | Accepted v1 risk; privacy notice warns users; PII detection is v2 scope |
| Gemini retains PII for training | **Launch prerequisite:** Gemini API key configured for zero-data-retention (ZDR) per Google Cloud agreement. Documented in privacy notice. |
| RAG_API_KEY / TURNSTILE_SECRET / R2 credential leak | CI grep bans secrets in client bundles |
| Mid-stream parse failure | React ErrorBoundary + per-event try/catch |
| SSE retry storms | Exponential backoff + jitter; respect `Retry-After`; no auto-retry on 4xx except 429 |
| SSRF via URL extraction (backend) | Spec 1 prerequisite: `ssrf-req-filter` blocks RFC1918 + 169.254/16 in adil-rag-api |
| XSS via markdown | `rehype-sanitize` strips dangerous schemes/HTML |
| Tabnabbing on citation links | `rel="noopener noreferrer"` forced on all external anchors |
| Jurisdiction enum bypass | Zod schema in every route handler |
| Hydration mismatch | Jurisdiction via cookie (SSR-readable), no localStorage in initial render |
| SessionStorage cross-tab | Replaced with URL query params for all deep-link flows |
| Malicious file upload | Presign validates content_type enum + size; object key server-generated; Turnstile on report submit catches automated abuse |
| IDOR on uploaded evidence | No client-facing GET on uploads in v1; displayed via client-side blob URLs only; backend-only R2 reads |
| Polyglot file confuses Gemini vision | Graceful fallback: if Gemini rejects, show "Image could not be analysed" instead of crashing |
| Global body size DoS | Per-route limits: default 4MB; uploads go direct to R2 (no body parsing); no global override |
| Frontend accidentally becomes stateful | CI grep bans `DATABASE_URL`, `pg`, `postgres`, local file writes in frontend source |
| Backend exposed to public internet | Railway internal network only; backend returns 401 on any request lacking valid `X-API-Key` (no socket-IP fallback) |
| R2 credential scope too wide | Frontend creds scoped to `PutObject` only; backend creds scoped to `GetObject`+`DeleteObject` |
| Cloudflare cutover mistake | Rehearse on `next.askadil.org` first; rollback command prepared |
