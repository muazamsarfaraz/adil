# OG-RAG Migration Design

**Date:** 2026-05-19
**Author:** Muazam + Claude (Opus 4.7)
**Status:** Spec — awaiting user review
**Supersedes:** `adil-rag-api/docs/plans/2026-05-17-ograg-migration.md` (MVP shipped from that plan; this spec covers the full ontology cutover that the MVP did not deliver)
**ClickUp parent:** [869dbq5bk](https://app.clickup.com/t/869dbq5bk)

---

## 1. Problem

`adil-rag-api/rag_service.py` is bound to a Gemini File Search Tool (FST) store owned by a single GCP project. Two problems:

1. **Vendor coupling.** Rotating `GEMINI_API_KEY` to a key from a different GCP project breaks RAG with 403 PERMISSION_DENIED. We hit this in production on 2026-05-17.
2. **No structural retrieval.** FST returns dense-only chunks. Citations stay at document granularity ("Equality Act 2010") rather than the section/paragraph granularity that legal practice demands.

The MVP shipped on 2026-05-17 (commit `2973f48`) addresses (1) by adding a flat pgvector path behind `RAG_BACKEND=ograg`, but it does not address (2): the MVP corpus is only 66 inline-curated chunks, no ontology, no relations. The 1,000+ TNA judgments still live exclusively in FST.

This spec covers the full cutover: ontology-grounded retrieval over the TNA + statutes corpus, with vendor-diverse extraction, replacing FST end-to-end.

## 2. Goals

In priority order:

1. **Eliminate FST coupling.** Re-ingest from sources we own (TNA via document-uploader; Acts via legislation.gov.uk).
2. **Match or exceed FST quality** on a curated eval set before cutover. No regression.
3. **Cite at section / paragraph granularity.** Statute citations like `Equality Act 2010 s.13(1)`; case citations like `[2023] UKSC 15 ¶42`.
4. **Stay rotation-safe.** Generation key can rotate freely; retrieval data lives in Postgres we own.
5. **Preserve the public API surface.** `POST /api/v1/query`, `/query/stream`, `/vision`, `/analyze` keep request/response shape unchanged.

## 3. Non-goals (this spec)

Deferred to a v2 follow-up:

- CodeOfPractice, StatutoryInstrument, StatutoryGuidance, PracticeDirection, Pre-action Protocol ingestion (no clean source pipelines)
- Time-bounded statute versioning ("as in force on YYYY-MM-DD")
- Cross-jurisdiction variant linking (Scottish/NI mirrors)
- Full ILP-based hyperedge cover (using greedy approximation)
- Multi-tenant / per-user indexes
- Replacing Gemini Flash as the generation LLM (generation works on any key; only FST is the failure mode)
- Real-time index updates (existing monthly cron is fine)

## 4. Architecture

### Service responsibilities

```
┌─────────────────────────────────────────────────────────────┐
│ adil-document-uploader-worker (arq)                          │
│   uploader's Postgres:                                       │
│     judgments (existing)                                     │
│     acts (NEW — Statute/Section/Subsection sources)          │
│     extraction_spend (NEW — cost tracking)                   │
│                                                              │
│   Tasks:                                                     │
│     fetch_case_law()      ── unchanged                       │
│     fetch_acts()          ── NEW (P1.5)                      │
│     upload_pending()      ── KEEPS RUNNING through P11        │
│     extract_ontology()    ── NEW (P2-P4)                     │
│     backfill_ograg()      ── NEW one-shot driver (P5)        │
│                                                              │
│   writes via raw asyncpg to ↓                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ adil-rag-api's Postgres (separate DB, same Railway project)  │
│   ontology_node       (NEW)                                  │
│   ontology_edge       (NEW)                                  │
│   hyperedge           (NEW — pgvector ivfflat)               │
│   eval_run            (NEW)                                  │
│   ograg_chunks        (MVP — retired in P12)                 │
│   rate_limit_counters (existing)                             │
│   uploads             (existing)                             │
│   conversation_log    (existing)                             │
└─────────────────────────────────────────────────────────────┘
                              ↑ reads only
┌─────────────────────────────────────────────────────────────┐
│ adil-rag-api (FastAPI)                                       │
│   rag_service.py        — routes RAG_BACKEND fst|ograg       │
│   ograg/                                                     │
│     embed.py            — Gemini gemini-embedding-001        │
│     retriever.py        — Algo-1 cover + query rewriting     │
│     backend.py          — unary answer                        │
│     stream.py           — NEW: SSE token streaming           │
│     viability.py        — NEW: structured viability          │
│     evidence.py         — NEW: structured evidence checklist │
└─────────────────────────────────────────────────────────────┘
```

### Why this split

- **Single writer per ontology table** — the document-uploader worker is the only process that writes ontology rows. Eliminates write-concurrency reasoning.
- **Worker already runs an extraction-style pipeline** (`upload_pending`). Adding `extract_ontology` is additive to existing patterns.
- **Source data lives next to extraction** — `judgments.clean_text` is already in the worker's DB. Extraction reads locally, writes cross-DB.
- **rag-api stays read-only on ontology** — keeps the request-path service slim and avoids LLM batch jobs alongside live query traffic.

### Cross-DB write pattern

Worker uses raw asyncpg against `RAG_API_DATABASE_URL` (the env var already exists in `app/workers/tasks.py::rate_limit_cleanup` — same pattern, same DSN). No shared SQLAlchemy models. SQL is hand-written. This trades type safety for zero coupling between codebases.

Migration ordering is enforced operationally: rag-api's alembic migration `004_ograg_ontology_init.sql` must complete before the worker's `extract_ontology` is ever called. CI deploys rag-api before the worker.

## 5. Ontology

### Node types (11, dropped from maximalist 20)

| Type | Source | Notes |
|---|---|---|
| `Statute` | legislation.gov.uk (P1.5) | Equality Act 2010, MCA 2005, etc. |
| `Section` | Statute parse | `s.13`, `s.19`, ... |
| `Subsection` | Statute parse | `(1)`, `(2)(a)`, ... |
| `Case` | TNA judgments (existing) | One per neutral citation |
| `TribunalDecision` | TNA tribunals (UKEAT) | Distinguished from `Case` for ranking |
| `Paragraph` | Case parse (P2) | One per numbered paragraph in judgment |
| `Party` | Haiku extraction (P3) | Plaintiff / Defendant / Appellant |
| `Judge` | Haiku extraction (P3) | |
| `Court` | Derived from neutral citation | UKSC, EWCA, UKEAT, ... |
| `Topic` | Haiku classification (P3) | Closed vocab (see below) |
| `Jurisdiction` | Derived | England&Wales / Scotland / NI |

**Topic closed vocab** (lifted from existing `solicitor_directory.py` and SYSTEM_INSTRUCTION):
`discrimination_direct`, `discrimination_indirect`, `harassment`, `victimisation`, `immigration_asylum`, `immigration_settlement`, `employment_dismissal`, `employment_pay`, `deputyship`, `court_of_protection`, `hate_crime_racial`, `hate_crime_religious`, `human_rights_article8`, `human_rights_article14`, `mental_capacity_assessment`, `mental_capacity_dols`.

### Edge types

| Relation | From → To |
|---|---|
| `part_of` | Subsection → Section → Statute |
| `cites` | Case → (Case \| Statute \| Section) |
| `overrules` | Case → Case |
| `distinguished_by` | Case → Case |
| `has_topic` | Case → Topic |
| `decided_in_court` | Case → Court |
| `judged_by` | Case → Judge |
| `heard_party` | Case → Party |
| `applies_to_jurisdiction` | Case → Jurisdiction |

### Hyperedges

One per `(Paragraph, all node-ids it references)`. Stored as:

```sql
CREATE TABLE hyperedge (
  id bigserial PRIMARY KEY,
  node_ids bigint[] NOT NULL,
  paragraph_text text NOT NULL,
  source_doc_id bigint NOT NULL,  -- Paragraph.id
  embedding vector(768) NOT NULL,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX hyperedge_embedding_idx ON hyperedge
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

Hyperedges are the unit retrieval ranks over. A paragraph that names `Equality Act 2010 s.13` AND `[2023] UKSC 15 ¶17` AND topic `discrimination_direct` produces one hyperedge with three referenced node IDs and one embedded paragraph.

## 6. Extraction pipeline

Three passes per judgment, all idempotent on `(judgment_id, pass_version)`:

### Pass 1 — Structural split (P2)

Module: `app/services/ograg_extract/pass1_structural.py`. Engine: regex + spaCy. Cost: $0.

Inputs: `judgments.clean_text`. Outputs: `Case` node, `Paragraph` nodes, candidate `Statute`/`Section` references resolved against P1.5 nodes.

Regex patterns:
- Neutral citation: `\[(?P<year>\d{4})\]\s+(?P<court>UKSC|UKHL|EWCA|EWHC|UKEAT|UKUT)\s+(?P<num>\d+)`
- Section: `\bs\.?\s*(?P<sec>\d+[A-Z]*)(?:\((?P<sub>\d+[a-z]*)\))?`
- Statute title: exact match against `UK_LEGISLATION_URLS` keys

Failure mode: if structural split produces fewer than 5 paragraphs, mark judgment `EXTRACTION_FAILED` and skip subsequent passes — the parse upstream is broken, manual review required.

### Pass 2 — Claude Haiku (P3)

Module: `app/services/ograg_extract/pass2_haiku.py`. Engine: `claude-haiku-4-5`. Cost target: ~$0.02/judgment, ~$20 total.

Per call: 5 paragraphs from one judgment. Few-shot prompt with 3 hand-curated examples. Outputs `Topic`/`Party`/`Judge` nodes + relations (`has_topic`, `judged_by`, `heard_party`).

Retry: exponential backoff (3 attempts) on 429/5xx. Per-call output validated against pydantic schema; schema-fail counts as a retry.

### Pass 3 — Gemini Flash cross-references (P4)

Module: `app/services/ograg_extract/pass3_flash.py`. Engine: `gemini-2.5-flash`. Cost target: ~$0.005/judgment, ~$5 total.

Per call: one case (all its paragraphs + extracted citations from Pass 1). Outputs `cites` / `overrules` / `distinguished_by` edges between Case nodes.

After Pass 3, build hyperedges: for each `Paragraph` node, collect referenced node IDs from passes 1-3, embed paragraph text via Gemini `gemini-embedding-001`, write `hyperedge` row.

### Cost-ceiling kill switch

Before every Haiku/Flash call:

```sql
SELECT sum(cost_usd) FROM extraction_spend
WHERE ts > $backfill_start_ts
```

If ≥ `$OGRAG_MAX_SPEND_USD` (default 50): raise `ExtractionBudgetExceeded`, Telegram alert, exit task. Operator must bump `OGRAG_MAX_SPEND_USD` or audit before resuming.

## 7. Retrieval

`adil-rag-api/ograg/retriever.py` v2:

```python
async def retrieve(question: str, *, history: list[dict] | None, k_target_tokens: int = 6000) -> list[Hyperedge]:
    # 1. Multi-turn query rewriting
    if history:
        question = await rewrite_query(history[-4:], question)  # Gemini Flash, ~$0.0001

    # 2. Embed
    qvec = await embed(question)  # Gemini gemini-embedding-001

    # 3. ANN: top 50 candidates
    candidates = await store.ann_search(qvec, top_k=50)

    # 4. Greedy Algorithm-1 cover
    selected: list[Hyperedge] = []
    covered_entities: set[int] = set()
    tokens_used = 0
    candidates.sort(key=lambda c: c.similarity * (1 + len(c.node_ids - covered_entities)), reverse=True)
    for c in candidates:
        token_cost = estimate_tokens(c.paragraph_text)
        if tokens_used + token_cost > k_target_tokens:
            continue
        selected.append(c)
        covered_entities.update(c.node_ids)
        tokens_used += token_cost
    return selected
```

Trade-offs:
- Greedy approximation (paper's full ILP deferred). Empirically within ~10% of optimal on small problems; if eval shows shortfall, swap to PuLP-CBC ILP in v2.
- 50-candidate cap balances ANN cost vs. cover quality. Tune after first eval.

## 8. Public API parity

### Streaming (`POST /api/v1/query/stream`)

`ograg/stream.py` uses `client.models.generate_content_stream()`. Because retrieval is unary before generation, all `source` SSE events emit immediately after retrieval completes (before the first `token` event). This is actually simpler than the FST streaming path, which interleaves tool calls.

### Vision (`POST /api/v1/vision`)

If vision currently grounds against FST: route through `ograg.backend.answer()` with the image as additional content. The retrieval query is built from the user prompt only (images don't embed sensibly in the text retrieval path).

### Viability + evidence checklist

Currently MVP `ograg/backend.answer()` returns `None` for `ViabilityAssessment` and `[]` for `evidence_checklist`. P7 implements both:

- `ograg/viability.py`: structured-output Gemini Flash call with rubric (`vento_band`, `reasoning`, `confidence`).
- `ograg/evidence.py`: structured-output call extracting list of evidence items.

Both consume the same retrieved hyperedges as the main answer — no extra retrieval round-trip.

### Static inline injection

The curated `LEGISLATION_SNIPPETS` and `UK_CASE_LAW` in `rag_service.py` (added for MCA / Court of Protection coverage) are promoted to first-class ontology nodes during backfill (`Op — Promote MCA snippets`). They also remain inline-injected as belt-and-braces, mirroring current FST behaviour.

## 9. Evaluation + cutover gate

### Eval set

`adil-rag-api/evals/queries.jsonl`: 30 queries pulled from `conversation_log` table. Manual anonymisation pass (strip names, emails, addresses) before commit.

### Eval pipeline

`adil-rag-api/evals/run.py`:

1. For each query, hit both backends (`fst` and `ograg`).
2. Record answer, sources, latency_ms, cost_usd into `eval_run` table.
3. LLM judge (Gemini Flash) scores each pair on rubric:
   - `factual_correctness` (1-5)
   - `citation_specificity` (1-5)
   - `completeness` (1-5)
   - `harmfulness` (1-5, lower better)
4. Generate `evals/eval_review_<ts>.md` with aggregated scores + 10 random queries flagged for human spot-check.
5. **User spot-check**: pass/fail per backend on each of the 10. Recorded inline.

### Cutover gate (P10)

All must hold:
- OG-RAG ≥ FST on aggregate LLM judge score (sum of factual + citation + completeness, with harmfulness as a hard veto)
- User pass rate ≥ 8/10 on human spot-check
- No harmfulness ≥ 4 on either backend in the spot-check set
- OG-RAG P95 latency ≤ 2× FST P95 baseline (measured in P0.5)

If any fails: investigate, do not cut over.

## 10. Phasing

Detailed sub-tasks in ClickUp [869dbq5bk](https://app.clickup.com/t/869dbq5bk). Summary:

| Phase | Days | Description |
|---|---|---|
| P0.5 | 0.5 | Measure FST latency baseline |
| P1 | 1 | Ontology schema (alembic 004) |
| P1.5 | 1 | Acts fetcher (legislation.gov.uk) |
| P2 | 1 | Extraction pass 1 (regex + structural) |
| P3 | 2 | Extraction pass 2 (Claude Haiku) |
| P4 | 1 | Extraction pass 3 (Gemini Flash cross-refs) |
| P5 | 1 | Backfill execution + dual-write to FST |
| P6 | 2 | Retriever v2 (Algo-1 cover + query rewriting) |
| P7 | 2 | Parity (viability + evidence + streaming + vision) |
| P8 | 2 | Eval harness + first run |
| P9 | 7 cal | Shadow week (logged not served) |
| P10 | 0.5 | Cutover flip |
| P11 | 7 cal | Hot-standby week (FST dual-write continues) |
| P12 | 1 | Decommission FST |

**Engineering: ~15 days (main phases) + ~1.5 days (Op sub-tasks, parallelisable). Calendar: ~4 weeks** — shadow + standby drive the calendar.

### Dual-write window

`upload_pending` to FST **must keep running** from P5 through P11. Otherwise rollback after P10 would land on a stale FST. The cost is real but small (FST stores cap at GB scale; we're around 200 MB). FST decommission happens only in P12.

## 11. Error handling

| Failure mode | Detection | Response |
|---|---|---|
| Extraction LLM 5xx | retry with backoff (3x) | mark judgment `EXTRACTION_FAILED`; backfill driver continues |
| Extraction pydantic-schema fail | counts as retry | same |
| Cost ceiling exceeded | pre-call DB check | raise `ExtractionBudgetExceeded`; Telegram alert; exit task |
| Empty ANN retrieval | post-retrieval check | log; fall back to inline `LEGISLATION_SNIPPETS` only; flag in answer metadata |
| Hyperedge `embedding` API fail | retry once | propagate as 503 from `/query` |
| Cross-DB connection down | asyncpg raises | retry once; on second failure, fail the task — operator alert |
| Hallucinated citation in answer | regex check post-generation | log; don't suppress (user can verify) |
| Vision query without RAG context | check `RAG_BACKEND` | route through OG-RAG with image; same answer path |

## 12. Testing strategy

### Unit (each phase)
- Pass 1: 5 hand-curated judgment fixtures → expected node/edge sets.
- Pass 2: prompt construction, retry/backoff, schema validation.
- Pass 3: cross-reference extraction on known case clusters.
- Retriever: empty result, very-short query, history-only follow-up, oversized hyperedges.
- Backend: viability shape parity, evidence parity, streaming token order.

### Integration (P5 prep)
- End-to-end extract → store → retrieve → generate on a 5-judgment fixture.

### Golden snapshot
- Extracted ontology for 3 known judgments stored as JSON fixtures.
- Re-extraction must match fixtures byte-for-byte (idempotency).

### Parity (P7 + P8)
- 5 fixed queries run through both backends; assert answer shape parity (not text — text varies).
- Eval suite is the canonical comparison.

### Property
- Hyperedge embeddings: ‖v‖ = 1.0 ± 1e-6 (cosine-normalised).
- Entity set on each hyperedge: deterministic order on re-extraction.

## 13. Open items deferred to v2

Tracked in a follow-up ClickUp ticket (not yet created):

- CodeOfPractice, StatutoryInstrument, StatutoryGuidance ingestion
- Pre-action Protocols, Practice Directions
- Time-bounded `StatuteVersion` ("in force at date X")
- Cross-jurisdiction variant linking (Scottish/NI mirrors)
- Full ILP-based hyperedge cover (PuLP-CBC)
- Multi-tenant indexes if MCB partners want isolated corpora

## 14. Decisions and rationale

| # | Decision | Why |
|---|---|---|
| 1 | Architecture B (extraction in worker, retrieval in rag-api) | Source data already in worker DB; existing extraction-style pipeline; clean writer/reader split |
| 2 | Rich ontology (11 types), not Maximalist (20) | Half of maximalist nodes have no ingestion source — would ship empty tables |
| 3 | Vendor-diverse extraction (Haiku + Flash) | Genuine multi-vendor — escapes Gemini coupling on the *extraction* stage too, not just retrieval |
| 4 | Keep `gemini-embedding-001` 768-d | Already shipped in MVP; switching mid-flight means re-embedding everything; embedding lock-in is recoverable (embeddings are just numbers, can be re-computed offline) unlike FST data lock-in |
| 5 | Eval B (LLM-as-judge + user spot-check 10/30) | Only option with both speed and human floor on legal accuracy |
| 6 | Cross-DB writes via raw asyncpg | Matches existing `rate_limit_cleanup` pattern; no shared-models coupling |
| 7 | Dual-write through P11 | Rollback safety; FST decommission only after 7 clean days |
| 8 | Greedy cover, not full ILP | Empirically within 10% on small problems; defer ILP unless eval shows shortfall |
| 9 | $50 hard cost ceiling on backfill | Belt-and-braces; expected cost ~$26 |
| 10 | Defer CoP/SI/Guidance/PD/StatuteVersion to v2 | No clean source pipelines; would balloon scope by 2+ weeks |

---

## Approval gate

Reply with:
- ✅ **approved** → I invoke writing-plans to generate the phase-by-phase implementation plan
- ✏️ **revisions** → tell me what to change; I update the spec
- 🛑 **different approach** → we brainstorm
