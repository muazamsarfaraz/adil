# AskAdil — Session Resume / Context-Clear Handoff

> Written 2026-05-24. Drop into a fresh Claude Code session to pick up where this one left off.
> Full architecture in `docs/ARCHITECTURE.md` (read that first for the system map).

---

## 1. TL;DR — current production state

**Live at askadil.org**. End-to-end smoke just passed (Section 13 EA 2010, Section 19 EA 2010, indirect discrimination follow-up all return real Claude Sonnet answers with cited case law).

**Vendor stack in the OG-RAG hot path:**

| Stage | Vendor | Model |
|---|---|---|
| Embeddings | **OpenAI** | `text-embedding-3-small` (1536-d) |
| Generation | **Anthropic** | `claude-sonnet-4-6` |
| Vision | Anthropic | `claude-sonnet-4-6` (image content blocks) |
| Eval judge | Anthropic | `claude-haiku-4-5` |

**Zero `generativelanguage.googleapis.com` calls from rag-api in production.** Gemini only remains in `adil-report-bridge` (browser automation for hate-crime portals — isolated, never serves askadil.org).

**Corpus: 26,021 chunks** in `ograg_chunks`. **99.8% TNA judgment coverage** (2,114 / 2,118). 66 hand-curated MCB seed chunks preserved.

**MSentry**: brain healthy (20-30s heartbeat). Both `AskAdil/adil` (parent) and `AskAdil/adil-rag-api` (sub-project) provisioned, routing to ClickUp list `901218094337`.

---

## 2. What this session accomplished

Chronological — useful if you need to undo something.

| Commit | What |
|---|---|
| `babd5ea` | Fixed `.railwayignore` — was inverted (excluded `adil-rag-api/`, included 482MB frontend). |
| `300f6c0` | Fixed `ontology_writer.py` edge insert column names (`src_id/dst_id/kind` → `source_id/target_id/relation`). |
| `f160e9d` | `OntologyStore` (asyncpg) + migration `007_hyperedge.sql`. 9 tests passing. |
| `bdecdee` | `rotate_llm_keys.py` — manifest-based service routing + Windows CLI shim + `--yes` flag. |
| `dd13f5a` | `rotate_llm_keys.py --keys-file` bulk mode + OpenRouter. |
| `56394e7` | OG-RAG migration spec (`docs/superpowers/specs/2026-05-19-og-rag-migration-design.md`). |
| `5877abb` | OG-RAG foundation implementation plan (`docs/superpowers/plans/2026-05-19-og-rag-foundation.md`). |
| `a27f31a` | **Phase 1**: OpenAI 1536-d embeddings (rewrote `ograg/embed.py`, migration 008 dim resize, spec §14 decision log). |
| `732a52b` | **Phase 2**: Claude Sonnet 4.6 for generation (rewrote `ograg/backend.py` for AsyncAnthropic, added anthropic/openai to requirements). |
| `4a0399c` | Rewrote `test_ograg_parity.py` to mock AsyncAnthropic (the Gemini sync wrapper was removed). 3/3 pass. |
| `a1c8f8b` | `ograg/store.py` filter `WHERE embedding IS NOT NULL` + `scripts/railway_fix_builder.py` GraphQL helper. |
| `d1c92a6` | **Phase 3** (eval judge → Claude Haiku 4.5) + **P5 backfill script** (TNA judgments → ograg_chunks). |
| `81e55ba` | UI smoke for askadil.org + GitHub Actions workflow (Playwright golden path, 15-min cron). |
| `0e75da6` | `docs/ARCHITECTURE.md` — full system PRD. |

Plus the data-side work (not in git):

- **All 2,114 TNA judgments** chunked + embedded via OpenAI + inserted to `ograg_chunks` (~25,955 rows).
- **8 UK Acts** fetched from legislation.gov.uk (by parallel auto-worker earlier in session).
- **`OPENAI_API_KEY` provisioned** on `adil-rag-api` Railway env.
- **`ANTHROPIC_API_KEY` provisioned** on `adil-rag-api`.
- **Railway service-instance config fixed** on `adil-rag-api`: builder back to Dockerfile via `railwayConfigFile=adil-rag-api/railway.toml`, `rootDirectory=adil-rag-api`. (Done via `scripts/railway_fix_builder.py`.)
- **MSentry project_aliases**: `adil-rag-api → AskAdil/adil` (for `/feedback` name routing).
- **MSentry projects table**: new sub-project row `AskAdil/adil-rag-api` with `local_path=E:\dev\AskAdil\adil\adil-rag-api`, shared ClickUp list (so cwd-based session matching works from the subdir too).

---

## 3. Open ClickUp tickets — created this session

All in the `adil` list (`901218094337`).

| ID | Title | Priority | What it's for |
|---|---|---|---|
| [869ddu0yw](https://app.clickup.com/t/869ddu0yw) | UI smoke for askadil.org — finish GH push + add secrets | normal | Local commit `81e55ba` blocked from pushing to GitHub (token lacks `workflow` scope). Resume: `gh auth refresh -h github.com -s workflow`, then `git push`, then add 4 secrets to GitHub repo. |
| [869ddu12e](https://app.clickup.com/t/869ddu12e) | Leverage LegalScraper (sibling project) for the solicitor finder | high | The big one. ~50K solicitors in `E:\dev\AskAdil\LegalScraper`. Three integration paths: static find-a-solicitor page on `adil-landing` (~1 day), outreach-engine SRA verify swap (~0.5 day), chatbot tool on rag-api (~2 days). |
| [869ddvj2y](https://app.clickup.com/t/869ddvj2y) | "Nearest me" solicitor finder — OSRM + LegalScraper | high | Depends on 869ddu12e. Adds geo-ranking via self-hosted OSRM at `https://osrmproj-production.up.railway.app` (verified 70-80ms). |
| [869ddw1xg](https://app.clickup.com/t/869ddw1xg) | WhatsApp channel for AskAdil — Meta Cloud API bridge | high | New service `adil-whatsapp-bridge` (already added to root CLAUDE.md services table). 3-phase rollout: Twilio sandbox → Meta direct → public launch. Requires MCB Meta Business Verification (3-10 day Meta review). |

Earlier sub-tickets under OG-RAG migration parent ([869dbq5bk](https://app.clickup.com/t/869dbq5bk)) — most done, a couple still open:

- [869dbqa4q](https://app.clickup.com/t/869dbqa4q) P8 eval harness — set status to "in progress" but harness exists; needs first real run + spot-check
- [869dbqa3y](https://app.clickup.com/t/869dbqa3y) P6 retriever v2 (hyperedge cover + multi-turn query rewriting) — schema exists, not populated, not wired
- [869dbqa7k](https://app.clickup.com/t/869dbqa7k) P11 hot-standby week
- [869dbqa8e](https://app.clickup.com/t/869dbqa8e) P12 FST decommission — defer until Phase 2 has been live ≥7 days clean

---

## 4. Locally committed but NOT pushed (push blocker)

```
git log origin/master..HEAD --oneline
```

Will show **one local commit** (`81e55ba` — the UI smoke + workflow files). GitHub refused the push because the OAuth credential lacks the `workflow` scope to create files under `.github/workflows/`.

**To unblock**:
1. Run `gh auth refresh -h github.com -s workflow` in any terminal
2. Complete the device flow at <https://github.com/login/device>
3. `git push`

Tracked in [869ddu0yw](https://app.clickup.com/t/869ddu0yw).

---

## 5. Things to know (avoid repeating mistakes)

### 5.1 The root `CLAUDE.md` is stale

User edited the services table (added `adil-whatsapp-bridge` row) but the **architecture section is still wrong**:

- Says "FastAPI + Gemini RAG" — actually FastAPI + OpenAI embed + Anthropic Sonnet
- Says "Gemini File Search Tool Store IS the vector DB" — actually pgvector
- Says "Gemini API (Flash 2.5, current traffic) ~$5-20" — actually Anthropic ~$50
- Says project total cost "$841 as of 2026-04-27" — needs refresh

`docs/ARCHITECTURE.md` (written this session, commit `0e75da6`) is the correct, current picture. Either delete the stale sections in root `CLAUDE.md` or point them at `ARCHITECTURE.md`.

### 5.2 Railway service-instance config can drift

`adil-rag-api`'s builder reverted to Railpack mid-session for unknown reason (causing the May 17 deploys to silently fail while production kept serving the older Gemini build). Fixed via `scripts/railway_fix_builder.py`. If a deploy completes but new code isn't running, **check the build logs for "railpack process exited with an error"** — that's the symptom. Re-run the script.

### 5.3 `railway up` upload uses the local `.railwayignore`

NOT the committed version. Per-service deploys flip the ignore file convention: comment out the deploying service's line, uncomment the others. Always verify before deploy that your subdir is INCLUDED in the upload.

### 5.4 OpenAI `int(UUID)` is 128 bits

UUID has an `__int__` that returns the integer representation. **This overflows Postgres bigint.** I hit this on the first backfill run — burned an hour. Always store UUIDs as TEXT in JSON columns when cross-referencing.

### 5.5 PowerShell here-strings + Python `-c` is fragile

PowerShell `*` is a wildcard, `:` is operator-like; passing python -c with SQL queries in PowerShell will misparse. Use a temp `.py` file every time. There's a `_clean_backfill.py` pattern in the repo to follow.

### 5.6 `gh auth refresh` has a 5-minute device-flow deadline

If you don't complete it in 5 min the process exits with "context deadline exceeded" silently. Better to run it interactively in your own shell, not via the agent's command output.

### 5.7 Migration 008 NULL'd the embedding column

When the dim was resized 768 → 1536, all existing data became NULL. `store.py` now defensively filters `WHERE embedding IS NOT NULL` so retrieval doesn't crash on the dim transition. If you ever change embedding model again, **plan a TRUNCATE + re-seed**, not an ALTER.

### 5.8 MSentry routing has TWO mechanisms

- `project_aliases` table: name → name. Used for `/feedback` POST routing (when a service sends feedback with project="adil-rag-api", it resolves to "AskAdil/adil").
- `projects` table with `local_path`: cwd → project. Used for Claude Code session matching when MSentry's agent is figuring out which project a shell belongs to.

I confused these mid-session. Aliases don't help cwd matching; you need a real `projects` row.

---

## 6. Common ops cookbook

### 6.1 Rotate LLM keys

```powershell
# 1. Copy template
Copy-Item scripts/keys.template.json scripts/.keys.local.json
# 2. Edit and paste real keys (file is gitignored)
notepad scripts/.keys.local.json
# 3. Dry run
python scripts/rotate_llm_keys.py --keys-file scripts/.keys.local.json --dry-run
# 4. Apply
python scripts/rotate_llm_keys.py --keys-file scripts/.keys.local.json --yes
# Script offers to shred .keys.local.json at the end.
```

### 6.2 Re-run the TNA backfill (idempotent, `--resume` by default)

```powershell
cd E:\dev\AskAdil\adil\adil-rag-api
$env:UPLOADER_DB = "postgresql://postgres:YMijBiHelQHKspMtHcYJWyXaNGHUHvgh@junction.proxy.rlwy.net:36691/railway"
$env:RAG_API_DB  = "postgresql://postgres:ZyrebqAKCKRowomubAQOuoufDLWlBFpJ@ballast.proxy.rlwy.net:51670/railway"
railway run --service adil-rag-api python scripts/backfill_judgments_to_ograg.py
```

### 6.3 Force adil-rag-api back to Dockerfile builder (if Railpack creeps back in)

```
python scripts/railway_fix_builder.py
```

Resets service-instance `rootDirectory`, `railwayConfigFile`, and builder via Railway GraphQL.

### 6.4 Deploy adil-rag-api

```powershell
cd E:\dev\AskAdil\adil
# Confirm .railwayignore has 'adil-rag-api/' COMMENTED OUT
railway up --service adil-rag-api
# Watch logs:
railway logs --service adil-rag-api --build
```

### 6.5 Check what's actually in the corpus

Quick script lives in cookbook form — paste into a `_check.py` file:

```python
import asyncio, os, asyncpg
async def main():
    conn = await asyncpg.connect(os.environ["RAG_API_DB"])
    try:
        total = await conn.fetchval("SELECT count(*) FROM ograg_chunks")
        distinct = await conn.fetchval(
            "SELECT count(DISTINCT source->>'judgment_id') FROM ograg_chunks "
            "WHERE source->>'judgment_id' IS NOT NULL")
        print(f"chunks={total} distinct_judgments={distinct}")
    finally:
        await conn.close()
asyncio.run(main())
```

### 6.6 Public Postgres URLs (for running scripts from local machine)

| DB | Public URL |
|---|---|
| rag-api Postgres | `postgresql://postgres:ZyrebqAKCKRowomubAQOuoufDLWlBFpJ@ballast.proxy.rlwy.net:51670/railway` |
| document-uploader Postgres-38de | `postgresql://postgres:YMijBiHelQHKspMtHcYJWyXaNGHUHvgh@junction.proxy.rlwy.net:36691/railway` |
| cc-monitor (MSentry) Postgres-bcPS | `postgresql://postgres:VIvSgKwwRajptYlyomGlDzjsBquqochm@viaduct.proxy.rlwy.net:39442/railway` |

These are **public proxy URLs** intended for ops. Pull fresh via `railway run --service <Postgres-name> python -c "import os; print(os.environ['DATABASE_PUBLIC_URL'])"` if any of these rotate.

---

## 7. Next session — natural starting points

In suggested order of leverage:

1. **Refresh the gh `workflow` scope and push `81e55ba`** (2 minutes, unblocks UI smoke alerting).
2. **Refresh root `CLAUDE.md`** to match `docs/ARCHITECTURE.md` (10 minutes). Delete the Gemini-as-RAG paragraph + the FST architecture diagram; point readers at ARCHITECTURE.md.
3. **LegalScraper Path 3** (find-a-solicitor on `adil-landing`, ticket [869ddu12e](https://app.clickup.com/t/869ddu12e)): drop `LegalScraper/data/directory_landing.json` into landing, build the vanilla-JS filter page. ~1 day. Lowest risk, biggest visible win.
4. **WhatsApp Phase A** (Twilio sandbox bridge, ticket [869ddw1xg](https://app.clickup.com/t/869ddw1xg)): stand up `adil-whatsapp-bridge` against Twilio sandbox. ~1 day. Proves the flow without waiting for Meta verification.
5. **P8 first eval run** (existing ticket [869dbqa4q](https://app.clickup.com/t/869dbqa4q)): 30 anonymised queries through both backends, Claude Haiku judges, 10-question spot-check. Gives the cutover-gate signal we never measured post-Phase-2.

If picking one for "show MCB stakeholders something tangible": #3 wins. If picking one for "harden what we just shipped": #2 then #5.

---

## 8. Files to skim if you only have 5 minutes

- `docs/ARCHITECTURE.md` (this is the canonical "how it works")
- `docs/superpowers/specs/2026-05-19-og-rag-migration-design.md` §14 (vendor decisions)
- `adil-rag-api/ograg/backend.py` (the Claude Sonnet generation path)
- `adil-rag-api/scripts/backfill_judgments_to_ograg.py` (how the corpus was populated)
- `.railway.json` at repo root (services + IDs)
- `tests/smoke/adil.spec.ts` (the golden-path UI test, pending push)

---

## 9. Decision log carried forward

Three open product decisions waiting on the operator:

1. **WhatsApp number ownership** — dedicated AskAdil number vs reuse existing MCB line. Affects consent flow.
2. **WhatsApp `report` flow** — collect form fields in chat, or hand off to website via magic link. Ticket assumes in-chat; website is simpler.
3. **Solicitor finder visibility** — surface to chatbot answers always, or only when user explicitly asks for one? Privacy + scope concerns.

None block any code work; just need answers before launch of those features.
