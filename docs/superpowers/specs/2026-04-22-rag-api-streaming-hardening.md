# adil-rag-api — Streaming Endpoint + Hardening (Spec 1)

**Date:** 2026-04-22
**Status:** Draft
**Scope:** Backend work required to support the Next.js frontend rewrite (see Spec 2: `2026-04-22-frontend-nextjs-rewrite.md`).

## Purpose

Add a streaming chat endpoint to `adil-rag-api` and harden the service for production use behind a new DB-free Next.js frontend. This spec covers only backend changes. Frontend UI work is out of scope here.

## Companion spec

`docs/superpowers/specs/2026-04-22-frontend-nextjs-rewrite.md` — the new Next.js frontend depends on this backend work.

## Work items

### 1. Streaming chat endpoint — `POST /api/v1/query/stream`

SSE-based streaming equivalent of the existing `/api/v1/query` endpoint.

**Request (identical shape to existing `/query`):**
```json
{
  "query": "…",
  "conversation_id": "uuid-v4",
  "conversation_history": [{"role":"user|assistant","content":"…"}],
  "jurisdiction": "england_wales|scotland|northern_ireland",
  "max_sources": 10,
  "include_viability_score": true
}
```

**Response:** `Content-Type: text/event-stream`, chunked:
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

**Implementation notes:**
- FastAPI `StreamingResponse` with `media_type="text/event-stream"`
- Each event: `event: <type>\ndata: <json or text>\n\n`
- Gemini streaming responses from the `google-genai` SDK map onto `token` events
- Sources + viability are emitted after the generation completes (or batched if they arrive async from the model)
- Heartbeat comment every 15 seconds (`: ping\n\n`) to keep connections open through Railway/Cloudflare proxies

### 2. Rate limiting (Postgres, backend-enforced)

New migration:

```sql
CREATE TABLE rate_limit_counters (
  bucket_key   TEXT        NOT NULL,
  bucket_start TIMESTAMPTZ NOT NULL,
  count        INT         NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket_key, bucket_start)
);
CREATE INDEX rate_limit_counters_bucket_start_idx ON rate_limit_counters (bucket_start);
```

**FastAPI middleware / dependency** applied to the protected endpoints:

| Endpoint | Bucket | Window | Limit |
|----------|--------|--------|-------|
| `/api/v1/query` + `/api/v1/query/stream` | `chat:ip:<addr>` | 1 min / 1 hour | 30 / 200 |
| `/api/v1/query/image` | `chat-image:ip:<addr>` | 1 min / 1 hour | 10 / 50 |
| `/api/v1/report/submit` | `report:ip:<addr>` | 1 hour / 24 hour | 3 / 10 |
| `/api/v1/extract-url` | `extract-url:ip:<addr>` | 1 min | 20 |
| `/api/v1/uploads/record` | `upload:ip:<addr>` | 1 hour | 10 |

**Fixed-window SQL:**

```sql
INSERT INTO rate_limit_counters (bucket_key, bucket_start, count)
VALUES ($1, date_trunc('minute', now()), 1)
ON CONFLICT (bucket_key, bucket_start)
DO UPDATE SET count = rate_limit_counters.count + 1
RETURNING count;
```

Reject with HTTP 429 + `Retry-After` header when count exceeds the bucket's limit.

**Cleanup:** hourly cron (via existing `adil-document-uploader` arq worker) runs `DELETE FROM rate_limit_counters WHERE bucket_start < now() - interval '48 hours'`.

### 3. Authentication and client IP trust

**Reject all requests without a valid `X-API-Key` — no anonymous fallback.**

The backend runs on Railway's internal private network (not exposed to public internet). Every request must carry a valid `X-API-Key`. Requests without it return HTTP 401 immediately; there is no socket-IP rate-limit fallback.

Client IP resolution (used only after `X-API-Key` is verified):
- Trust `X-AskAdil-Client-IP` header from the frontend proxy
- Metric: count requests with and without the header so we can observe misconfigurations
- If missing: log a warning and use the socket peer address (should only happen during debugging)

### 4. Upload metadata endpoint + R2 integration

```
POST /api/v1/uploads/record
Body: {conversation_id, upload_id, object_key, content_type, size_bytes}
→ 201 {upload_id}
```

Validates payload (Zod), inserts into the `uploads` table:

```sql
CREATE TABLE uploads (
  id              UUID         PRIMARY KEY,
  conversation_id UUID         NOT NULL,
  object_key      TEXT         NOT NULL,          -- R2 key
  content_type    TEXT         NOT NULL CHECK (content_type IN ('image/png','image/jpeg','image/webp')),
  size_bytes      INT          NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours')
);
CREATE INDEX uploads_conversation_id_idx ON uploads (conversation_id);
```

Rate-limited under `upload:ip:<addr>`.

**Cleanup:** R2 lifecycle rule deletes objects after 24h. Postgres row cleanup runs hourly:

```sql
DELETE FROM uploads WHERE expires_at < now();
```

(No external file-delete call required — R2 handles bytes, Postgres handles metadata.)

**`/api/v1/query/image` handler:**
- Zod-validates each `upload_id` as UUID
- Looks up rows by `(id, conversation_id)` — rejects with 403 if any row is missing or belongs to a different conversation
- Fetches object from R2 using backend credentials (`@aws-sdk/client-s3 GetObjectCommand`)
- Streams bytes to Gemini vision API
- On polyglot / rejected by Gemini: returns a structured error so the frontend can show "Image could not be analysed"

**Backend R2 env vars:**
```
R2_ACCOUNT_ID=<cloudflare account>
R2_BUCKET=adil-uploads-prod
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_BACKEND_ACCESS_KEY_ID=<GetObject+DeleteObject scope>
R2_BACKEND_SECRET_ACCESS_KEY=<…>
```

### 5. SSRF egress filter for URL extraction

`/api/v1/extract-url` (and any other URL-fetching code path) must block:
- `127.0.0.0/8` (loopback)
- `10.0.0.0/8` (RFC1918 private)
- `172.16.0.0/12` (RFC1918 private)
- `192.168.0.0/16` (RFC1918 private)
- `169.254.0.0/16` (link-local + cloud metadata)
- `::1` / `fc00::/7` / `fe80::/10` (IPv6 equivalents)

Resolve DNS first, validate the resolved IP is not in a blocked range, and use a custom `httpx` transport that re-validates on each redirect (prevent DNS rebinding). Python library: `advocate` or equivalent.

### 6. Viability + source payload shape (documented)

Make the streaming event `data` payloads explicit in `rag_service.py` docstrings and a new `docs/api/streaming-events.md`:

- `source.data` schema: `{type: "statute"|"case_law"|"echr_judgment", title, url, citation, excerpt?}`
- `viability.data` schema: `{score, vento_band, statutory_footing, case_law_precedent, quantum_potential, evidence_checklist}`
- `error.data.code` enum: `RATE_LIMIT | AUTH | INTERNAL | VALIDATION | UPSTREAM`

### 7. Remove CORS (backend is internal-only)

Current `adil-rag-api` has `allow_origins=["*"]`. Since the frontend proxies all traffic (no browser ever hits the backend directly), CORS headers are unnecessary.

- **Production:** backend runs on Railway's internal private network. Public endpoint removed. CORS middleware disabled.
- **Development:** `allow_origins=["http://localhost:3000"]` is permitted in dev via env-gated config (`ENABLE_DEV_CORS=true`). Default is off.

### 8. Gemini zero-data-retention prerequisite

**Launch blocker, documented here:** the Gemini API project used by AskAdil must be configured for **zero-data-retention (ZDR)** with Google Cloud. This ensures pasted PII (despite our UX separation of the report flow) is not retained by Google for training or human review. Without ZDR, users pasting PII into the chat is a GDPR/UK DPA violation.

Action: confirm ZDR status with Google before deploying the Next.js frontend publicly. Document in the privacy notice.

## Testing

- Unit tests for the rate-limit SQL helper (SQLite via aiosqlite)
- Integration test for `/api/v1/query/stream` using `httpx.AsyncClient` — asserts SSE events arrive in expected order and `Retry-After` is present on 429
- Integration test: rate-limit 429 response + `Retry-After` header
- Unit test: SSRF filter rejects each blocked CIDR range (IPv4 + IPv6)
- Integration test: `/api/v1/uploads/record` + `/api/v1/query/image` ownership check — cross-conversation reference returns 403
- Integration test: any request without `X-API-Key` returns 401 (no socket-IP fallback)
- Integration test: R2 GetObject path (mocked with moto / minio) returns bytes to Gemini

## Success criteria

- Streaming endpoint produces a complete answer with < 2s p50 time-to-first-token
- Rate limit table stays under 100K rows in steady state (cleanup working)
- All SSRF tests pass
- CORS denies requests from unlisted origins
- No regressions in existing `/api/v1/query` non-streaming endpoint

## Out of scope

- Converting existing non-streaming endpoint to streaming (kept as fallback)
- Cloudflare Turnstile (handled at frontend layer later if abuse observed)
- Token-cost quotas per user (only per-IP rate limits in v1)

## Risks

| Risk | Mitigation |
|------|------------|
| SSE keepalive dropped by intermediary proxies | 15-second heartbeat comments; client reconnect logic |
| Rate limit false positives behind NAT | Accepted — same-IP legitimate traffic will occasionally hit the limit; bucket windows are tuned to be forgiving |
| X-AskAdil-Client-IP spoofing | Only accepted with valid X-API-Key (our frontend); all other origins use socket IP |
| Upload table grows unbounded | 24h TTL + hourly cleanup removes expired rows and triggers file deletion |
| SSRF library false-positives blocking legitimate URLs | Maintain allowlist escape hatch via environment config if needed |
