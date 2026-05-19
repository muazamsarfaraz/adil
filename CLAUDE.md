# AskAdil — Monorepo

Muslim Council of Britain legal-tech platform providing free UK discrimination law guidance.
Live at **askadil.org**.

## Services

| Directory | Purpose | Railway Service ID |
|-----------|---------|-------------------|
| `adil-frontend-next/` | Next.js chat UI (askadil.org) | deployed via `adil-frontend-next/` subdir |
| `adil-rag-api/` | FastAPI RAG backend + report submission | deployed via `adil-rag-api/` subdir |
| `adil-report-bridge/` | AI browser-automation form filler | `546e173e-2e3d-41fe-bdc8-e6b8cc61aaa9` |
| `adil-document-uploader/` | TNA case-law fetcher → Gemini FST | deployed from repo root via wrapper |
| `adil-outreach-engine/` | AI outreach automation (LangGraph + arq) | deployed via `adil-outreach-engine/` subdir |
| `adil-landing/` | Static landing page | deployed via `adil-landing/` subdir |

## Deploy

All services use `railway up` CLI — never GitHub auto-deploy.

**Standard services** (deploy from their own subdir):
```bash
cd adil-rag-api && railway up
cd adil-frontend-next && railway up
```

**Repo-root services** (the upload bundle must be the repo root — running
`railway up` from inside the subdir wraps the bundle in an extra folder and
breaks Dockerfile resolution; see [[2576]]):

- **adil-document-uploader** + **adil-document-uploader-worker** — use the
  wrapper that cd's to repo root:
  ```bash
  ./adil-document-uploader/deploy.sh                                 # api
  ./adil-document-uploader/deploy.sh adil-document-uploader-worker   # worker
  ```
  Or on Windows: `./adil-document-uploader/deploy.ps1 [<service>]`.
  Service instance has `rootDirectory=adil-document-uploader` +
  `railwayConfigFile=adil-document-uploader/railway.toml` set via the
  Railway API.

- **adil-report-bridge** — deploy from repo root with explicit service ID:
  ```bash
  railway up --service 546e173e-2e3d-41fe-bdc8-e6b8cc61aaa9
  ```
  Requires `rootDirectory=adil-report-bridge` and
  `railwayConfigFile=adil-report-bridge/railway.toml` on the service instance
  (done via API; see memory `feedback_bridge_deploy_method.md`).

## Architecture

```
User → askadil.org (Next.js)
         ↓  /api/* proxy
       adil-rag-api (FastAPI + Gemini RAG)
         ↓  BRIDGE_URL internal
       adil-report-bridge (browser-use + Gemini Flash → hate crime portals)

adil-document-uploader → TNA → Gemini File Search Tool Store (1000+ judgments)
```

The Gemini File Search Tool Store IS the vector DB — no separate vector store.
Always append to the single existing store; never create a new one.

## Environment

Key shared env vars (set per service in Railway):
- `GEMINI_API_KEY` — Google Gemini
- `FILE_SEARCH_STORE_ID` — single FST store ID (shared read access)
- `DATABASE_URL` — Postgres (rate limits, conversation logs)
- `ADIL_API_KEY` / `RAG_API_KEY` — inter-service auth

## Git

Main branch: `master`. Feature branches: `feat/*`.
Commits use conventional format: `feat(scope):`, `fix(scope):`, `chore:`.

## Cost & Value

### Production infrastructure (monthly standing costs)
| Item | Cost/month |
|------|-----------|
| Railway Pro (6 services + Postgres) | ~$50–80 |
| Gemini API (Flash 2.5, current traffic) | ~$5–20 |
| Cloudflare R2 | ~$0–3 |
| SendGrid, Turnstile | Free tier |
| **Total infra** | **~$55–100/mo** |

### Claude Code development spend
| Month | All-projects Claude Code spend |
|-------|-------------------------------|
| Feb 2026 | $72 |
| Mar 2026 | $2,573 |
| Apr 2026 | $9,823 |

This project (adil) specifically: **$841** total as of 2026-04-27.

### What a traditional team would cost
Scope built: Next.js chat UI, FastAPI RAG backend, SSE streaming, AI browser-automation
agent (11 hate crime portals), TNA case-law ingestion pipeline, Gemini FST RAG,
outreach engine, 6 Railway services, Cloudflare DNS + Turnstile, bespoke editorial UI.

| Route | Cost | Timeline |
|-------|------|----------|
| UK agency (tech lead + PM + designers + devs + QA) | ~$405,000 | 9 months |
| Experienced freelancers | ~$210,000 | 6–7 months |
| **Claude Code + developer direction** | **~$841 tokens + ~$5k dev time** | **~3 weeks** |

**Efficiency ratio: 40–80× cheaper than freelancers, 100× cheaper than agency.**

Monthly traditional equivalent (agency team sustaining/iterating):
- Ongoing feature dev (1 senior dev + PM): ~$20,000–30,000/month
- Maintenance only (part-time): ~$5,000–8,000/month
- Claude Code equivalent for same output: ~$500–2,000/month in tokens

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
