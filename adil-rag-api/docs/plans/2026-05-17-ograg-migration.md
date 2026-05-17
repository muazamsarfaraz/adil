# OG-RAG Migration Plan — adil-rag-api

**Date:** 2026-05-17
**Author:** Muazam + Claude Code
**Status:** Draft — awaiting scope approval

---

## 1. Why this exists

The current `rag_service.py` is bound to a **Gemini File Search Tool Store** (`project-adil-legal-knowledg-8gl78e375lwz`). This store is owned by a specific Google Cloud project, and **rotating the Gemini API key to a key from a different GCP project breaks RAG** with `403 PERMISSION_DENIED`. We hit this on 2026-05-17: rotating GEMINI_API_KEY for security took prod down on the `/api/v1/query` path until manually rolled back.

Two motivations:
1. **Operational**: future key rotations must not depend on a single GCP project's account integrity.
2. **Strategic**: legal RAG benefits from ontology-grounded retrieval. UK law has a strong inherent ontology (statute → section → subsection; case → court → year → citation → topic; cross-references between them). Treating documents as a hypergraph rather than a chunk soup should improve both accuracy and citation precision.

OG-RAG ([arXiv:2412.15235](https://arxiv.org/abs/2412.15235), [microsoft/ograg2](https://github.com/microsoft/ograg2)) is a published technique with a reference implementation, claiming +55% fact recall, +40% correctness, +27% reasoning accuracy over chunk-based RAG. Microsoft Research authored. Apt for legal because the paper explicitly calls out "legal" as a target domain.

## 2. Goals (in priority order)

1. **Eliminate FST coupling** — the new backend must not depend on any Google Cloud project's data ownership. Re-ingest from sources we own (TNA fetched via adil-document-uploader).
2. **Match or exceed current quality** on the existing legal eval set before cut-over. No quality regression.
3. **Cite better** — answers should cite section/subsection/case paragraph, not just "Equality Act 2010".
4. **Stay rotation-safe** — Gemini API key for generation can rotate freely; embeddings can live anywhere; retrieval data lives in Postgres we control.
5. **Don't break the existing API surface** — `POST /api/v1/query`, `POST /api/v1/query/stream`, `POST /api/v1/analyze` keep the same request/response shape.

## 3. Non-goals (this plan)

- Replacing Gemini Flash as the generation LLM. Generation works fine on any key; the FST integration is the only failure mode.
- Rebuilding the ingest pipeline — `adil-document-uploader` already fetches TNA case law and Acts. We change where the indexed output goes, not where it comes from.
- Multi-tenancy / per-user document indexes.
- Real-time index updates — current pipeline is monthly cron, that's fine.

## 4. Architecture

### Current

```
User query
  → POST /api/v1/query (X-API-Key auth)
  → rag_service.query(question, jurisdiction, topic)
     ├─ static LEGISLATION_SNIPPETS inline-injected
     ├─ static UK_CASE_LAW inline-injected
     └─ Gemini File Search Tool (store ID hard-bound)
        ↳ retrieve chunks
        ↳ Gemini Flash 2.5 generates
  → Answer + citations
```

### Proposed

```
User query
  → POST /api/v1/query
  → rag_service.query(question, jurisdiction, topic)
     ├─ if RAG_BACKEND=ograg:
     │    └─ OntologyRAG.retrieve(question)
     │       ├─ embed query (Gemini text-embedding-004 OR voyage-2)
     │       ├─ pgvector ANN over hyperedge embeddings
     │       ├─ optimization step: minimal hyperedge cover (paper Algo 1)
     │       └─ return ordered context chunks + citations
     ├─ else (RAG_BACKEND=fst, default during migration):
     │    └─ existing Gemini File Search path
     └─ Gemini Flash 2.5 .generate(context, question)
  → Answer + citations
```

Key change: **Postgres + pgvector becomes the vector store and ontology graph**. Already have Postgres on Railway; pgvector is a single extension `CREATE EXTENSION vector;`. Postgres-first rule applies.

## 5. The ontology

The minimum useful UK legal ontology:

```
Statute
  ├─ Section (1..N)
  │   └─ Subsection (1..N)
  ├─ year
  ├─ short_title
  ├─ legislation_gov_uk_url
  └─ amends → Statute
  └─ amended_by → Statute

Case
  ├─ neutral_citation (e.g. [2023] UKSC 15)
  ├─ court (UKSC | UKEAT | EWCA | EWHC | UKHL | …)
  ├─ year
  ├─ jurisdiction (E&W | Scotland | NI)
  ├─ parties → list[Party]
  ├─ judges → list[Judge]
  ├─ topics → list[Topic]
  ├─ cites → list[Case | Statute]
  ├─ overrules → list[Case]
  └─ paragraphs → list[Paragraph]
      └─ paragraph_number, text

Topic (closed vocab: discrimination_direct, discrimination_indirect,
       harassment, victimisation, immigration_asylum, immigration_settlement,
       employment_dismissal, employment_pay, deputyship, court_of_protection,
       hate_crime_racial, hate_crime_religious, …)
```

This is small (~10 node types, ~8 edge types) — JSON-LD or a Python dataclass module suffices. No need for full LegalRuleML.

## 6. Phased delivery

### Phase 0 — Restore prod (30 min) ⚠️ BLOCKER

Either roll back to original Gemini key, OR generate a key in the correct GCP project. Without this, askadil.org keeps 500ing on `/api/v1/query`. This must happen regardless of the OG-RAG decision — even if we go full OG-RAG, the migration takes days, and we can't leave prod down.

**Decision required from user.** All subsequent phases assume prod is restored.

### Phase 1 — Foundation: Postgres + pgvector (½ day)

- Enable `pgvector` extension on the shared Postgres on Railway.
- Add 3 new alembic-managed tables:
  - `ontology_node` — JSONB attributes, type enum, embedding vector(768)
  - `ontology_edge` — source_id, target_id, relation enum, optional weight
  - `hyperedge` — set of node_ids, embedding vector(768), source_document_id
- Cover-index for `hyperedge.embedding USING ivfflat (embedding vector_cosine_ops)`.
- A new Python module `ograg/store.py` with read/write helpers.

**Deliverable:** schema migration + 5 unit tests.

### Phase 2 — Ingest pipeline (1 day)

Adapter that takes the same TNA-fetched documents `adil-document-uploader` currently pushes to FST and instead:
1. Splits each document by structural boundary (Act → Sections → Subsections; Case → Paragraphs).
2. For each chunk, calls a **light LLM extraction pass** (Gemini Flash) to identify ontology entities: "this paragraph mentions Equality Act 2010 s.13, in the context of direct discrimination based on race".
3. Writes `ontology_node` + `ontology_edge` rows.
4. Groups co-occurring entities into hyperedges per paper Algorithm 0.
5. Embeds each hyperedge's surface text and stores vector.

**Cost estimate:** 1000 judgments × ~50 chunks each × ~$0.0001 per Gemini Flash call ≈ **$5–10 one-time** for the full re-ingest. Re-ingests on monthly cron incremental, ~$0.50/mo.

**Deliverable:** `scripts/build_ograg_index.py`, idempotent (skips already-indexed documents), runnable locally against the dev Postgres and remotely against Railway via `railway run`.

### Phase 3 — Retrieval (1 day)

`ograg/retriever.py`:
1. Embed query.
2. ANN search hyperedge.embedding → top 30 candidates.
3. Run a simplified version of the paper's Algorithm 1: greedily pick hyperedges to maximize entity coverage subject to a token budget. (Full ILP can come later.)
4. Return: list of (hyperedge_text, citations, score).

A `RAG_BACKEND` env flag in `rag_service.py` switches between FST (legacy) and OG-RAG (new). Default `fst` during the parallel-running period.

**Deliverable:** retriever + 8 unit tests covering edge cases (empty result, very short query, very long query, malformed citation in a candidate).

### Phase 4 — Evaluation harness (½ day)

Need to compare the two backends fairly:

- Curate ~30 representative queries from the existing askadil.org logs (anonymise first).
- For each query, run both backends and score:
  - Did it cite a real case/statute? (hand-curated truth list)
  - Did it answer the question? (LLM-as-judge, Gemini Flash 2.5 with explicit rubric)
  - Latency
  - Token cost per query

**Deliverable:** `evals/ograg_vs_fst.py` + a markdown report after first run.

### Phase 5 — Cutover (½ day, gated by Phase 4)

- If OG-RAG ≥ FST on quality: flip `RAG_BACKEND=ograg` in Railway env on `adil-rag-api`, redeploy, monitor MSentry for 24h, archive `rag_service.py`'s FST code path.
- If OG-RAG < FST: stop, investigate, do not cut over.

### Phase 6 — Decommission FST (½ day, only after 7 days of cleanly running on OG-RAG)

- Remove FST integration code from `rag_service.py`.
- Remove `FILE_SEARCH_STORE_ID` env var.
- Remove `adil-document-uploader`'s FST push (it keeps writing to TNA → ontology pipeline instead).
- Document the new architecture in `CLAUDE.md`.

**Total estimate:** ~4 working days end-to-end if no surprises. Phase 1-3 (foundation through retrieval) is the longest pole; phases 4-6 are quick once the system works.

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Ontology extraction misses citations a human would catch | Medium | High (legal accuracy) | Eval harness gates cutover; keep `LEGISLATION_SNIPPETS` static inline as belt-and-braces |
| pgvector index doesn't scale past 50k hyperedges | Low | Medium | We have <10k after full TNA ingest. Worry about it at 10x scale. |
| Re-ingest takes longer / costs more than estimated | Medium | Low | Cap at $50, fail loudly if exceeded; tune chunk size |
| Eval queries don't match production query mix | High | Medium | Sample from real logs (anonymised), refresh quarterly |
| User-facing latency increases | Medium | High | Pre-compute hyperedge embeddings; ANN is O(log n); target P95 < 2s end-to-end |
| Gemini Flash extraction misclassifies legal entities | Medium | Medium | Use few-shot prompting with 5 hand-curated examples; sample 50 outputs for manual review before full re-ingest |

## 8. Open questions for the user

1. **Phase 0**: Roll back to original Gemini key, or generate from correct GCP project? Either way I push and verify. **Need to choose before anything else.**
2. **Embedding model**: stay on Gemini `text-embedding-004` (768-dim, ~$0.01/M tokens, same vendor risk we're trying to escape) OR switch to OpenAI `text-embedding-3-small` (1536-dim, similar cost) OR Voyage `voyage-3-lite` (512-dim, cheapest, legal-specialised variant exists)? Recommend **Voyage** for diversification.
3. **Ontology scope**: ship the slim ontology in §5 OR invest in a richer one (additional node types like Statutory Instrument, Code of Practice, Statutory Guidance)? Recommend **slim first**, expand based on eval failures.
4. **Parallel-run window**: how long do we run both backends? Recommend **7 days** in shadow mode (OG-RAG retrieves but doesn't serve) + 7 days as the active backend before decommissioning FST.
5. **Who reviews Phase 4 evals**? Quality-grading legal answers needs domain knowledge — not just LLM-as-judge.

## 9. What I'm NOT planning to do yet

- Write any code. This is a planning document. After your approval (or revisions), Phase 1 starts.
- Touch `rag_service.py` until the new module exists and is unit-tested.
- Run any large LLM batches that cost real money.

---

## Approval gate

Reply to this plan with:
- ✅ approved as-is → I start Phase 1
- ✏️ revisions → I update the plan
- 🛑 different approach → we brainstorm
