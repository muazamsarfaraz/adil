# adil-frontend-next Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Chainlit frontend with a Next.js 16 + React 19 app forked from `ai-shamela/frontend`. Feature parity with the existing Chainlit UI (jurisdiction picker, streaming chat, image uploads via R2, URL extraction, hate-crime report flow with Turnstile, viability cards, solicitor directory). Deploy to `next.askadil.org` first, cut over to `askadil.org` after sign-off.

**Architecture:** Stateless Next.js proxy. Browser is a Client Component that talks only to same-origin `app/api/**` route handlers. Route handlers validate with Zod, attach `X-API-Key` + `X-AskAdil-Client-IP` headers, and forward to `adil-rag-api`. Image uploads go directly from the browser to Cloudflare R2 via short-lived presigned URLs (no bytes through Next.js). Report submit is gated by Cloudflare Turnstile verified server-side.

**Tech Stack:** Next.js 16.2.3, React 19.2.4, TypeScript strict, Tailwind CSS v4, `@microsoft/fetch-event-source`, `react-markdown` + `remark-gfm` + `rehype-sanitize`, `zod`, `@aws-sdk/client-s3` + `@aws-sdk/s3-request-presigner` (R2), Playwright + MSW, Docker multi-stage + Railway.

**Spec:** `docs/superpowers/specs/2026-04-22-frontend-nextjs-rewrite.md`

**Prerequisite:** `docs/superpowers/plans/2026-04-23-rag-api-streaming-hardening.md` (backend work). The frontend can start development against the non-streaming endpoint and switch to streaming once Task 9 of the backend plan lands.

---

## File Map

All paths relative to `adil-frontend-next/` (new directory at repo root).

### Routes (app/)

| File | Responsibility |
|------|----------------|
| `app/layout.tsx` | Root layout — fonts, nav, theme, globals.css |
| `app/page.tsx` | Home — server redirect to `/chat/<new-uuid>` |
| `app/globals.css` | Tailwind imports + AskAdil tokens (MCB green) |
| `app/chat/[id]/page.tsx` | Main chat — `"use client"` |
| `app/privacy/page.tsx` | Privacy notice (static) |
| `app/api/health/route.ts` | Railway healthcheck |
| `app/api/jurisdiction/route.ts` | Proxy: GET /api/v1/detect-jurisdiction |
| `app/api/chat/route.ts` | Proxy: POST /api/v1/query (non-streaming fallback) |
| `app/api/chat/stream/route.ts` | Proxy: POST /api/v1/query/stream (SSE passthrough) |
| `app/api/chat/image/route.ts` | Proxy: POST /api/v1/query/image (no byte handling) |
| `app/api/extract-url/route.ts` | Proxy: POST /api/v1/extract-url |
| `app/api/report/route.ts` | Verify Turnstile → proxy POST /api/v1/report/submit |
| `app/api/upload/presign/route.ts` | Mint R2 presigned PUT URL + record metadata via backend |
| `app/api/solicitors/route.ts` | Proxy: GET /api/v1/solicitors |

### Components

| File | Responsibility |
|------|----------------|
| `components/nav.tsx` | Top nav (logo, report link, privacy, theme toggle) |
| `components/jurisdiction-selector.tsx` | 3 buttons, sets cookie |
| `components/composer.tsx` | Textarea + attach button + URL paste detection + send |
| `components/image-upload.tsx` | File picker + R2 presign + direct PUT |
| `components/url-preview.tsx` | Inline preview for extracted URL content |
| `components/searching-indicator.tsx` | Animated dots while waiting for first token |
| `components/error-boundary.tsx` | Wraps `MessageList` — catches mid-stream parse errors |
| `components/chat/message-list.tsx` | Scrolling list + empty-state picker |
| `components/chat/message.tsx` | Markdown + citation buttons |
| `components/chat/source-card.tsx` | Single source tile |
| `components/chat/sources-panel.tsx` | Collapsible sources panel |
| `components/chat/viability-card.tsx` | Score + Vento band + evidence checklist |
| `components/report/report-flow.tsx` | State machine for PII-isolated inline form |
| `components/report/report-target-picker.tsx` | 8-button org picker (BMT first) |
| `components/report/report-modal.tsx` | Final review + Turnstile + submit |

### lib (server + client helpers)

| File | Responsibility |
|------|----------------|
| `lib/types.ts` | Zod schemas + TS types for request/response shapes |
| `lib/client-ip.ts` | CF-Connecting-IP → rightmost XFF → socket |
| `lib/proxy.ts` | Server fetch helper (attaches API key + client IP) |
| `lib/r2.ts` | S3 client configured for R2 + presigned URL minter |
| `lib/turnstile.ts` | Server-side Turnstile token verifier |
| `lib/stream.ts` | Client fetchEventSource wrapper + exponential backoff |
| `lib/jurisdiction.ts` | Cookie reader/writer |
| `lib/sanitize.ts` | rehype-sanitize config |
| `lib/api.ts` | Client-side fetch helpers (same-origin) |

### Config

| File | Responsibility |
|------|----------------|
| `Dockerfile` | Multi-stage Node 20 alpine, `output: 'standalone'` |
| `railway.toml` | `builder = "DOCKERFILE"`, healthcheck `/api/health` |
| `next.config.ts` | `output: 'standalone'`, no global body size override |
| `tailwind.config.ts` | MCB green + typography plugin |
| `postcss.config.mjs` | Tailwind v4 |
| `eslint.config.mjs` | Ban `RAG_API_KEY`/`DATABASE_URL` outside `app/api/**` |
| `tsconfig.json` | strict, `paths: { "@/*": ["./*"] }` |
| `package.json` | dependencies below |
| `.env.example` | All vars |
| `.gitignore` | Standard Next.js |

### Tests

| File | Responsibility |
|------|----------------|
| `tests/smoke.spec.ts` | Chat loads, jurisdiction picker works, send message |
| `tests/streaming.spec.ts` | MSW-mocked SSE — tokens render, sources attach, viability card shows |
| `tests/report-flow.spec.ts` | Mock Turnstile + submit — modal opens, consent required |
| `tests/upload.spec.ts` | Mock R2 presign + PUT — thumbnail shows |
| `tests/ci-secrets.spec.ts` | Grep built bundle — no RAG_API_KEY, no DATABASE_URL |

---

## Task 1: Fork from ai-shamela and strip to AskAdil shell

**Files:**
- Create: `adil-frontend-next/` (new top-level directory)

- [ ] **Step 1: Copy ai-shamela/frontend**

```bash
cd E:/dev/mcbx/adil
cp -r ../ai-shamela/frontend adil-frontend-next
cd adil-frontend-next
rm -rf node_modules .next tsconfig.tsbuildinfo
```

- [ ] **Step 2: Rename the package**

Edit `package.json`, change the `name` field to `"adil-frontend-next"`.

- [ ] **Step 3: Remove shamela-specific modules**

```bash
rm -rf app/hadith app/library app/progress
rm -rf components/hadith components/library
rm -f components/book-picker.tsx components/tier-selector.tsx components/search-input.tsx
rm -f lib/use-book-count.ts lib/citations.ts
rm -rf tests/*
```

- [ ] **Step 4: Replace README and CLAUDE.md**

```bash
rm -f CLAUDE.md AGENTS.md
```

Create `adil-frontend-next/README.md`:

```markdown
# adil-frontend-next

Next.js 16 frontend for AskAdil. Replaces the Chainlit app in `adil-frontend/`.

## Quick start

```bash
cp .env.example .env.local  # fill in real values
npm install
npm run dev                 # http://localhost:3000
```

Tests:

```bash
npx playwright install       # one-time
npm run test
```

## Deployment

Railway service `adil-frontend-next`, root directory `adil-frontend-next`,
preview at `next.askadil.org`. See `docs/superpowers/specs/2026-04-22-frontend-nextjs-rewrite.md` for architecture.
```

- [ ] **Step 5: Gitignore Playwright reports**

Add to `.gitignore`:

```
.playwright/
playwright-report/
test-results/
```

- [ ] **Step 6: Commit the shell**

```bash
cd E:/dev/mcbx/adil
git add adil-frontend-next/
git commit -m "feat(frontend-next): fork ai-shamela shell, strip shamela-specific modules"
```

---

## Task 2: Tailwind + AskAdil theme

**Files:**
- Modify: `adil-frontend-next/tailwind.config.ts`
- Replace: `adil-frontend-next/app/globals.css`

- [ ] **Step 1: Rewrite tailwind.config.ts**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f0fdf4",
          100: "#dcfce7",
          500: "#22c55e",
          700: "#15803d",
          900: "#14532d",   // MCB primary
        },
        scale: {
          50:  "#fefce8",
          500: "#eab308",   // scales-of-justice gold accent
        },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
```

- [ ] **Step 2: Replace globals.css**

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";

@theme {
  --color-brand-900: #14532d;
  --color-brand-700: #15803d;
  --color-brand-500: #22c55e;
  --color-scale-500: #eab308;
}

html, body {
  @apply h-full bg-white text-gray-900 antialiased;
}

body {
  font-family: var(--font-sans, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);
}
```

- [ ] **Step 3: Commit**

```bash
git add adil-frontend-next/tailwind.config.ts adil-frontend-next/app/globals.css
git commit -m "feat(frontend-next): AskAdil MCB-green tailwind theme"
```

---

## Task 3: Dependencies + Dockerfile + railway.toml + next.config.ts

**Files:**
- Modify: `adil-frontend-next/package.json`
- Create/replace: `adil-frontend-next/Dockerfile`
- Create/replace: `adil-frontend-next/railway.toml`
- Replace: `adil-frontend-next/next.config.ts`
- Create: `adil-frontend-next/.env.example`

- [ ] **Step 1: Update package.json**

```json
{
  "name": "adil-frontend-next",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start -p ${PORT:-3000}",
    "lint": "eslint",
    "test": "playwright test"
  },
  "dependencies": {
    "@aws-sdk/client-s3": "^3.700.0",
    "@aws-sdk/s3-request-presigner": "^3.700.0",
    "@microsoft/fetch-event-source": "^2.0.1",
    "@tailwindcss/typography": "^0.5.19",
    "next": "16.2.3",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "react-markdown": "^10.1.0",
    "rehype-sanitize": "^6.0.0",
    "remark-gfm": "^4.0.1",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.59.1",
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.2.3",
    "msw": "^2.6.0",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

Install:

```bash
cd adil-frontend-next
npm install
```

- [ ] **Step 2: Rewrite next.config.ts**

```ts
import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // NOTE: No global serverActions.bodySizeLimit override.
  // Uploads go directly to R2 from the browser via presigned URLs — no bytes through Next.js.
  // The default 4MB API route body limit stays in force for all other endpoints.
};

export default config;
```

- [ ] **Step 3: Create Dockerfile**

```dockerfile
# Stage 1 — builder
FROM node:20-alpine AS builder

WORKDIR /app

# Enable corepack for consistent npm/pnpm/yarn
RUN corepack enable

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# Stage 2 — runtime
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Non-root user
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001 -G nodejs

# Standalone build includes only what's needed
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
```

- [ ] **Step 4: Create railway.toml**

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/api/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

- [ ] **Step 5: Create .env.example**

```env
# Backend proxy target
NEXT_PUBLIC_RAG_API_URL=https://adil-rag-api-production.up.railway.app
RAG_API_KEY=change-me

# Cloudflare R2 (frontend creds — PutObject scope)
R2_ACCOUNT_ID=your-account-id
R2_BUCKET=adil-uploads-prod
R2_ENDPOINT=https://your-account-id.r2.cloudflarestorage.com
R2_FRONTEND_ACCESS_KEY_ID=change-me
R2_FRONTEND_SECRET_ACCESS_KEY=change-me

# Cloudflare Turnstile (report submit)
NEXT_PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA  # testing key; replace in prod
TURNSTILE_SECRET=change-me

NODE_ENV=production
```

- [ ] **Step 6: Commit**

```bash
git add adil-frontend-next/package.json adil-frontend-next/package-lock.json \
        adil-frontend-next/Dockerfile adil-frontend-next/railway.toml \
        adil-frontend-next/next.config.ts adil-frontend-next/.env.example
git commit -m "feat(frontend-next): dependencies, Dockerfile, railway.toml, config"
```

---

## Task 4: Types + Zod schemas in lib/types.ts

**Files:**
- Create: `adil-frontend-next/lib/types.ts`

- [ ] **Step 1: Write the types**

```ts
import { z } from "zod";

// ----- Primitive enums -----
export const JurisdictionEnum = z.enum(["england_wales", "scotland", "northern_ireland"]);
export type Jurisdiction = z.infer<typeof JurisdictionEnum>;

export const ContentTypeEnum = z.enum(["image/png", "image/jpeg", "image/webp"]);
export type ContentType = z.infer<typeof ContentTypeEnum>;

export const SourceTypeEnum = z.enum(["statute", "case_law", "echr_judgment"]);
export type SourceType = z.infer<typeof SourceTypeEnum>;

export const VentoBandEnum = z.enum(["Lower", "Middle", "Upper", "Exceptional"]);
export type VentoBand = z.infer<typeof VentoBandEnum>;

// ----- Chat -----
export const ConversationTurnSchema = z.object({
  role: z.enum(["user", "assistant"]),
  content: z.string().max(20_000),
});
export type ConversationTurn = z.infer<typeof ConversationTurnSchema>;

export const QueryRequestSchema = z.object({
  query: z.string().min(1).max(5_000),
  conversation_id: z.string().uuid(),
  conversation_history: z.array(ConversationTurnSchema).max(50).optional(),
  jurisdiction: JurisdictionEnum.optional(),
  max_sources: z.number().int().min(1).max(20).default(10),
  include_viability_score: z.boolean().default(true),
});
export type QueryRequest = z.infer<typeof QueryRequestSchema>;

export const SourceSchema = z.object({
  type: SourceTypeEnum,
  title: z.string(),
  url: z.string().url().nullable().optional(),
  citation: z.string(),
  excerpt: z.string().optional(),
});
export type Source = z.infer<typeof SourceSchema>;

export const ViabilitySchema = z.object({
  score: z.number().int().min(0).max(100),
  vento_band: VentoBandEnum,
  statutory_footing: z.boolean(),
  case_law_precedent: z.boolean(),
  quantum_potential: z.enum(["low", "moderate", "high"]),
  evidence_checklist: z.array(z.string()),
});
export type Viability = z.infer<typeof ViabilitySchema>;

// ----- Stream events -----
export type StreamEvent =
  | { event: "token"; data: string }
  | { event: "source"; data: Source }
  | { event: "viability"; data: Viability }
  | { event: "done"; data: { conversation_id: string | null; sources_count: number; tokens_used: number } }
  | { event: "error"; data: { message: string; code: string } };

// ----- Image query -----
export const ImageQueryRequestSchema = z.object({
  query: z.string().min(1).max(5_000),
  conversation_id: z.string().uuid(),
  upload_ids: z.array(z.string().uuid()).min(1).max(5),
});
export type ImageQueryRequest = z.infer<typeof ImageQueryRequestSchema>;

// ----- Upload presign -----
export const PresignRequestSchema = z.object({
  conversation_id: z.string().uuid(),
  content_type: ContentTypeEnum,
  size_bytes: z.number().int().min(1).max(10_485_760),
});
export type PresignRequest = z.infer<typeof PresignRequestSchema>;

export const PresignResponseSchema = z.object({
  upload_id: z.string().uuid(),
  presigned_url: z.string().url(),
  object_key: z.string(),
  expires_at: z.string(),
});
export type PresignResponse = z.infer<typeof PresignResponseSchema>;

// ----- Report -----
export const ReporterInfoSchema = z.object({
  name: z.string().min(1).max(200),
  email: z.string().email().max(200),
  phone: z.string().max(50).optional(),
  dob: z.string().optional(),
  address: z.string().max(500).optional(),
});

export const IncidentInfoSchema = z.object({
  target_org: z.string().min(1).max(50),
  summary: z.string().min(10).max(5_000),
  date: z.string().optional(),
  location: z.string().max(500).optional(),
});

export const ReportSubmitRequestSchema = z.object({
  reporter: ReporterInfoSchema,
  incident: IncidentInfoSchema,
  turnstile_token: z.string().min(10),
});
export type ReportSubmitRequest = z.infer<typeof ReportSubmitRequestSchema>;

// ----- Extract URL -----
export const ExtractUrlRequestSchema = z.object({
  url: z.string().url().max(2_000),
});
export type ExtractUrlRequest = z.infer<typeof ExtractUrlRequestSchema>;
```

- [ ] **Step 2: Commit**

```bash
git add adil-frontend-next/lib/types.ts
git commit -m "feat(frontend-next): Zod schemas + TS types for all request/response shapes"
```

---

## Task 5: lib/client-ip.ts

**Files:**
- Create: `adil-frontend-next/lib/client-ip.ts`
- Create: `adil-frontend-next/tests/client-ip.spec.ts`

- [ ] **Step 1: Write the failing test**

```ts
// tests/client-ip.spec.ts
import { test, expect } from "@playwright/test";
import { extractClientIp } from "../lib/client-ip";

test.describe("extractClientIp", () => {
  test("prefers CF-Connecting-IP", () => {
    const req = new Request("http://x", {
      headers: {
        "cf-connecting-ip": "9.9.9.9",
        "x-forwarded-for": "1.1.1.1, 2.2.2.2",
      },
    });
    expect(extractClientIp(req)).toBe("9.9.9.9");
  });

  test("falls back to rightmost X-Forwarded-For", () => {
    const req = new Request("http://x", {
      headers: {
        "x-forwarded-for": "1.2.3.4, 10.0.0.1",
      },
    });
    expect(extractClientIp(req)).toBe("10.0.0.1");
  });

  test("handles single XFF entry", () => {
    const req = new Request("http://x", {
      headers: { "x-forwarded-for": "5.5.5.5" },
    });
    expect(extractClientIp(req)).toBe("5.5.5.5");
  });

  test("returns 'unknown' when no headers present", () => {
    const req = new Request("http://x");
    expect(extractClientIp(req)).toBe("unknown");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd adil-frontend-next
npm run test -- tests/client-ip.spec.ts
```

Expected: fails — module doesn't exist.

- [ ] **Step 3: Implement client-ip.ts**

```ts
// lib/client-ip.ts
/**
 * Extract the real client IP from incoming request headers.
 *
 * Cloudflare's CF-Connecting-IP is non-spoofable when we sit behind Cloudflare.
 * X-Forwarded-For is parsed from the right-most entry (the last trusted proxy).
 * The socket peer address is unavailable in Next.js route handlers, so if no
 * headers are present we return "unknown" (which will bucket oddly but does
 * not misattribute to a spoofed IP).
 */
export function extractClientIp(request: Request): string {
  const cf = request.headers.get("cf-connecting-ip");
  if (cf && cf.trim()) {
    return cf.trim();
  }

  const xff = request.headers.get("x-forwarded-for");
  if (xff && xff.trim()) {
    const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length > 0) {
      return parts[parts.length - 1];
    }
  }

  const xri = request.headers.get("x-real-ip");
  if (xri && xri.trim()) return xri.trim();

  return "unknown";
}
```

- [ ] **Step 4: Run tests**

Playwright config needs to pick up unit-style tests. Create a minimal `playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  reporter: "list",
  use: {
    headless: true,
  },
});
```

Then run:

```bash
npm run test -- tests/client-ip.spec.ts
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add adil-frontend-next/lib/client-ip.ts adil-frontend-next/playwright.config.ts adil-frontend-next/tests/client-ip.spec.ts
git commit -m "feat(frontend-next): client IP extraction (CF-Connecting-IP first)"
```

---

## Task 6: lib/proxy.ts — shared server fetch helper

**Files:**
- Create: `adil-frontend-next/lib/proxy.ts`

- [ ] **Step 1: Implement**

```ts
// lib/proxy.ts
import { extractClientIp } from "./client-ip";

export interface ProxyOptions {
  /** HTTP method. Default POST. */
  method?: "GET" | "POST";
  /** Request body (will be JSON-stringified if not undefined). */
  body?: unknown;
  /** Extra headers to forward. */
  extraHeaders?: Record<string, string>;
}

export function getRagApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_RAG_API_URL;
  if (!url) throw new Error("NEXT_PUBLIC_RAG_API_URL is not configured");
  return url.replace(/\/+$/, "");
}

export function getRagApiKey(): string {
  const key = process.env.RAG_API_KEY;
  if (!key) throw new Error("RAG_API_KEY is not configured (server-side secret)");
  return key;
}

export async function proxyToBackend(
  request: Request,
  path: string,
  options: ProxyOptions = {},
): Promise<Response> {
  const baseUrl = getRagApiBaseUrl();
  const apiKey = getRagApiKey();
  const clientIp = extractClientIp(request);

  const headers: Record<string, string> = {
    "X-API-Key": apiKey,
    "X-AskAdil-Client-IP": clientIp,
    "Content-Type": "application/json",
    ...(options.extraHeaders ?? {}),
  };

  const init: RequestInit = {
    method: options.method ?? "POST",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  };

  return fetch(`${baseUrl}${path}`, init);
}
```

- [ ] **Step 2: Commit**

```bash
git add adil-frontend-next/lib/proxy.ts
git commit -m "feat(frontend-next): shared proxy helper for backend calls"
```

---

## Task 7: lib/r2.ts — R2 client + presign helper

**Files:**
- Create: `adil-frontend-next/lib/r2.ts`

- [ ] **Step 1: Implement**

```ts
// lib/r2.ts
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { randomUUID } from "crypto";
import { ContentType } from "./types";

function envOrThrow(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not configured`);
  return v;
}

let _client: S3Client | null = null;

export function getR2Client(): S3Client {
  if (_client) return _client;
  const endpoint = envOrThrow("R2_ENDPOINT");
  const accessKeyId = envOrThrow("R2_FRONTEND_ACCESS_KEY_ID");
  const secretAccessKey = envOrThrow("R2_FRONTEND_SECRET_ACCESS_KEY");
  _client = new S3Client({
    region: "auto",
    endpoint,
    credentials: { accessKeyId, secretAccessKey },
    forcePathStyle: false,
  });
  return _client;
}

export function getR2Bucket(): string {
  return envOrThrow("R2_BUCKET");
}

export interface PresignResult {
  uploadId: string;
  objectKey: string;
  presignedUrl: string;
  expiresAt: string;
}

const EXT: Record<ContentType, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
};

/**
 * Mint a short-lived (5 min) presigned PUT URL for the given content type + size.
 * Object key is server-generated (UUID); never accepts client-supplied filenames.
 * The URL pins Content-Type and Content-Length so a malicious client cannot
 * upload mismatched types or oversized payloads.
 */
export async function presignUpload(args: {
  conversationId: string;
  contentType: ContentType;
  sizeBytes: number;
  expirySeconds?: number;
}): Promise<PresignResult> {
  const client = getR2Client();
  const bucket = getR2Bucket();
  const uploadId = randomUUID();
  const ext = EXT[args.contentType];
  const objectKey = `uploads/${args.conversationId}/${uploadId}.${ext}`;

  const command = new PutObjectCommand({
    Bucket: bucket,
    Key: objectKey,
    ContentType: args.contentType,
    ContentLength: args.sizeBytes,
  });

  const expirySeconds = args.expirySeconds ?? 300; // 5 minutes
  const presignedUrl = await getSignedUrl(client, command, { expiresIn: expirySeconds });
  const expiresAt = new Date(Date.now() + expirySeconds * 1000).toISOString();

  return { uploadId, objectKey, presignedUrl, expiresAt };
}
```

- [ ] **Step 2: Commit**

```bash
git add adil-frontend-next/lib/r2.ts
git commit -m "feat(frontend-next): R2 presigned PUT URL minter"
```

---

## Task 8: lib/turnstile.ts — server-side Turnstile verifier

**Files:**
- Create: `adil-frontend-next/lib/turnstile.ts`

- [ ] **Step 1: Implement**

```ts
// lib/turnstile.ts
/**
 * Server-side Cloudflare Turnstile token verifier.
 * See https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
 */

const VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

export interface TurnstileResult {
  success: boolean;
  errorCodes?: string[];
}

export async function verifyTurnstile(token: string, remoteIp?: string): Promise<TurnstileResult> {
  const secret = process.env.TURNSTILE_SECRET;
  if (!secret) {
    throw new Error("TURNSTILE_SECRET is not configured");
  }

  const body = new URLSearchParams();
  body.set("secret", secret);
  body.set("response", token);
  if (remoteIp && remoteIp !== "unknown") body.set("remoteip", remoteIp);

  const resp = await fetch(VERIFY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    // Short timeout — don't hang the report submit
    signal: AbortSignal.timeout(5_000),
  });

  if (!resp.ok) {
    return { success: false, errorCodes: [`http-${resp.status}`] };
  }

  const data = (await resp.json()) as { success: boolean; "error-codes"?: string[] };
  return { success: data.success === true, errorCodes: data["error-codes"] };
}
```

- [ ] **Step 2: Commit**

```bash
git add adil-frontend-next/lib/turnstile.ts
git commit -m "feat(frontend-next): server-side Turnstile token verifier"
```

---

## Task 9: lib/stream.ts — client SSE wrapper with backoff

**Files:**
- Create: `adil-frontend-next/lib/stream.ts`

- [ ] **Step 1: Implement**

```ts
// lib/stream.ts
"use client";

import { fetchEventSource, EventSourceMessage } from "@microsoft/fetch-event-source";
import { StreamEvent } from "./types";

export interface StreamOptions {
  url: string;
  body: unknown;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
  onError: (err: { message: string; status?: number; retryAfter?: number }) => void;
  /** Max automatic retry attempts (only on network errors or 5xx). */
  maxAttempts?: number;
}

/**
 * POST+SSE consumer. Browser EventSource is GET-only and doesn't support
 * custom headers, so we use @microsoft/fetch-event-source.
 *
 * Retry discipline:
 *   - 4xx (except 429): no retry, surface error immediately
 *   - 429: no auto-retry; surface Retry-After to caller
 *   - 5xx or network error: exponential backoff with jitter, up to maxAttempts
 *   - Client must initiate retry via user action (no silent auto-retry)
 */
export async function streamChat(opts: StreamOptions): Promise<void> {
  const maxAttempts = opts.maxAttempts ?? 1; // By default, no auto-retry on success path errors
  let attempt = 0;

  while (attempt < maxAttempts) {
    attempt += 1;
    let retry = false;

    try {
      await fetchEventSource(opts.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(opts.body),
        signal: opts.signal,
        openWhenHidden: true,

        async onopen(response) {
          if (response.ok && response.headers.get("content-type")?.startsWith("text/event-stream")) {
            return;
          }
          if (response.status === 429) {
            const retryAfter = parseInt(response.headers.get("retry-after") ?? "0", 10);
            opts.onError({ message: "Too many requests", status: 429, retryAfter: retryAfter || undefined });
            throw new Error("429");
          }
          if (response.status >= 400 && response.status < 500) {
            const text = await response.text().catch(() => "");
            opts.onError({ message: text || response.statusText, status: response.status });
            throw new Error(`client-${response.status}`);
          }
          // 5xx — retry
          retry = true;
          throw new Error(`server-${response.status}`);
        },

        onmessage(msg: EventSourceMessage) {
          if (!msg.event || !msg.data) return;
          try {
            const parsed: StreamEvent = {
              event: msg.event as StreamEvent["event"],
              data: msg.event === "token" ? JSON.parse(msg.data) : JSON.parse(msg.data),
            } as StreamEvent;
            opts.onEvent(parsed);
          } catch {
            // Malformed chunk — skip. ErrorBoundary prevents propagation.
          }
        },

        onerror(err) {
          // Network-level error — allow one backoff retry
          retry = true;
          throw err;
        },

        onclose() {
          // Stream ended normally — don't retry
          retry = false;
        },
      });

      // Completed cleanly
      return;
    } catch {
      if (!retry || attempt >= maxAttempts) {
        if (!retry) return; // 4xx or 429 — already reported
        opts.onError({ message: "Connection failed after retries" });
        return;
      }
      // Exponential backoff with jitter: base 500ms, cap 30s
      const base = 500;
      const delay = Math.min(base * 2 ** (attempt - 1), 30_000) + Math.random() * 1000;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add adil-frontend-next/lib/stream.ts
git commit -m "feat(frontend-next): POST+SSE client wrapper with exponential backoff"
```

---

## Task 10: lib/sanitize.ts + lib/jurisdiction.ts + lib/api.ts

**Files:**
- Create: `adil-frontend-next/lib/sanitize.ts`
- Create: `adil-frontend-next/lib/jurisdiction.ts`
- Create: `adil-frontend-next/lib/api.ts`

- [ ] **Step 1: sanitize.ts**

```ts
// lib/sanitize.ts
import { defaultSchema } from "rehype-sanitize";

/**
 * Hardened rehype-sanitize config:
 *   - Strip javascript:, data:, vbscript: URL schemes
 *   - Remove inline event handlers
 *   - Force rel="noopener noreferrer" + target="_blank" removed on anchors (prevents tabnabbing)
 */
export const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [
      ["href", /^(?!javascript:|data:|vbscript:)/i],
      "title",
    ],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: ["http", "https", "mailto"],
  },
};

/**
 * rehype plugin: force rel="noopener noreferrer" on every anchor with target="_blank",
 * or strip target="_blank" entirely (safer default).
 */
export function rehypeSafeLinks() {
  return (tree: any) => {
    const visit = (node: any) => {
      if (node.type === "element" && node.tagName === "a" && node.properties) {
        delete node.properties.target;
        node.properties.rel = "noopener noreferrer";
      }
      if (node.children) node.children.forEach(visit);
    };
    visit(tree);
  };
}
```

- [ ] **Step 2: jurisdiction.ts**

```ts
// lib/jurisdiction.ts
import { cookies } from "next/headers";
import { JurisdictionEnum, Jurisdiction } from "./types";

const COOKIE = "askadil_jurisdiction";
const MAX_AGE_S = 60 * 60 * 24 * 365; // 1 year

export async function readJurisdiction(): Promise<Jurisdiction | null> {
  const store = await cookies();
  const v = store.get(COOKIE)?.value;
  if (!v) return null;
  const parsed = JurisdictionEnum.safeParse(v);
  return parsed.success ? parsed.data : null;
}

export function writeJurisdictionHeaders(j: Jurisdiction): string {
  // For use in client components setting document.cookie directly
  return `${COOKIE}=${encodeURIComponent(j)}; Path=/; Max-Age=${MAX_AGE_S}; SameSite=Lax`;
}

// Client-side helpers
export function readJurisdictionClient(): Jurisdiction | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!match) return null;
  const parsed = JurisdictionEnum.safeParse(decodeURIComponent(match[1]));
  return parsed.success ? parsed.data : null;
}

export function writeJurisdictionClient(j: Jurisdiction): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE}=${encodeURIComponent(j)}; Path=/; Max-Age=${MAX_AGE_S}; SameSite=Lax`;
}
```

- [ ] **Step 3: api.ts (client-side fetchers)**

```ts
// lib/api.ts
"use client";

import type {
  QueryRequest, ImageQueryRequest, PresignRequest, PresignResponse,
  ReportSubmitRequest, ExtractUrlRequest,
} from "./types";

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw Object.assign(new Error(text || resp.statusText), { status: resp.status });
  }
  return (await resp.json()) as T;
}

export async function presignUpload(body: PresignRequest): Promise<PresignResponse> {
  const resp = await fetch("/api/upload/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<PresignResponse>(resp);
}

export async function submitReport(body: ReportSubmitRequest): Promise<{ reference: string }> {
  const resp = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<{ reference: string }>(resp);
}

export async function extractUrl(body: ExtractUrlRequest): Promise<{ title: string; excerpt: string }> {
  const resp = await fetch("/api/extract-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json(resp);
}

export async function queryImage(body: ImageQueryRequest): Promise<unknown> {
  const resp = await fetch("/api/chat/image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json(resp);
}
```

- [ ] **Step 4: Commit**

```bash
git add adil-frontend-next/lib/sanitize.ts adil-frontend-next/lib/jurisdiction.ts adil-frontend-next/lib/api.ts
git commit -m "feat(frontend-next): sanitize, jurisdiction cookie, client api helpers"
```

---

## Task 11: Route handlers (all 9)

**Files:**
- Create: `adil-frontend-next/app/api/health/route.ts`
- Create: `adil-frontend-next/app/api/jurisdiction/route.ts`
- Create: `adil-frontend-next/app/api/chat/route.ts`
- Create: `adil-frontend-next/app/api/chat/stream/route.ts`
- Create: `adil-frontend-next/app/api/chat/image/route.ts`
- Create: `adil-frontend-next/app/api/extract-url/route.ts`
- Create: `adil-frontend-next/app/api/report/route.ts`
- Create: `adil-frontend-next/app/api/upload/presign/route.ts`
- Create: `adil-frontend-next/app/api/solicitors/route.ts`

Each route follows the same pattern: Zod validate → proxy or mint presign → return response.

- [ ] **Step 1: health**

```ts
// app/api/health/route.ts
export const dynamic = "force-dynamic";
export async function GET() {
  return Response.json({ status: "ok", service: "adil-frontend-next" });
}
```

- [ ] **Step 2: jurisdiction**

```ts
// app/api/jurisdiction/route.ts
import { proxyToBackend } from "@/lib/proxy";

export async function GET(request: Request) {
  const upstream = await proxyToBackend(request, "/api/v1/detect-jurisdiction", { method: "GET" });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
```

- [ ] **Step 3: chat (non-streaming fallback)**

```ts
// app/api/chat/route.ts
import { QueryRequestSchema } from "@/lib/types";
import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = QueryRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }
  const upstream = await proxyToBackend(request, "/api/v1/query", { body: parsed.data });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
```

- [ ] **Step 4: chat/stream (SSE passthrough)**

```ts
// app/api/chat/stream/route.ts
import { QueryRequestSchema } from "@/lib/types";
import { getRagApiBaseUrl, getRagApiKey } from "@/lib/proxy";
import { extractClientIp } from "@/lib/client-ip";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = QueryRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }

  const upstream = await fetch(`${getRagApiBaseUrl()}/api/v1/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getRagApiKey(),
      "X-AskAdil-Client-IP": extractClientIp(request),
      Accept: "text/event-stream",
    },
    body: JSON.stringify(parsed.data),
  });

  // Pass through SSE stream (and any 4xx/5xx response) verbatim
  const contentType = upstream.headers.get("content-type") ?? "text/event-stream";
  const headers: Record<string, string> = {
    "Content-Type": contentType,
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
  };
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) headers["Retry-After"] = retryAfter;

  return new Response(upstream.body, { status: upstream.status, headers });
}
```

- [ ] **Step 5: chat/image**

```ts
// app/api/chat/image/route.ts
import { ImageQueryRequestSchema } from "@/lib/types";
import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = ImageQueryRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }
  const upstream = await proxyToBackend(request, "/api/v1/query/image", { body: parsed.data });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
```

- [ ] **Step 6: extract-url**

```ts
// app/api/extract-url/route.ts
import { ExtractUrlRequestSchema } from "@/lib/types";
import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = ExtractUrlRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }
  const upstream = await proxyToBackend(request, "/api/v1/extract-url", { body: parsed.data });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
```

- [ ] **Step 7: report (Turnstile → proxy)**

```ts
// app/api/report/route.ts
import { ReportSubmitRequestSchema } from "@/lib/types";
import { proxyToBackend } from "@/lib/proxy";
import { verifyTurnstile } from "@/lib/turnstile";
import { extractClientIp } from "@/lib/client-ip";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = ReportSubmitRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }

  const clientIp = extractClientIp(request);
  const ts = await verifyTurnstile(parsed.data.turnstile_token, clientIp);
  if (!ts.success) {
    return Response.json({ error: "turnstile_failed", codes: ts.errorCodes ?? [] }, { status: 403 });
  }

  // Backend doesn't need the turnstile token — strip it before forwarding
  const { turnstile_token, ...forwardBody } = parsed.data;
  const upstream = await proxyToBackend(request, "/api/v1/report/submit", { body: forwardBody });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
```

- [ ] **Step 8: upload/presign**

```ts
// app/api/upload/presign/route.ts
import { PresignRequestSchema } from "@/lib/types";
import { presignUpload } from "@/lib/r2";
import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = PresignRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }

  const { conversation_id, content_type, size_bytes } = parsed.data;
  const { uploadId, objectKey, presignedUrl, expiresAt } = await presignUpload({
    conversationId: conversation_id,
    contentType: content_type,
    sizeBytes: size_bytes,
  });

  // Record metadata on the backend. If this fails, return 502 — the client will retry.
  const record = await proxyToBackend(request, "/api/v1/uploads/record", {
    body: {
      id: uploadId,
      conversation_id,
      object_key: objectKey,
      content_type,
      size_bytes,
    },
  });
  if (record.status >= 300) {
    const detail = await record.text().catch(() => "");
    return Response.json({ error: "record_failed", detail }, { status: 502 });
  }

  return Response.json({
    upload_id: uploadId,
    object_key: objectKey,
    presigned_url: presignedUrl,
    expires_at: expiresAt,
  });
}
```

- [ ] **Step 9: solicitors**

```ts
// app/api/solicitors/route.ts
import { proxyToBackend } from "@/lib/proxy";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const qs = url.search;
  const upstream = await proxyToBackend(request, `/api/v1/solicitors${qs}`, { method: "GET" });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
```

- [ ] **Step 10: Commit**

```bash
git add adil-frontend-next/app/api/
git commit -m "feat(frontend-next): 9 route handlers (Zod-validated proxies + R2 presign + Turnstile)"
```

---

## Task 12: Root layout, home redirect, privacy page

**Files:**
- Create: `adil-frontend-next/app/layout.tsx`
- Create: `adil-frontend-next/app/page.tsx`
- Create: `adil-frontend-next/app/privacy/page.tsx`

- [ ] **Step 1: layout.tsx**

```tsx
// app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/nav";

export const metadata: Metadata = {
  title: "AskAdil — UK discrimination law guidance",
  description: "Free AI-powered UK discrimination law education for British Muslims. A Muslim Council of Britain initiative.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full flex flex-col">
        <Nav />
        <main className="flex-1 flex flex-col overflow-hidden">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: page.tsx (home → /chat/<uuid>)**

```tsx
// app/page.tsx
import { redirect } from "next/navigation";
import { randomUUID } from "crypto";

export default function HomePage() {
  const id = randomUUID();
  redirect(`/chat/${id}`);
}
```

- [ ] **Step 3: privacy page**

```tsx
// app/privacy/page.tsx
export const metadata = { title: "Privacy — AskAdil" };

export default function PrivacyPage() {
  return (
    <article className="prose max-w-3xl mx-auto py-10 px-4">
      <h1>Privacy notice</h1>
      <p><em>Last updated: April 2026.</em></p>
      <h2>What we collect</h2>
      <p>Anonymised conversation logs (no names, no contact details). IP address for rate limiting only.</p>
      <h2>What we do NOT collect</h2>
      <p>We do not collect user accounts. We do not track you across sites.</p>
      <h2>Hate crime reports</h2>
      <p>When you submit a hate crime report, your details are forwarded directly to the selected organisation
         (e.g. British Muslim Trust) and <strong>immediately discarded</strong> from our servers. We do not store your personal details.</p>
      <h2>AI processing</h2>
      <p>Chat messages are sent to Google Gemini under a zero-data-retention agreement.
         Google does not retain or train on your messages.</p>
      <h2>Contact</h2>
      <p>Email the MCB privacy team at privacy@mcb.org.uk.</p>
    </article>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add adil-frontend-next/app/layout.tsx adil-frontend-next/app/page.tsx adil-frontend-next/app/privacy/
git commit -m "feat(frontend-next): root layout, home redirect, privacy page"
```

---

## Task 13: Components batch A — Nav, JurisdictionSelector, SearchingIndicator, ErrorBoundary

**Files:**
- Create: `adil-frontend-next/components/nav.tsx`
- Create: `adil-frontend-next/components/jurisdiction-selector.tsx`
- Create: `adil-frontend-next/components/searching-indicator.tsx`
- Create: `adil-frontend-next/components/error-boundary.tsx`

- [ ] **Step 1: nav.tsx**

```tsx
// components/nav.tsx
import Link from "next/link";

export default function Nav() {
  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="font-semibold text-brand-900 text-lg">
          AskAdil <span className="font-normal text-gray-500">(عادل)</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/chat/new" className="text-gray-700 hover:text-brand-700">New chat</Link>
          <Link href="/privacy" className="text-gray-700 hover:text-brand-700">Privacy</Link>
        </nav>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: jurisdiction-selector.tsx**

```tsx
// components/jurisdiction-selector.tsx
"use client";

import { Jurisdiction } from "@/lib/types";
import { writeJurisdictionClient } from "@/lib/jurisdiction";

export default function JurisdictionSelector({ onSelect }: { onSelect: (j: Jurisdiction) => void }) {
  const pick = (j: Jurisdiction) => {
    writeJurisdictionClient(j);
    onSelect(j);
  };
  return (
    <div className="flex flex-wrap gap-2 my-3">
      <button onClick={() => pick("england_wales")}
              className="px-4 py-2 rounded-full bg-brand-900 text-white hover:bg-brand-700 transition-colors">
        🏴󠁧󠁢󠁥󠁮󠁧󠁿 England &amp; Wales
      </button>
      <button onClick={() => pick("scotland")}
              className="px-4 py-2 rounded-full bg-brand-900 text-white hover:bg-brand-700 transition-colors">
        🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland
      </button>
      <button onClick={() => pick("northern_ireland")}
              className="px-4 py-2 rounded-full bg-brand-900 text-white hover:bg-brand-700 transition-colors">
        🇬🇧 Northern Ireland
      </button>
    </div>
  );
}
```

- [ ] **Step 3: searching-indicator.tsx**

```tsx
// components/searching-indicator.tsx
export default function SearchingIndicator() {
  return (
    <div className="flex items-center gap-2 text-gray-500 text-sm py-2">
      <span className="inline-block w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
      <span>Searching UK legislation and case law…</span>
    </div>
  );
}
```

- [ ] **Step 4: error-boundary.tsx**

```tsx
// components/error-boundary.tsx
"use client";

import React from "react";

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: unknown) { console.error("ErrorBoundary caught", error); }
  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="p-4 bg-red-50 text-red-800 rounded">
          Something went wrong rendering this message. Please retry.
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add adil-frontend-next/components/nav.tsx adil-frontend-next/components/jurisdiction-selector.tsx \
        adil-frontend-next/components/searching-indicator.tsx adil-frontend-next/components/error-boundary.tsx
git commit -m "feat(frontend-next): nav, jurisdiction selector, searching indicator, error boundary"
```

---

## Task 14: Components batch B — Chat message, source card, sources panel, viability card

**Files:**
- Create: `adil-frontend-next/components/chat/message.tsx`
- Create: `adil-frontend-next/components/chat/source-card.tsx`
- Create: `adil-frontend-next/components/chat/sources-panel.tsx`
- Create: `adil-frontend-next/components/chat/viability-card.tsx`

- [ ] **Step 1: message.tsx**

```tsx
// components/chat/message.tsx
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { sanitizeSchema, rehypeSafeLinks } from "@/lib/sanitize";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`py-3 ${isUser ? "bg-gray-50" : "bg-white"}`}>
      <div className="max-w-3xl mx-auto px-4">
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">
          {isUser ? "You" : "AskAdil"}
        </div>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[[rehypeSanitize, sanitizeSchema], rehypeSafeLinks]}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: source-card.tsx**

```tsx
// components/chat/source-card.tsx
import { Source } from "@/lib/types";

export default function SourceCard({ source }: { source: Source }) {
  const typeBadge = {
    statute: { label: "Statute", color: "bg-brand-100 text-brand-900" },
    case_law: { label: "Case law", color: "bg-scale-50 text-amber-900" },
    echr_judgment: { label: "ECHR", color: "bg-blue-50 text-blue-900" },
  }[source.type];

  const inner = (
    <>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${typeBadge.color}`}>{typeBadge.label}</span>
        <span className="text-xs text-gray-400">{source.citation}</span>
      </div>
      <div className="text-sm font-semibold text-gray-900">{source.title}</div>
      {source.excerpt && <div className="text-xs text-gray-600 mt-1 line-clamp-3">{source.excerpt}</div>}
    </>
  );

  return source.url ? (
    <a href={source.url} target="_blank" rel="noopener noreferrer"
       className="block p-3 border border-gray-200 rounded-lg hover:border-brand-500 transition-colors">
      {inner}
    </a>
  ) : (
    <div className="block p-3 border border-gray-200 rounded-lg">{inner}</div>
  );
}
```

- [ ] **Step 3: sources-panel.tsx**

```tsx
// components/chat/sources-panel.tsx
"use client";

import { useState } from "react";
import { Source } from "@/lib/types";
import SourceCard from "./source-card";

export default function SourcesPanel({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;
  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <button onClick={() => setOpen((v) => !v)}
              className="text-xs font-medium text-brand-700 hover:text-brand-900">
        {open ? "Hide" : "Show"} {sources.length} source{sources.length !== 1 ? "s" : ""}
      </button>
      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
          {sources.map((s, i) => (<SourceCard key={i} source={s} />))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: viability-card.tsx**

```tsx
// components/chat/viability-card.tsx
import { Viability } from "@/lib/types";

export default function ViabilityCard({ viability }: { viability: Viability }) {
  const bandColor = {
    Lower: "bg-green-50 border-green-200 text-green-900",
    Middle: "bg-yellow-50 border-yellow-200 text-yellow-900",
    Upper: "bg-orange-50 border-orange-200 text-orange-900",
    Exceptional: "bg-red-50 border-red-200 text-red-900",
  }[viability.vento_band];

  return (
    <div className={`mt-3 p-4 border rounded-lg ${bandColor}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold">Viability: {viability.score}/100</div>
        <div className="text-xs font-medium">{viability.vento_band} band</div>
      </div>
      <ul className="text-xs space-y-1">
        <li>{viability.statutory_footing ? "✅" : "❌"} Statutory footing</li>
        <li>{viability.case_law_precedent ? "✅" : "❌"} Case law precedent</li>
        <li>💰 Quantum potential: <strong>{viability.quantum_potential}</strong></li>
      </ul>
      {viability.evidence_checklist.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-semibold mb-1">Evidence to gather:</div>
          <ul className="text-xs space-y-1">
            {viability.evidence_checklist.map((item, i) => (<li key={i}>• {item}</li>))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add adil-frontend-next/components/chat/
git commit -m "feat(frontend-next): chat message, source card, sources panel, viability card"
```

---

## Task 15: Components batch C — Image upload, URL preview, Composer

**Files:**
- Create: `adil-frontend-next/components/image-upload.tsx`
- Create: `adil-frontend-next/components/url-preview.tsx`
- Create: `adil-frontend-next/components/composer.tsx`

- [ ] **Step 1: image-upload.tsx**

```tsx
// components/image-upload.tsx
"use client";

import { useState } from "react";
import { presignUpload } from "@/lib/api";
import type { ContentType } from "@/lib/types";

export interface UploadedImage {
  upload_id: string;
  object_key: string;
  preview_url: string;
  name: string;
}

const ACCEPTED: Record<string, ContentType> = {
  "image/png": "image/png",
  "image/jpeg": "image/jpeg",
  "image/webp": "image/webp",
};
const MAX_BYTES = 10_485_760; // 10MB

async function uploadOne(conversationId: string, file: File): Promise<UploadedImage> {
  if (!ACCEPTED[file.type]) throw new Error(`Unsupported type: ${file.type}`);
  if (file.size > MAX_BYTES) throw new Error(`${file.name} is larger than 10MB`);

  const presign = await presignUpload({
    conversation_id: conversationId,
    content_type: ACCEPTED[file.type],
    size_bytes: file.size,
  });

  const put = await fetch(presign.presigned_url, {
    method: "PUT",
    headers: { "Content-Type": file.type, "Content-Length": String(file.size) },
    body: file,
  });
  if (!put.ok) throw new Error(`R2 PUT failed: ${put.status}`);

  return {
    upload_id: presign.upload_id,
    object_key: presign.object_key,
    preview_url: URL.createObjectURL(file),
    name: file.name,
  };
}

export default function ImageUpload({
  conversationId,
  images,
  onChange,
}: {
  conversationId: string;
  images: UploadedImage[];
  onChange: (next: UploadedImage[]) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList) return;
    setErr(null);
    const files = Array.from(fileList).slice(0, 5 - images.length);
    setUploading(true);
    try {
      const results: UploadedImage[] = [];
      for (const f of files) {
        results.push(await uploadOne(conversationId, f));
      }
      onChange([...images, ...results]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <label className={`inline-flex items-center gap-2 text-sm cursor-pointer ${uploading ? "opacity-50" : ""}`}>
        <span className="px-2 py-1 border border-gray-300 rounded hover:border-brand-500">📎 Attach</span>
        <input type="file" multiple accept="image/png,image/jpeg,image/webp"
               className="hidden" disabled={uploading}
               onChange={(e) => handleFiles(e.target.files)} />
      </label>
      {err && <div className="text-xs text-red-700">{err}</div>}
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {images.map((img) => (
            <div key={img.upload_id} className="relative w-16 h-16">
              <img src={img.preview_url} alt={img.name} className="w-full h-full object-cover rounded" />
              <button type="button" onClick={() => onChange(images.filter((i) => i.upload_id !== img.upload_id))}
                      className="absolute -top-2 -right-2 bg-white rounded-full w-5 h-5 text-xs border border-gray-300">
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: url-preview.tsx**

```tsx
// components/url-preview.tsx
"use client";

import { useEffect, useState } from "react";
import { extractUrl } from "@/lib/api";

export default function UrlPreview({ url, onCancel }: { url: string; onCancel: () => void }) {
  const [data, setData] = useState<{ title: string; excerpt: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    extractUrl({ url })
      .then((d) => !cancelled && setData(d as { title: string; excerpt: string }))
      .catch((e) => !cancelled && setErr(e.message || "Extraction failed"));
    return () => { cancelled = true; };
  }, [url]);

  if (err) return <div className="p-2 text-xs text-red-700">Couldn't preview: {err}</div>;
  if (!data) return <div className="p-2 text-xs text-gray-500">Previewing {url}…</div>;

  return (
    <div className="p-2 border border-gray-200 rounded bg-gray-50 text-xs">
      <div className="font-semibold">{data.title}</div>
      <div className="text-gray-600 line-clamp-2 mt-1">{data.excerpt}</div>
      <button onClick={onCancel} className="mt-2 text-brand-700 underline">Remove</button>
    </div>
  );
}
```

- [ ] **Step 3: composer.tsx**

```tsx
// components/composer.tsx
"use client";

import { useState, FormEvent } from "react";
import ImageUpload, { UploadedImage } from "./image-upload";
import UrlPreview from "./url-preview";

interface Props {
  conversationId: string;
  disabled: boolean;
  onSubmit: (payload: { text: string; images: UploadedImage[]; url?: string }) => void;
}

const URL_RE = /(https?:\/\/\S+)/i;

export default function Composer({ conversationId, disabled, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [pastedUrl, setPastedUrl] = useState<string | null>(null);

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    const match = pasted.match(URL_RE);
    if (match && !pastedUrl) setPastedUrl(match[0]);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() && images.length === 0) return;
    onSubmit({ text: text.trim(), images, url: pastedUrl ?? undefined });
    setText("");
    setImages([]);
    setPastedUrl(null);
  };

  return (
    <form onSubmit={submit} className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto flex flex-col gap-2">
        {pastedUrl && <UrlPreview url={pastedUrl} onCancel={() => setPastedUrl(null)} />}
        <div className="flex items-end gap-2">
          <ImageUpload conversationId={conversationId} images={images} onChange={setImages} />
          <textarea
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onPaste={handlePaste}
            placeholder="Type your question…"
            disabled={disabled}
            className="flex-1 min-h-10 max-h-40 p-2 border border-gray-300 rounded text-sm focus:outline-none focus:border-brand-500"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(e); } }}
          />
          <button type="submit" disabled={disabled}
                  className="px-4 py-2 bg-brand-900 text-white rounded hover:bg-brand-700 disabled:opacity-50">
            ↑
          </button>
        </div>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add adil-frontend-next/components/image-upload.tsx adil-frontend-next/components/url-preview.tsx adil-frontend-next/components/composer.tsx
git commit -m "feat(frontend-next): image upload (R2 presign + direct PUT), URL preview, composer"
```

---

## Task 16: Report flow components (PII-isolated, final modal with Turnstile)

**Files:**
- Create: `adil-frontend-next/components/report/report-target-picker.tsx`
- Create: `adil-frontend-next/components/report/report-flow.tsx`
- Create: `adil-frontend-next/components/report/report-modal.tsx`

- [ ] **Step 1: report-target-picker.tsx**

```tsx
// components/report/report-target-picker.tsx
"use client";

const TARGETS = [
  { id: "bmt",           label: "🕌 British Muslim Trust", desc: "Government-appointed anti-Muslim hatred partner" },
  { id: "police-uk",     label: "🚔 Police UK",            desc: "National hate crime (England & Wales)" },
  { id: "police-scot",   label: "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Police Scotland",    desc: "Hate crime (Scotland)" },
  { id: "iru",           label: "🛡️ IRU",                  desc: "Islamophobia Response Unit (UK-wide)" },
  { id: "islamophobiaUK",label: "📍 Islamophobia UK",      desc: "Anonymous tracker (UK-wide)" },
  { id: "eass",          label: "📧 EASS",                 desc: "Equality Advisory Support Service (email)" },
  { id: "stop-hate-uk",  label: "📧 Stop Hate UK",         desc: "24/7 hate crime support (email)" },
  { id: "tellmama",      label: "🕌 Tell MAMA",            desc: "Anti-Muslim hate (UK-wide)" },
];

export default function ReportTargetPicker({ onSelect }: { onSelect: (targetId: string) => void }) {
  return (
    <div className="my-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
      {TARGETS.map((t) => (
        <button key={t.id} onClick={() => onSelect(t.id)}
                className="text-left p-3 border border-gray-200 rounded-lg hover:border-brand-500 transition-colors">
          <div className="text-sm font-semibold">{t.label}</div>
          <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: report-flow.tsx — state machine**

```tsx
// components/report/report-flow.tsx
"use client";

import { useState } from "react";
import ReportTargetPicker from "./report-target-picker";
import ReportModal from "./report-modal";

export interface ReportState {
  targetId: string;
  name: string;
  email: string;
  phone?: string;
  dob?: string;
  address?: string;
  summary: string;
  date?: string;
  location?: string;
}

type Step = "pick_target" | "collect_details" | "review";

export default function ReportFlow({ onComplete }: { onComplete: (reference: string) => void }) {
  const [step, setStep] = useState<Step>("pick_target");
  const [state, setState] = useState<ReportState>({
    targetId: "", name: "", email: "", summary: "",
  });

  if (step === "pick_target") {
    return (
      <div className="my-3">
        <div className="text-sm text-gray-700 mb-2">Where would you like to submit your report?</div>
        <ReportTargetPicker onSelect={(id) => { setState({ ...state, targetId: id }); setStep("collect_details"); }} />
      </div>
    );
  }

  if (step === "collect_details") {
    return (
      <div className="my-3 p-4 border border-brand-200 bg-brand-50 rounded-lg space-y-2">
        <div className="text-sm font-semibold">Incident details (kept private — not sent to AI)</div>
        <label className="block text-xs">
          Name
          <input className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                 value={state.name} onChange={(e) => setState({ ...state, name: e.target.value })} />
        </label>
        <label className="block text-xs">
          Email
          <input className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                 type="email" value={state.email} onChange={(e) => setState({ ...state, email: e.target.value })} />
        </label>
        <label className="block text-xs">
          What happened?
          <textarea className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                    rows={4} value={state.summary} onChange={(e) => setState({ ...state, summary: e.target.value })} />
        </label>
        <label className="block text-xs">
          Date (optional)
          <input type="date" className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                 value={state.date ?? ""} onChange={(e) => setState({ ...state, date: e.target.value })} />
        </label>
        <button className="mt-2 px-4 py-2 bg-brand-900 text-white rounded hover:bg-brand-700 text-sm"
                disabled={!state.name || !state.email || state.summary.length < 10}
                onClick={() => setStep("review")}>
          Review &amp; submit
        </button>
      </div>
    );
  }

  return (
    <ReportModal
      state={state}
      onCancel={() => setStep("collect_details")}
      onSubmitted={(ref) => {
        setStep("pick_target");
        onComplete(ref);
      }}
    />
  );
}
```

- [ ] **Step 3: report-modal.tsx — with Turnstile**

```tsx
// components/report/report-modal.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { ReportState } from "./report-flow";
import { submitReport } from "@/lib/api";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: { sitekey: string; callback: (t: string) => void; "error-callback"?: () => void }) => string;
      reset: (id: string) => void;
    };
  }
}

export default function ReportModal({
  state, onCancel, onSubmitted,
}: { state: ReportState; onCancel: () => void; onSubmitted: (reference: string) => void }) {
  const [consent, setConsent] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);

  useEffect(() => {
    // Load Turnstile script
    const existing = document.querySelector<HTMLScriptElement>("#turnstile-script");
    if (existing) {
      render();
      return;
    }
    const s = document.createElement("script");
    s.id = "turnstile-script";
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = render;
    document.head.appendChild(s);

    function render() {
      if (!widgetRef.current || !window.turnstile) return;
      widgetId.current = window.turnstile.render(widgetRef.current, {
        sitekey: process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "",
        callback: (t) => setToken(t),
        "error-callback": () => setErr("Turnstile verification failed"),
      });
    }
  }, []);

  const submit = async () => {
    if (!consent || !token) return;
    setSubmitting(true);
    setErr(null);
    try {
      const result = await submitReport({
        reporter: { name: state.name, email: state.email, phone: state.phone, dob: state.dob, address: state.address },
        incident: { target_org: state.targetId, summary: state.summary, date: state.date, location: state.location },
        turnstile_token: token,
      });
      onSubmitted(result.reference);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Submission failed");
      if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
      setToken(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-lg w-full p-6 space-y-3">
        <h2 className="text-lg font-semibold">Review and submit</h2>
        <dl className="text-sm space-y-1">
          <div><dt className="inline font-medium">Target:</dt> <dd className="inline">{state.targetId}</dd></div>
          <div><dt className="inline font-medium">Name:</dt> <dd className="inline">{state.name}</dd></div>
          <div><dt className="inline font-medium">Email:</dt> <dd className="inline">{state.email}</dd></div>
          {state.date && <div><dt className="inline font-medium">Date:</dt> <dd className="inline">{state.date}</dd></div>}
          <div><dt className="font-medium">Incident:</dt><dd className="whitespace-pre-wrap mt-1">{state.summary}</dd></div>
        </dl>
        <label className="flex items-start gap-2 text-xs">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>I confirm the details above are accurate and I consent to sharing them with the selected organisation.</span>
        </label>
        <div ref={widgetRef} />
        {err && <div className="text-xs text-red-700">{err}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button className="px-3 py-1.5 text-sm text-gray-700" onClick={onCancel} disabled={submitting}>Cancel</button>
          <button className="px-3 py-1.5 text-sm bg-brand-900 text-white rounded disabled:opacity-50"
                  disabled={!consent || !token || submitting} onClick={submit}>
            {submitting ? "Submitting…" : "Submit report"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add adil-frontend-next/components/report/
git commit -m "feat(frontend-next): PII-isolated report flow with Turnstile modal"
```

---

## Task 17: Main chat page (`app/chat/[id]/page.tsx`)

**Files:**
- Create: `adil-frontend-next/app/chat/[id]/page.tsx`

- [ ] **Step 1: Implement**

```tsx
// app/chat/[id]/page.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Message, { ChatMessage } from "@/components/chat/message";
import SourcesPanel from "@/components/chat/sources-panel";
import ViabilityCard from "@/components/chat/viability-card";
import JurisdictionSelector from "@/components/jurisdiction-selector";
import SearchingIndicator from "@/components/searching-indicator";
import ErrorBoundary from "@/components/error-boundary";
import Composer from "@/components/composer";
import ReportFlow from "@/components/report/report-flow";
import type { UploadedImage } from "@/components/image-upload";
import { readJurisdictionClient } from "@/lib/jurisdiction";
import type { Jurisdiction, Source, Viability } from "@/lib/types";
import { streamChat } from "@/lib/stream";
import { queryImage } from "@/lib/api";

export default function ChatPage() {
  const params = useParams<{ id: string }>();
  const conversationId = params?.id ?? "";

  const [jurisdiction, setJurisdiction] = useState<Jurisdiction | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sourcesByMsg, setSourcesByMsg] = useState<Record<number, Source[]>>({});
  const [viabilityByMsg, setViabilityByMsg] = useState<Record<number, Viability>>({});
  const [streaming, setStreaming] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setJurisdiction(readJurisdictionClient());
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  const send = async (text: string, images: UploadedImage[]) => {
    if (!jurisdiction) return;
    if (text.trim().toLowerCase() === "report") {
      setShowReport(true);
      return;
    }

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((m) => [...m, userMsg]);

    if (images.length > 0) {
      // Non-streaming vision call
      setStreaming(true);
      try {
        const resp = (await queryImage({
          query: text, conversation_id: conversationId,
          upload_ids: images.map((i) => i.upload_id),
        })) as { answer: string; sources?: Source[]; viability_assessment?: Viability };
        const idx = messages.length + 1;
        setMessages((m) => [...m, { role: "assistant", content: resp.answer }]);
        if (resp.sources) setSourcesByMsg((s) => ({ ...s, [idx]: resp.sources! }));
        if (resp.viability_assessment) setViabilityByMsg((v) => ({ ...v, [idx]: resp.viability_assessment! }));
      } finally {
        setStreaming(false);
      }
      return;
    }

    // Streaming chat path
    const assistantIdx = messages.length + 1;
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    setStreaming(true);
    abortRef.current = new AbortController();

    await streamChat({
      url: "/api/chat/stream",
      signal: abortRef.current.signal,
      body: {
        query: text,
        conversation_id: conversationId,
        conversation_history: messages.map((m) => ({ role: m.role, content: m.content })),
        jurisdiction,
        max_sources: 10,
        include_viability_score: true,
      },
      onEvent: (e) => {
        if (e.event === "token") {
          setMessages((m) => {
            const copy = [...m];
            copy[assistantIdx] = { ...copy[assistantIdx], content: (copy[assistantIdx]?.content ?? "") + e.data };
            return copy;
          });
        } else if (e.event === "source") {
          setSourcesByMsg((s) => ({ ...s, [assistantIdx]: [...(s[assistantIdx] ?? []), e.data] }));
        } else if (e.event === "viability") {
          setViabilityByMsg((v) => ({ ...v, [assistantIdx]: e.data }));
        }
      },
      onError: ({ message, status, retryAfter }) => {
        const hint = status === 429
          ? `Rate limited. Try again in ${retryAfter ?? "a few"} seconds.`
          : message;
        setMessages((m) => {
          const copy = [...m];
          copy[assistantIdx] = { ...copy[assistantIdx], content: `⚠️ ${hint}` };
          return copy;
        });
      },
    });

    setStreaming(false);
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollerRef} className="flex-1 overflow-y-auto">
        <ErrorBoundary>
          <div className="max-w-3xl mx-auto px-4 py-6">
            {messages.length === 0 && !jurisdiction && (
              <div className="bg-white p-4 rounded border border-gray-200">
                <p className="text-sm">
                  Welcome to AskAdil — free AI legal education for British Muslims.
                  Please select your jurisdiction to begin:
                </p>
                <JurisdictionSelector onSelect={setJurisdiction} />
              </div>
            )}
            {messages.length === 0 && jurisdiction && (
              <div className="text-sm text-gray-600">
                Ask me anything about UK discrimination and hate crime law. Type <strong>report</strong> to submit a hate crime report.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i}>
                <Message message={m} />
                {sourcesByMsg[i] && <div className="max-w-3xl mx-auto px-4"><SourcesPanel sources={sourcesByMsg[i]} /></div>}
                {viabilityByMsg[i] && <div className="max-w-3xl mx-auto px-4"><ViabilityCard viability={viabilityByMsg[i]} /></div>}
              </div>
            ))}
            {streaming && <SearchingIndicator />}
            {showReport && <ReportFlow onComplete={(ref) => {
              setShowReport(false);
              setMessages((m) => [...m, { role: "assistant", content: `✅ Report submitted. Reference: **${ref}**. Confirmation email sent.` }]);
            }} />}
          </div>
        </ErrorBoundary>
      </div>
      <Composer
        conversationId={conversationId}
        disabled={streaming || !jurisdiction}
        onSubmit={({ text, images }) => { void send(text, images); }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add adil-frontend-next/app/chat/
git commit -m "feat(frontend-next): main chat page ties everything together"
```

---

## Task 18: CI secret grep + ESLint rule

**Files:**
- Modify: `adil-frontend-next/eslint.config.mjs`
- Create: `adil-frontend-next/scripts/check-client-secrets.sh`

- [ ] **Step 1: ESLint rule**

Add a custom rule that forbids `process.env.RAG_API_KEY`, `TURNSTILE_SECRET`, `R2_FRONTEND_SECRET_ACCESS_KEY`, or `DATABASE_URL` outside `app/api/**`:

```js
// eslint.config.mjs
import next from "eslint-config-next";

export default [
  ...next(),
  {
    files: ["components/**/*.{ts,tsx}", "lib/api.ts", "lib/stream.ts",
            "lib/sanitize.ts", "lib/client-ip.ts", "lib/jurisdiction.ts",
            "app/layout.tsx", "app/page.tsx", "app/privacy/**", "app/chat/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "MemberExpression[object.property.name='env'][property.name='RAG_API_KEY']",
          message: "RAG_API_KEY must only be referenced in app/api/** route handlers.",
        },
        {
          selector: "MemberExpression[object.property.name='env'][property.name='TURNSTILE_SECRET']",
          message: "TURNSTILE_SECRET must only be referenced in app/api/** route handlers.",
        },
        {
          selector: "MemberExpression[object.property.name='env'][property.name='R2_FRONTEND_SECRET_ACCESS_KEY']",
          message: "R2_FRONTEND_SECRET_ACCESS_KEY must only be referenced in app/api/** route handlers.",
        },
        {
          selector: "MemberExpression[object.property.name='env'][property.name='DATABASE_URL']",
          message: "DATABASE_URL must not appear in the frontend at all.",
        },
      ],
    },
  },
];
```

- [ ] **Step 2: Build-time grep**

Create `scripts/check-client-secrets.sh`:

```bash
#!/bin/bash
# CI check: confirm server secrets never appear in built client bundles.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .next ]; then
  echo "❌ .next/ not found — run 'npm run build' first"
  exit 1
fi

FORBIDDEN=(RAG_API_KEY TURNSTILE_SECRET R2_FRONTEND_SECRET_ACCESS_KEY DATABASE_URL)
FAIL=0

for secret in "${FORBIDDEN[@]}"; do
  # Only scan client bundles (static and chunks served to browser)
  if grep -rq "$secret" .next/static 2>/dev/null; then
    echo "❌ Found '$secret' in client bundle (.next/static)"
    FAIL=1
  fi
done

if [ $FAIL -eq 1 ]; then
  echo "Client bundle contains server secrets. Fix before deploying."
  exit 1
fi

echo "✅ No server secrets found in client bundle"
```

Make it executable:

```bash
chmod +x adil-frontend-next/scripts/check-client-secrets.sh
```

- [ ] **Step 3: Commit**

```bash
git add adil-frontend-next/eslint.config.mjs adil-frontend-next/scripts/
git commit -m "feat(frontend-next): CI guards — ESLint + build-time secret grep"
```

---

## Task 19: Playwright smoke test

**Files:**
- Create: `adil-frontend-next/tests/smoke.spec.ts`

- [ ] **Step 1: Implement**

```ts
// tests/smoke.spec.ts
import { test, expect } from "@playwright/test";

test("home redirects to /chat/<uuid>", async ({ page }) => {
  await page.goto("/");
  await page.waitForURL(/\/chat\/[0-9a-f-]+/);
  expect(page.url()).toMatch(/\/chat\/[0-9a-f-]{36}/);
});

test("jurisdiction picker appears when cookie absent", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/");
  await expect(page.getByRole("button", { name: /england.*wales/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /scotland/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /northern ireland/i })).toBeVisible();
});

test("selecting jurisdiction unlocks input", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/");
  await page.getByRole("button", { name: /england.*wales/i }).click();
  const textarea = page.getByPlaceholder("Type your question…");
  await expect(textarea).toBeVisible();
  await expect(textarea).toBeEnabled();
});
```

- [ ] **Step 2: Update playwright config with webServer**

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
  },
  webServer: {
    command: "npm run start",
    url: "http://localhost:3000/api/health",
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    env: {
      // minimal envs so the server starts; route handlers will error if called
      NEXT_PUBLIC_RAG_API_URL: "http://localhost:9999",
      RAG_API_KEY: "test",
      R2_ACCOUNT_ID: "test",
      R2_BUCKET: "test",
      R2_ENDPOINT: "http://localhost:9999",
      R2_FRONTEND_ACCESS_KEY_ID: "test",
      R2_FRONTEND_SECRET_ACCESS_KEY: "test",
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: "1x00000000000000000000AA",
      TURNSTILE_SECRET: "test",
    },
  },
});
```

- [ ] **Step 3: Run**

```bash
cd adil-frontend-next
npm run build
npm run test -- tests/smoke.spec.ts
```

Expected: 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add adil-frontend-next/tests/smoke.spec.ts adil-frontend-next/playwright.config.ts
git commit -m "test(frontend-next): Playwright smoke tests"
```

---

## Task 20: Deploy to Railway + DNS

**Files:**
- (no code changes — Railway configuration)

- [ ] **Step 1: Create Railway service via API**

Use the Railway GraphQL API (see earlier deployment pattern in the repo). Service name: `adil-frontend-next`, repo: `muazamsarfaraz/adil`, root directory: `adil-frontend-next`.

Set env vars (all from `.env.example`):
- `NEXT_PUBLIC_RAG_API_URL` → production URL
- `RAG_API_KEY` → copied from `adil-rag-api` service
- `R2_*` → Cloudflare R2 credentials (frontend-scoped)
- `NEXT_PUBLIC_TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET` → from Cloudflare Turnstile dashboard

- [ ] **Step 2: Trigger first deploy**

```bash
railway service link adil-frontend-next
railway service redeploy --yes
```

Wait for SUCCESS, then:

```bash
railway domain
```

Copy the Railway-provided URL (e.g. `adil-frontend-next-production.up.railway.app`).

- [ ] **Step 3: Cloudflare DNS for preview**

Add a CNAME record in Cloudflare:
```
next.askadil.org    CNAME    adil-frontend-next-production.up.railway.app
```

Keep Cloudflare proxy enabled (orange cloud) so `CF-Connecting-IP` is populated.

- [ ] **Step 4: Smoke-test live**

```bash
curl https://next.askadil.org/api/health
```

Expected: `{"status":"ok","service":"adil-frontend-next"}`.

Then open in browser and go through the full flow: select jurisdiction → ask a question → verify streaming → try `report` → confirm Turnstile widget appears → submit.

- [ ] **Step 5: Add heartbeat target**

Update `adil-document-uploader`'s `HEARTBEAT_TARGETS` env var to include `next=https://next.askadil.org/api/health`.

- [ ] **Step 6: Commit the deployment notes**

```bash
# No code to commit — deployment is infrastructure. Document the cutover plan in the spec.
```

---

## Self-review

**Spec coverage:**

| Spec section | Tasks |
|--------------|-------|
| Fork ai-shamela + strip | Task 1 |
| Tailwind + MCB green | Task 2 |
| Dependencies, Dockerfile, Railway config | Task 3 |
| Types + Zod schemas | Task 4 |
| Client IP extraction (CF-Connecting-IP) | Task 5 |
| Proxy helper | Task 6 |
| R2 presigned URLs | Task 7 |
| Turnstile verification | Task 8 |
| SSE client with backoff | Task 9 |
| Sanitize, jurisdiction cookie, api | Task 10 |
| 9 route handlers | Task 11 |
| Layout + home + privacy | Task 12 |
| Nav + jurisdiction + searching + error boundary | Task 13 |
| Message, source card, sources panel, viability card | Task 14 |
| Image upload, URL preview, composer | Task 15 |
| Report flow + target picker + modal | Task 16 |
| Chat page (glue) | Task 17 |
| CI guards | Task 18 |
| Smoke test | Task 19 |
| Railway + DNS | Task 20 |

All spec sections mapped to tasks.

**Parallel execution map:**

```
Task 1 (scaffold)
  └─> Task 2 (theme)         ┐
  └─> Task 3 (deps + Docker) ┴─> [parallel]
        └─> Task 4 (types)
              ├─> Task 5 (client-ip)    ┐
              ├─> Task 6 (proxy)        │
              ├─> Task 7 (r2)           │
              ├─> Task 8 (turnstile)    ├─> [parallel — libs]
              ├─> Task 9 (stream)       │
              └─> Task 10 (sanitize etc)┘
                    └─> Task 11 (9 route handlers — parallel)
                          └─> Task 12 (layout/home/privacy)
                                ├─> Task 13 (batch A components)  ┐
                                ├─> Task 14 (batch B components)  ├─> [parallel]
                                ├─> Task 15 (batch C components)  │
                                └─> Task 16 (report components)   ┘
                                      └─> Task 17 (chat page)
                                            └─> Task 18 (CI guards)
                                                  └─> Task 19 (smoke tests)
                                                        └─> Task 20 (deploy)
```

Tasks 5-10 can all run in parallel. Route handlers in Task 11 are independent files — can be split further if wanted. Component batches 13-16 are independent.
