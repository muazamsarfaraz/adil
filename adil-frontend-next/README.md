# Ask Adil — Frontend (Next.js)

Next.js 16 / React 19 chat UI for **Ask Adil**, the Muslim Council of Britain's free
UK discrimination-law guidance assistant. Live at **https://askadil.org**.

This service replaces the legacy Flask `adil-frontend` and is the canonical web frontend
for the Adil platform.

## Tech Stack

- **Next.js 16** (App Router, TypeScript)
- **React 19**
- **Tailwind CSS v4** (`@import "tailwindcss"` + `@theme` in `globals.css`)
- **@microsoft/fetch-event-source** for SSE streaming
- **react-markdown** + remark-gfm + rehype-sanitize for answer rendering
- **@aws-sdk/client-s3** for Cloudflare R2 image uploads
- **Cloudflare Turnstile** for report-submit abuse protection
- **Playwright** for E2E testing
- **Railway** deployment via Dockerfile

## Routes

| Route | Description |
|-------|-------------|
| `/` | Home → redirects to `/chat/[id]` |
| `/chat/[id]` | Main chat page with SSE streaming |
| `/privacy` | Privacy policy |
| `/api/chat` | Proxy to RAG API `/api/v1/query` |
| `/api/chat/stream` | SSE proxy to RAG API `/api/v1/query/stream` |
| `/api/chat/image` | Proxy to RAG API `/api/v1/vision` |
| `/api/report` | Proxy to RAG API `/api/v1/submit-report` |
| `/api/report/prefill` | Extract report fields from conversation |
| `/api/upload/presign` | R2 presigned URL for client-side image upload |
| `/api/jurisdiction` | Jurisdiction detection |
| `/api/solicitors` | Solicitor directory |
| `/api/extract-url` | URL content extraction proxy |
| `/api/health` | Railway healthcheck |

## Development

```bash
npm install
npm run dev          # http://localhost:3000
npm run build        # production build
npm run start        # serve the built app
npm run lint         # ESLint
npm run test         # Playwright e2e
```

## Environment Variables

Copy `.env.example` to `.env.local` and fill in real values. Vars are split between
build-time (baked into the Docker image — must be Railway **build** vars) and runtime.

### Build-time (Railway build args)

`NEXT_PUBLIC_*` variables are inlined into the JS bundle at `next build` time, so they
must be present as build args, not just runtime env.

| Var | Purpose |
|-----|---------|
| `NEXT_PUBLIC_RAG_API_URL` | Public base URL for the RAG API (e.g. `https://adil-rag-api-production.up.railway.app`) |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Cloudflare Turnstile site key (prod: `0x4AAAAAADDLP89CUloLqCrk`) |

### Runtime

| Var | Purpose |
|-----|---------|
| `RAG_API_KEY` | Auth key for inter-service calls to `adil-rag-api` |
| `TURNSTILE_SECRET` | Cloudflare Turnstile secret (server-side verification) |
| `R2_ACCOUNT_ID` | Cloudflare R2 account ID |
| `R2_BUCKET` | R2 bucket name (e.g. `adil-uploads-prod`) |
| `R2_ENDPOINT` | R2 S3-compatible endpoint URL |
| `R2_FRONTEND_ACCESS_KEY_ID` | R2 credentials, scoped to `PutObject` |
| `R2_FRONTEND_SECRET_ACCESS_KEY` | R2 credentials |
| `MSENTRY_FEEDBACK_URL` | MSentry central health-bot inbox (optional) |
| `MSENTRY_FEEDBACK_SECRET` | MSentry shared secret (optional) |
| `MSENTRY_PROJECT` | MSentry project tag, defaults to `adil-frontend-next` |
| `NODE_ENV` | `production` in deployed envs |

## Deployment

Railway service deployed from the `adil-frontend-next/` subdirectory via CLI upload
(never GitHub auto-deploy):

```bash
cd adil-frontend-next
railway up
```

The service uses a Dockerfile builder (Node 20 Alpine, Next.js `standalone` output).
`NEXT_PUBLIC_TURNSTILE_SITE_KEY` and `NEXT_PUBLIC_RAG_API_URL` must be set as Railway
**build** variables — runtime env alone is not enough because they're baked in at
Docker build time (`ARG` in the builder stage).

## Key lib/ modules

- `stream.ts` — `streamChat()` SSE client; handles `token`, `source`, `viability`, `error` events
- `api.ts` — fetch wrappers for all API routes (server/client URL switching)
- `types.ts` — shared TypeScript types (Source, Viability, Jurisdiction, etc.)
- `r2.ts` — S3Client + presigned URL generation for image uploads
- `turnstile.ts` — Cloudflare Turnstile verification
- `jurisdiction.ts` — jurisdiction cookie read/write
- `sanitize.ts` — content sanitization utilities

## Report Prefill Flow

When the user types `report` in chat:

1. Chat page calls `POST /api/report/prefill` with the full `messages` array
2. Shows an "Analysing your conversation…" card while the Gemini call runs (~1–2s)
3. `ReportFlow` receives `initialData` and pre-populates `details`, `location`, `date_time`
4. Personal PII fields (name, DOB, email) stay blank — user fills those manually
5. On completion or failure, `reportPrefill` state is reset to null

## Testing

```bash
npx playwright test
npx playwright test --reporter=html
```

## See also

- Repo-root `CLAUDE.md` — monorepo overview and service catalog
- `adil-frontend-next/CLAUDE.md` — deeper dev notes (Turnstile, SSE event handling, build-time vs runtime env)
- `adil-rag-api/` — FastAPI backend this frontend proxies to
- `adil-report-bridge/` — browser-automation service that submits reports to police portals
