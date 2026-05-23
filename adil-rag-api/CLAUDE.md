# adil-rag-api

FastAPI RAG backend for AskAdil. Handles legal Q&A, content analysis, vision queries,
report submission proxying, and rate limiting.

## Deploy

```bash
cd E:\dev\mcbx\adil\adil-rag-api
railway up
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/query` | X-API-Key | Multi-turn legal Q&A (text) |
| POST | `/api/v1/query/stream` | X-API-Key | SSE streaming Q&A |
| POST | `/api/v1/vision` | X-API-Key | Image/document analysis |
| POST | `/api/v1/report/prefill` | X-API-Key | Extract report fields from conversation history |
| POST | `/api/v1/submit-report` | X-API-Key | Proxy to adil-report-bridge |
| GET | `/api/v1/report-targets` | X-API-Key | List available report targets |
| GET | `/api/v1/solicitors` | X-API-Key | Firm directory (curated + SRA) |
| GET | `/api/v1/solicitors/search` | X-API-Key | Per-solicitor search (LegalScraper data) |
| GET | `/api/v1/solicitors/facets` | X-API-Key | Distinct areas + languages |
| GET | `/api/v1/solicitors/verify/{sra_id}` | X-API-Key | Verify solicitor by SRA ID |
| GET | `/health` | none | Liveness probe |
| GET | `/health/report-bridge` | none | Bridge reachability check |
| GET | `/stats` | none | Uptime + request counts |

Rate limits (Postgres-backed, per API key):
- Query/stream/vision: 30 req/min
- Report/upload: 5 req/min
- Health/stats: 60 req/min

## Key Files

- `app.py` — FastAPI app, all endpoints, CORS gating
- `rag_service.py` — Gemini File Search Tool Store query logic
- `rate_limit.py` — Postgres-backed rate limiter
- `auth.py` — API key verification
- `models.py` — Pydantic request/response schemas
- `telegram_notifier.py` — Error alerts with 10-min dedup
- `email_receipt.py` — SendGrid report confirmation emails
- `r2_client.py` — Cloudflare R2 (image upload ownership)
- `ssrf_filter.py` — Blocks private IP ranges on outbound fetches
- `content_extractor.py` — YouTube/Instagram/webpage content extraction
- `geolocation.py` — Jurisdiction detection from IP
- `conversation_log.py` — Postgres conversation history
- `solicitor_directory.py` — Solicitor lookup
- `report_generator.py` — Structured report generation

## Environment Variables

| Var | Required | Description |
|-----|----------|-------------|
| `ADIL_API_KEY` | Yes | Comma-separated valid API keys |
| `DATABASE_URL` | Yes | Postgres connection string |
| `GEMINI_API_KEY` | Yes | Google Gemini key |
| `FILE_SEARCH_STORE_ID` | Yes | Single FST store ID — never create a new one |
| `BRIDGE_URL` | Yes | adil-report-bridge internal URL |
| `BRIDGE_API_KEY` | Yes | X-Bridge-Key for bridge auth |
| `R2_ENDPOINT` | For vision | Cloudflare R2 endpoint |
| `R2_BUCKET` | For vision | R2 bucket name |
| `R2_ACCESS_KEY_ID` | For vision | R2 credentials |
| `R2_SECRET_ACCESS_KEY` | For vision | R2 credentials |
| `SENDGRID_API_KEY` | For receipts | Email receipts on report submission |
| `TELEGRAM_BOT_TOKEN` | For alerts | Error notification bot |
| `TELEGRAM_CHAT_ID` | For alerts | Target chat for alerts |
| `GEMINI_MODEL` | No | Default: `gemini-2.5-flash` |
| `RAG_BACKEND` | No | `fst` (default) or `ograg` — routes /query to FST or pgvector OG-RAG |
| `RAG_SHADOW` | No | `1` enables P9 shadow logging: fire-and-forget OG-RAG run alongside every FST query, logged to `eval_run` table. Never affects user response. |
| `ENABLE_DEV_CORS` | Dev only | Enables permissive CORS (never set in prod) |
| `LOG_LEVEL` | No | Default: INFO |

## SSE Streaming

`POST /api/v1/query/stream` emits these event types:
- `token` — text chunk
- `source` — citation object
- `viability` — viability assessment object
- `error` — error with `code` and `message`
- `done` — stream complete

## Report Prefill

`POST /api/v1/report/prefill` takes `conversation_history` and uses Gemini Flash to extract:
- `details` — 2–4 paragraph first-person incident narrative (includes image analyses already embedded in assistant messages)
- `location` — where the incident occurred (null if not mentioned)
- `date_time` — formatted as `YYYY-MM-DDTHH:MM` (null if not mentioned)

Personal PII (name, DOB, email) is never inferable from chat and is intentionally excluded.
Falls back to empty strings/nulls on any extraction failure so the form still renders.

## Solicitor Directory

`solicitor_directory.py` loads from three sources on startup:

1. **Curated seed** — `docs/plans/muslim-solicitors-seed-database.json` (manually maintained, Muslim-focus firms)
2. **SRA register scrape** — `docs/sra_firms.json` (167 law firms, auto-scraped)
3. **LegalScraper landing export** — `docs/legalscraper_landing.json` (~1,500 per-solicitor profiles with practice areas, languages, accreditations, SRA IDs). Sourced from the sibling `LegalScraper` project. Refresh recipe: `LegalScraper/INTEGRATION.md` §4.3 — re-run `scripts/export_landing_json.py --muslim-only` and copy the file across; override path with `LEGALSCRAPER_LANDING_PATH` env var if needed.

The first two power `/api/v1/solicitors` (firm-level browse). The third powers `/api/v1/solicitors/search` (per-solicitor filter by area + language + postcode prefix + name + `muslim_only`), `/api/v1/solicitors/facets`, and `/api/v1/solicitors/verify/{sra_id}`.

SRA data covers: employment discrimination, equality act, hate crime, mental capacity, human rights, civil liberties, court of protection. Scraped from the public SRA register at `https://www.sra.org.uk/consumers/register/`. **Attribution required**: "data supplied by the Solicitors Regulation Authority".

To refresh the SRA data:
```bash
cd E:\dev\mcbx\adil
python scripts/scrape_sra.py --out adil-rag-api/docs/sra_firms.json
```
Takes ~3 minutes. Re-deploy the RAG API after.

SRA API (when portal is back): `https://sra-prod-apim.developer.azure-api.net` — free, 24h fresh, same data but with more fields.

## RAG Architecture

Gemini File Search Tool Store holds 1,000+ UK case law judgments. There is **one store**
(`FILE_SEARCH_STORE_ID`). Always append to it; never create a new one.

## P8 eval harness — FST vs OG-RAG

`evals/` runs every query in `queries.jsonl` through both backends, judges the
pairs with Gemini Flash, and emits a markdown report with auto cutover-gate
verdicts + 10 random pairs for human spot-check.

```bash
python -m evals.run                                    # both backends, ~10-15 min
python -m evals.judge  --run-id <run_id>               # LLM judge with rubric
python -m evals.report --run-id <run_id>               # eval_review_<run_id>.md
```

Eval rows land in `eval_run` table with `meta->>'run_id'` tagging. See
`evals/README.md` for the full workflow and the cutover-gate definition.
