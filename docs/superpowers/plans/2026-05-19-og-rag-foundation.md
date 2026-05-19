# OG-RAG Foundation Implementation Plan (Plans series 1/4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the schema + statute-source foundation for OG-RAG cutover — FST latency baseline measured, ontology tables live in rag-api Postgres, ~8 UK Acts parsed into Statute/Section/Subsection nodes. Nothing user-visible changes.

**Architecture:** Two services, two Postgres databases. document-uploader (alembic) gains a new `acts` table + `fetch_acts` arq worker; that worker writes nodes cross-DB into rag-api's Postgres via raw asyncpg (matches existing `rate_limit_cleanup` pattern). rag-api gains raw-SQL migration `004_ograg_ontology_init.sql` creating `ontology_node`/`ontology_edge`/`hyperedge`/`eval_run`.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, alembic, pgvector, httpx, lxml (Acts XML parsing), pytest.

**Spec:** [`docs/superpowers/specs/2026-05-19-og-rag-migration-design.md`](../specs/2026-05-19-og-rag-migration-design.md)

**ClickUp:**
- P0.5 → [869dbqa0u](https://app.clickup.com/t/869dbqa0u)
- P1 → [869dbqa1c](https://app.clickup.com/t/869dbqa1c)
- P1.5 → [869dbqa1w](https://app.clickup.com/t/869dbqa1w)

**Series scope:** This plan covers phases P0.5, P1, P1.5 only (~2.5 engineering days). Follow-ups:
- Plan 2/4: Extraction passes (P2–P5)
- Plan 3/4: Retrieval + parity + eval (P6–P8)
- Plan 4/4: Rollout (P9–P12)

Each subsequent plan is written when its prerequisites complete.

---

## File Structure

### Created
- `adil-rag-api/evals/__init__.py` — package marker
- `adil-rag-api/evals/fst_baseline.py` — script: run N queries through FST, write `fst_baseline.json`
- `adil-rag-api/evals/fst_baseline.json` — output file, committed to repo
- `adil-rag-api/evals/queries_seed.jsonl` — 5 hand-curated queries for baseline (kept; superset later becomes the 30-query eval set)
- `adil-rag-api/tests/test_fst_baseline.py` — unit tests for `percentile` + `BaselineRunner` glue
- `adil-rag-api/migrations/004_ograg_ontology_init.sql` — raw-SQL migration (idempotent, `IF NOT EXISTS`)
- `adil-rag-api/ograg/store_v2.py` — asyncpg helpers for ontology tables (read+write)
- `adil-rag-api/tests/test_ograg_store_v2.py` — unit tests against real Postgres
- `adil-document-uploader/alembic/versions/b1a2c3d4e5f6_add_acts_table.py` — uploader-side `acts` table
- `adil-document-uploader/app/models/act.py` — SQLAlchemy model for `acts`
- `adil-document-uploader/app/services/legislation_client.py` — httpx client for legislation.gov.uk CLML/RDF
- `adil-document-uploader/app/services/acts_parser.py` — XML → (Statute, Section[], Subsection[]) extraction
- `adil-document-uploader/app/services/ograg_writer.py` — cross-DB asyncpg writer to rag-api's ontology_node table
- `adil-document-uploader/tests/test_legislation_client.py`
- `adil-document-uploader/tests/test_acts_parser.py`
- `adil-document-uploader/tests/test_ograg_writer.py` — integration against real rag-api test DB
- `adil-document-uploader/tests/fixtures/equality_act_2010_clml.xml` — fixture
- `adil-document-uploader/tests/fixtures/mca_2005_clml.xml` — fixture

### Modified
- `adil-document-uploader/app/workers/tasks.py` — append `fetch_acts(ctx)` task
- `adil-document-uploader/app/workers/settings.py` — register `fetch_acts` in `WorkerSettings.functions` + monthly cron
- `adil-document-uploader/app/config.py` — add `legislation_gov_uk_base_url` + `rag_api_database_url` (already exists via env, but ensure typed)
- `adil-document-uploader/app/models/__init__.py` — export `Act`
- `adil-document-uploader/requirements.txt` — add `lxml`

---

## Task 1: FST latency baseline runner skeleton (P0.5)

**Files:**
- Create: `adil-rag-api/evals/__init__.py`
- Create: `adil-rag-api/evals/queries_seed.jsonl`
- Create: `adil-rag-api/evals/fst_baseline.py`
- Create: `adil-rag-api/tests/test_fst_baseline.py`

- [ ] **Step 1: Write the failing test for the percentile helper**

Create `adil-rag-api/tests/test_fst_baseline.py`:

```python
"""Tests for FST baseline measurement helpers."""
from __future__ import annotations

import pytest

from evals.fst_baseline import percentile


class TestPercentile:
    def test_p50_of_sorted_list(self):
        assert percentile([10, 20, 30, 40, 50], 50) == 30

    def test_p95_of_100_items(self):
        # 1..100; the 95th percentile by nearest-rank should be 95
        assert percentile(list(range(1, 101)), 95) == 95

    def test_p99_of_100_items(self):
        assert percentile(list(range(1, 101)), 99) == 99

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="empty"):
            percentile([], 50)

    def test_unsorted_input_sorted_internally(self):
        # P50 must be invariant to input order
        assert percentile([50, 10, 30, 40, 20], 50) == 30
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd adil-rag-api
pytest tests/test_fst_baseline.py -v
```

Expected: ImportError or ModuleNotFoundError on `evals.fst_baseline`.

- [ ] **Step 3: Create the evals package marker**

Create `adil-rag-api/evals/__init__.py` (empty file).

- [ ] **Step 4: Create the seed query set**

Create `adil-rag-api/evals/queries_seed.jsonl` — 5 hand-curated queries that cover the main practice areas:

```jsonl
{"id": "q1", "topic": "discrimination_direct", "query": "What is direct discrimination under the Equality Act 2010?"}
{"id": "q2", "topic": "hate_crime_religious", "query": "What constitutes religiously aggravated harassment in England?"}
{"id": "q3", "topic": "mental_capacity_assessment", "query": "How is capacity assessed under the Mental Capacity Act 2005?"}
{"id": "q4", "topic": "employment_dismissal", "query": "What is the burden of proof for unfair dismissal on grounds of religion?"}
{"id": "q5", "topic": "court_of_protection", "query": "When is a deputyship order appropriate?"}
```

- [ ] **Step 5: Implement `percentile`**

Create `adil-rag-api/evals/fst_baseline.py`:

```python
"""Measure FST latency baseline.

Runs each query in queries_seed.jsonl through the live FST path N times,
records per-stage latency, writes aggregated P50/P95/P99 to fst_baseline.json.

The output file is committed to the repo; it is the reference number against
which OG-RAG's cutover gate ('P95 <= 2x FST baseline') is evaluated.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


def percentile(samples: list[float | int], p: int) -> float:
    """Nearest-rank percentile. Pure function — pure for testing."""
    if not samples:
        raise ValueError("percentile of empty sample set is undefined")
    if not 0 <= p <= 100:
        raise ValueError(f"p must be in [0, 100], got {p}")
    s = sorted(samples)
    # Nearest-rank: ceil(p/100 * N), 1-indexed.
    idx = max(1, -(-p * len(s) // 100)) - 1
    return s[idx]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_fst_baseline.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add adil-rag-api/evals/__init__.py adil-rag-api/evals/queries_seed.jsonl adil-rag-api/evals/fst_baseline.py adil-rag-api/tests/test_fst_baseline.py
git commit -m "feat(rag-api): evals package + percentile helper for FST baseline (P0.5)"
```

---

## Task 2: FST baseline runner — end-to-end query loop

**Files:**
- Modify: `adil-rag-api/evals/fst_baseline.py`
- Modify: `adil-rag-api/tests/test_fst_baseline.py`

- [ ] **Step 1: Write the failing test for `BaselineRunner.measure_one`**

Append to `adil-rag-api/tests/test_fst_baseline.py`:

```python
import respx
from httpx import Response

from evals.fst_baseline import BaselineRunner


class TestBaselineRunner:
    @pytest.mark.asyncio
    @respx.mock
    async def test_measure_one_records_latency(self):
        route = respx.post("https://api.example.test/api/v1/query").mock(
            return_value=Response(200, json={"answer": "yes", "sources": []})
        )
        runner = BaselineRunner(api_url="https://api.example.test", api_key="k")
        result = await runner.measure_one(query_id="q1", query="test")
        assert route.called
        assert result["query_id"] == "q1"
        assert result["latency_ms"] >= 0
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    @respx.mock
    async def test_measure_one_records_failure(self):
        respx.post("https://api.example.test/api/v1/query").mock(
            return_value=Response(500, json={"detail": "boom"})
        )
        runner = BaselineRunner(api_url="https://api.example.test", api_key="k")
        result = await runner.measure_one(query_id="q1", query="test")
        assert result["status"] == "fail"
        assert result["http_status"] == 500
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_fst_baseline.py::TestBaselineRunner -v
```

Expected: ImportError on `BaselineRunner`.

- [ ] **Step 3: Add `respx` to dev deps if absent**

Check `adil-rag-api/requirements-dev.txt` or `pyproject.toml`. If `respx` missing:

```bash
echo "respx>=0.21" >> adil-rag-api/requirements-dev.txt
pip install respx
```

- [ ] **Step 4: Implement `BaselineRunner`**

Append to `adil-rag-api/evals/fst_baseline.py`:

```python
class BaselineRunner:
    """Run baseline measurement against the live rag-api FST path."""

    def __init__(self, api_url: str, api_key: str, timeout_s: float = 60.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def measure_one(self, query_id: str, query: str) -> dict[str, Any]:
        """Send one query, record latency and status. Does not retry."""
        payload = {"query": query, "max_sources": 5, "include_viability_score": False}
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        url = f"{self.api_url}/api/v1/query"

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    return {
                        "query_id": query_id,
                        "latency_ms": elapsed_ms,
                        "status": "ok",
                        "http_status": 200,
                    }
                return {
                    "query_id": query_id,
                    "latency_ms": elapsed_ms,
                    "status": "fail",
                    "http_status": resp.status_code,
                }
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                return {
                    "query_id": query_id,
                    "latency_ms": elapsed_ms,
                    "status": "error",
                    "error": str(exc)[:200],
                }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_fst_baseline.py::TestBaselineRunner -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add adil-rag-api/evals/fst_baseline.py adil-rag-api/tests/test_fst_baseline.py adil-rag-api/requirements-dev.txt
git commit -m "feat(rag-api): BaselineRunner.measure_one for FST baseline (P0.5)"
```

---

## Task 3: FST baseline CLI + aggregation

**Files:**
- Modify: `adil-rag-api/evals/fst_baseline.py`
- Create: `adil-rag-api/evals/fst_baseline.json` (generated)

- [ ] **Step 1: Implement aggregation + CLI main**

Append to `adil-rag-api/evals/fst_baseline.py`:

```python
async def run_baseline(
    api_url: str,
    api_key: str,
    queries: list[dict[str, str]],
    repetitions: int = 20,
) -> dict[str, Any]:
    """Run each query `repetitions` times; aggregate latency stats."""
    runner = BaselineRunner(api_url=api_url, api_key=api_key)
    all_results: list[dict[str, Any]] = []
    for _ in range(repetitions):
        for q in queries:
            r = await runner.measure_one(q["id"], q["query"])
            all_results.append(r)

    ok = [r for r in all_results if r["status"] == "ok"]
    latencies = [r["latency_ms"] for r in ok]
    return {
        "total_runs": len(all_results),
        "ok_runs": len(ok),
        "fail_runs": len(all_results) - len(ok),
        "p50_ms": percentile(latencies, 50) if latencies else None,
        "p95_ms": percentile(latencies, 95) if latencies else None,
        "p99_ms": percentile(latencies, 99) if latencies else None,
        "min_ms": min(latencies) if latencies else None,
        "max_ms": max(latencies) if latencies else None,
        "queries_used": [q["id"] for q in queries],
    }


def _load_seed_queries() -> list[dict[str, str]]:
    path = Path(__file__).parent / "queries_seed.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def _cli_main() -> None:
    api_url = os.environ["BASELINE_API_URL"]
    api_key = os.environ["BASELINE_API_KEY"]
    repetitions = int(os.environ.get("BASELINE_REPS", "20"))
    queries = _load_seed_queries()
    summary = await run_baseline(api_url, api_key, queries, repetitions)

    out_path = Path(__file__).parent / "fst_baseline.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}: P50={summary['p50_ms']:.0f}ms P95={summary['p95_ms']:.0f}ms")


if __name__ == "__main__":
    asyncio.run(_cli_main())
```

- [ ] **Step 2: Run an actual baseline against production**

```bash
cd adil-rag-api
BASELINE_API_URL=https://adil-rag-api-production.up.railway.app \
BASELINE_API_KEY=$ADIL_API_KEY \
BASELINE_REPS=20 \
python -m evals.fst_baseline
```

Expected output: `Wrote evals/fst_baseline.json: P50=XXXms P95=XXXms` and a populated JSON file.

If `BASELINE_API_KEY` is not in your shell, fetch from Railway: `railway variables --service adil-rag-api | grep ADIL_API_KEY`.

- [ ] **Step 3: Inspect the file**

```bash
cat adil-rag-api/evals/fst_baseline.json
```

Expected fields: `total_runs`, `ok_runs`, `fail_runs`, `p50_ms`, `p95_ms`, `p99_ms`, `min_ms`, `max_ms`. `ok_runs` should equal `total_runs` (100 = 5 queries × 20 reps). If `fail_runs > 0`, investigate before committing.

- [ ] **Step 4: Commit baseline + CLI**

```bash
git add adil-rag-api/evals/fst_baseline.py adil-rag-api/evals/fst_baseline.json
git commit -m "feat(rag-api): record FST production baseline for cutover gate (P0.5)"
```

P0.5 complete.

---

## Task 4: Ontology schema migration (P1)

**Files:**
- Create: `adil-rag-api/migrations/004_ograg_ontology_init.sql`

- [ ] **Step 1: Write the migration**

Create `adil-rag-api/migrations/004_ograg_ontology_init.sql`:

```sql
-- 004 — OG-RAG ontology tables (Phase 1 of OG-RAG cutover)
-- Spec: docs/superpowers/specs/2026-05-19-og-rag-migration-design.md
-- All DDL idempotent for db_migrate.py re-runs.

CREATE EXTENSION IF NOT EXISTS vector;

-- Enum types (idempotent)
DO $$ BEGIN
  CREATE TYPE ograg_node_type AS ENUM (
    'statute', 'section', 'subsection',
    'case', 'tribunal_decision', 'paragraph',
    'party', 'judge', 'court',
    'topic', 'jurisdiction'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE ograg_edge_relation AS ENUM (
    'part_of',
    'cites', 'overrules', 'distinguished_by',
    'has_topic', 'decided_in_court', 'judged_by', 'heard_party',
    'applies_to_jurisdiction'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS ontology_node (
  id bigserial PRIMARY KEY,
  node_type ograg_node_type NOT NULL,
  natural_key text NOT NULL,                   -- e.g. 'statute:equality-act-2010', 'case:[2023]-uksc-15'
  attrs jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(768),                       -- nullable; only some node types are embedded
  source_doc_id bigint,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (node_type, natural_key)
);

CREATE INDEX IF NOT EXISTS ontology_node_type_idx ON ontology_node (node_type);
CREATE INDEX IF NOT EXISTS ontology_node_natural_key_idx ON ontology_node (natural_key);
CREATE INDEX IF NOT EXISTS ontology_node_attrs_gin ON ontology_node USING gin (attrs);

CREATE TABLE IF NOT EXISTS ontology_edge (
  id bigserial PRIMARY KEY,
  source_id bigint NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
  target_id bigint NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
  relation ograg_edge_relation NOT NULL,
  weight real,
  attrs jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, target_id, relation)
);

CREATE INDEX IF NOT EXISTS ontology_edge_source_idx ON ontology_edge (source_id);
CREATE INDEX IF NOT EXISTS ontology_edge_target_idx ON ontology_edge (target_id);
CREATE INDEX IF NOT EXISTS ontology_edge_relation_idx ON ontology_edge (relation);

CREATE TABLE IF NOT EXISTS hyperedge (
  id bigserial PRIMARY KEY,
  node_ids bigint[] NOT NULL,
  paragraph_text text NOT NULL,
  source_doc_id bigint NOT NULL,               -- references ontology_node(id) for Paragraph node
  embedding vector(768) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ivfflat needs ANALYZE before being used efficiently; left to operator after backfill.
DO $$ BEGIN
  CREATE INDEX hyperedge_embedding_idx ON hyperedge
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
EXCEPTION WHEN duplicate_table THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS eval_run (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  backend text NOT NULL,                        -- 'fst' | 'ograg' | 'ograg_shadow'
  query_id text NOT NULL,
  query text NOT NULL,
  answer text,
  sources jsonb,
  latency_ms integer,
  cost_usd numeric(10, 6),
  judge_score jsonb,
  human_grade text                              -- 'pass' | 'fail' | null
);

CREATE INDEX IF NOT EXISTS eval_run_ts_idx ON eval_run (ts DESC);
CREATE INDEX IF NOT EXISTS eval_run_backend_query_idx ON eval_run (backend, query_id);
```

- [ ] **Step 2: Apply locally against a test Postgres**

```bash
# Use the existing pytest fixture DB or a fresh one
docker run --rm -d --name og-rag-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 pgvector/pgvector:pg16
sleep 5
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -f adil-rag-api/migrations/004_ograg_ontology_init.sql
```

Expected: zero errors. If `pgvector` not in image, error message identifies the cause clearly.

- [ ] **Step 3: Verify the schema**

```bash
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -c "\dt"
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -c "\d ontology_node"
```

Expected: tables `ontology_node`, `ontology_edge`, `hyperedge`, `eval_run` listed. `ontology_node` has `embedding vector(768)` column.

- [ ] **Step 4: Verify re-runs are idempotent**

```bash
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -f adil-rag-api/migrations/004_ograg_ontology_init.sql
```

Expected: zero errors on second apply.

- [ ] **Step 5: Tear down test DB**

```bash
docker stop og-rag-test-pg
```

- [ ] **Step 6: Commit**

```bash
git add adil-rag-api/migrations/004_ograg_ontology_init.sql
git commit -m "feat(rag-api): ontology_node/edge/hyperedge/eval_run schema (P1)"
```

---

## Task 5: store_v2 asyncpg helpers — node upsert + lookup

**Files:**
- Create: `adil-rag-api/ograg/store_v2.py`
- Create: `adil-rag-api/tests/test_ograg_store_v2.py`

- [ ] **Step 1: Write the failing test**

Create `adil-rag-api/tests/test_ograg_store_v2.py`:

```python
"""Integration tests for ograg.store_v2 against real Postgres."""
from __future__ import annotations

import os

import pytest
import asyncpg

from ograg.store_v2 import OntologyStore, NodeRecord


@pytest.fixture
def database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or os.environ["DATABASE_URL"]


@pytest.fixture
async def store(database_url: str):
    s = OntologyStore(database_url)
    await s.connect()
    yield s
    # Cleanup: drop all rows in tables under test
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("TRUNCATE ontology_edge, hyperedge, ontology_node RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    await s.close()


@pytest.mark.asyncio
async def test_upsert_node_new(store: OntologyStore):
    node_id = await store.upsert_node(
        NodeRecord(
            node_type="statute",
            natural_key="statute:equality-act-2010",
            attrs={"short_title": "Equality Act 2010", "year": 2010},
        )
    )
    assert node_id > 0


@pytest.mark.asyncio
async def test_upsert_node_idempotent(store: OntologyStore):
    rec = NodeRecord(
        node_type="statute",
        natural_key="statute:mca-2005",
        attrs={"short_title": "Mental Capacity Act 2005"},
    )
    id1 = await store.upsert_node(rec)
    id2 = await store.upsert_node(rec)
    assert id1 == id2


@pytest.mark.asyncio
async def test_upsert_node_updates_attrs(store: OntologyStore):
    rec1 = NodeRecord(node_type="statute", natural_key="statute:hra-1998", attrs={"v": 1})
    rec2 = NodeRecord(node_type="statute", natural_key="statute:hra-1998", attrs={"v": 2})
    id1 = await store.upsert_node(rec1)
    id2 = await store.upsert_node(rec2)
    assert id1 == id2
    fetched = await store.get_node(id1)
    assert fetched.attrs["v"] == 2


@pytest.mark.asyncio
async def test_get_node_by_natural_key(store: OntologyStore):
    await store.upsert_node(
        NodeRecord(node_type="statute", natural_key="statute:poa-1986", attrs={})
    )
    fetched = await store.get_node_by_key("statute", "statute:poa-1986")
    assert fetched is not None
    assert fetched.attrs == {}


@pytest.mark.asyncio
async def test_get_node_missing_returns_none(store: OntologyStore):
    fetched = await store.get_node_by_key("statute", "statute:does-not-exist")
    assert fetched is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd adil-rag-api
# Ensure a Postgres with the schema applied is available at $DATABASE_URL
pytest tests/test_ograg_store_v2.py -v
```

Expected: ImportError on `ograg.store_v2`.

- [ ] **Step 3: Implement OntologyStore — upsert_node + get_node**

Create `adil-rag-api/ograg/store_v2.py`:

```python
"""asyncpg helpers for the OG-RAG ontology tables.

Pattern matches `adil-document-uploader.app.workers.tasks.rate_limit_cleanup`
(raw asyncpg, no ORM). Used both from rag-api (read path) and from
document-uploader's worker (write path, cross-DB).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import asyncpg


@dataclass
class NodeRecord:
    node_type: str
    natural_key: str
    attrs: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    source_doc_id: int | None = None
    id: int | None = None  # populated on read


class OntologyStore:
    """Thin asyncpg wrapper for ontology_node/edge/hyperedge.

    Single-connection client for simplicity; callers needing concurrency
    create multiple instances.
    """

    def __init__(self, database_url: str):
        self._dsn = database_url
        self._conn: asyncpg.Connection | None = None

    async def connect(self) -> None:
        self._conn = await asyncpg.connect(self._dsn)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> asyncpg.Connection:
        if self._conn is None:
            raise RuntimeError("OntologyStore not connected; call connect() first")
        return self._conn

    async def upsert_node(self, node: NodeRecord) -> int:
        """Insert or update by (node_type, natural_key). Returns node id."""
        conn = self._require_conn()
        row = await conn.fetchrow(
            """
            INSERT INTO ontology_node (node_type, natural_key, attrs, embedding, source_doc_id)
            VALUES ($1::ograg_node_type, $2, $3::jsonb, $4, $5)
            ON CONFLICT (node_type, natural_key) DO UPDATE
                SET attrs = EXCLUDED.attrs,
                    embedding = COALESCE(EXCLUDED.embedding, ontology_node.embedding),
                    source_doc_id = COALESCE(EXCLUDED.source_doc_id, ontology_node.source_doc_id),
                    updated_at = now()
            RETURNING id
            """,
            node.node_type,
            node.natural_key,
            json.dumps(node.attrs),
            node.embedding,
            node.source_doc_id,
        )
        return int(row["id"])

    async def get_node(self, node_id: int) -> NodeRecord | None:
        conn = self._require_conn()
        row = await conn.fetchrow(
            "SELECT id, node_type::text, natural_key, attrs, source_doc_id FROM ontology_node WHERE id = $1",
            node_id,
        )
        if row is None:
            return None
        return NodeRecord(
            id=row["id"],
            node_type=row["node_type"],
            natural_key=row["natural_key"],
            attrs=json.loads(row["attrs"]) if isinstance(row["attrs"], str) else row["attrs"],
            source_doc_id=row["source_doc_id"],
        )

    async def get_node_by_key(self, node_type: str, natural_key: str) -> NodeRecord | None:
        conn = self._require_conn()
        row = await conn.fetchrow(
            "SELECT id, node_type::text, natural_key, attrs, source_doc_id "
            "FROM ontology_node WHERE node_type = $1::ograg_node_type AND natural_key = $2",
            node_type,
            natural_key,
        )
        if row is None:
            return None
        return NodeRecord(
            id=row["id"],
            node_type=row["node_type"],
            natural_key=row["natural_key"],
            attrs=json.loads(row["attrs"]) if isinstance(row["attrs"], str) else row["attrs"],
            source_doc_id=row["source_doc_id"],
        )
```

- [ ] **Step 4: Apply the migration to your test DB and run the tests**

```bash
# Assume TEST_DATABASE_URL or DATABASE_URL points at a Postgres with 004 applied
pytest tests/test_ograg_store_v2.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add adil-rag-api/ograg/store_v2.py adil-rag-api/tests/test_ograg_store_v2.py
git commit -m "feat(rag-api): OntologyStore upsert_node/get_node helpers (P1)"
```

---

## Task 6: store_v2 — edge upsert + batch helpers

**Files:**
- Modify: `adil-rag-api/ograg/store_v2.py`
- Modify: `adil-rag-api/tests/test_ograg_store_v2.py`

- [ ] **Step 1: Write the failing tests for edges + batch ops**

Append to `adil-rag-api/tests/test_ograg_store_v2.py`:

```python
from ograg.store_v2 import EdgeRecord


@pytest.mark.asyncio
async def test_upsert_edge(store: OntologyStore):
    a = await store.upsert_node(NodeRecord(node_type="statute", natural_key="statute:a", attrs={}))
    b = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:a-s1", attrs={}))
    edge_id = await store.upsert_edge(EdgeRecord(source_id=b, target_id=a, relation="part_of"))
    assert edge_id > 0


@pytest.mark.asyncio
async def test_upsert_edge_idempotent(store: OntologyStore):
    a = await store.upsert_node(NodeRecord(node_type="statute", natural_key="statute:b", attrs={}))
    b = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:b-s1", attrs={}))
    e = EdgeRecord(source_id=b, target_id=a, relation="part_of")
    id1 = await store.upsert_edge(e)
    id2 = await store.upsert_edge(e)
    assert id1 == id2


@pytest.mark.asyncio
async def test_batch_upsert_nodes(store: OntologyStore):
    records = [
        NodeRecord(node_type="section", natural_key=f"section:c-s{i}", attrs={"n": i})
        for i in range(1, 6)
    ]
    ids = await store.batch_upsert_nodes(records)
    assert len(ids) == 5
    assert len(set(ids)) == 5  # all distinct


@pytest.mark.asyncio
async def test_get_edges_by_source(store: OntologyStore):
    a = await store.upsert_node(NodeRecord(node_type="statute", natural_key="statute:d", attrs={}))
    s1 = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:d-s1", attrs={}))
    s2 = await store.upsert_node(NodeRecord(node_type="section", natural_key="section:d-s2", attrs={}))
    await store.upsert_edge(EdgeRecord(source_id=s1, target_id=a, relation="part_of"))
    await store.upsert_edge(EdgeRecord(source_id=s2, target_id=a, relation="part_of"))
    edges = await store.get_edges_from(a, relation="part_of", reverse=True)
    assert {e.source_id for e in edges} == {s1, s2}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ograg_store_v2.py -v -k "edge or batch"
```

Expected: ImportError on `EdgeRecord` and missing methods.

- [ ] **Step 3: Implement EdgeRecord + edge/batch methods**

Append to `adil-rag-api/ograg/store_v2.py`:

```python
@dataclass
class EdgeRecord:
    source_id: int
    target_id: int
    relation: str
    weight: float | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    id: int | None = None


# Extend OntologyStore — append to the class body in the same file.
async def _upsert_edge_impl(self, edge: EdgeRecord) -> int:
    conn = self._require_conn()
    row = await conn.fetchrow(
        """
        INSERT INTO ontology_edge (source_id, target_id, relation, weight, attrs)
        VALUES ($1, $2, $3::ograg_edge_relation, $4, $5::jsonb)
        ON CONFLICT (source_id, target_id, relation) DO UPDATE
            SET weight = EXCLUDED.weight,
                attrs = EXCLUDED.attrs
        RETURNING id
        """,
        edge.source_id, edge.target_id, edge.relation, edge.weight, json.dumps(edge.attrs),
    )
    return int(row["id"])


async def _batch_upsert_nodes_impl(self, nodes: list[NodeRecord]) -> list[int]:
    """Sequential upsert in a single transaction. ~10x faster than per-call commits."""
    conn = self._require_conn()
    ids: list[int] = []
    async with conn.transaction():
        for n in nodes:
            row = await conn.fetchrow(
                """
                INSERT INTO ontology_node (node_type, natural_key, attrs, embedding, source_doc_id)
                VALUES ($1::ograg_node_type, $2, $3::jsonb, $4, $5)
                ON CONFLICT (node_type, natural_key) DO UPDATE
                    SET attrs = EXCLUDED.attrs,
                        updated_at = now()
                RETURNING id
                """,
                n.node_type, n.natural_key, json.dumps(n.attrs), n.embedding, n.source_doc_id,
            )
            ids.append(int(row["id"]))
    return ids


async def _get_edges_from_impl(
    self, node_id: int, relation: str | None = None, reverse: bool = False,
) -> list[EdgeRecord]:
    conn = self._require_conn()
    if reverse:
        sql = "SELECT id, source_id, target_id, relation::text, weight, attrs FROM ontology_edge WHERE target_id = $1"
    else:
        sql = "SELECT id, source_id, target_id, relation::text, weight, attrs FROM ontology_edge WHERE source_id = $1"
    args: list[Any] = [node_id]
    if relation is not None:
        sql += " AND relation = $2::ograg_edge_relation"
        args.append(relation)
    rows = await conn.fetch(sql, *args)
    return [
        EdgeRecord(
            id=r["id"], source_id=r["source_id"], target_id=r["target_id"],
            relation=r["relation"], weight=r["weight"],
            attrs=json.loads(r["attrs"]) if isinstance(r["attrs"], str) else r["attrs"],
        )
        for r in rows
    ]
```

Now bind these as methods. In `adil-rag-api/ograg/store_v2.py`, find the `OntologyStore` class and add the three methods inside it (not as module-level functions). The cleanest is to inline them into the class definition rather than monkey-patching. Replace the module-level helper stubs above with these in-class methods:

```python
class OntologyStore:
    # ... existing __init__, connect, close, _require_conn, upsert_node, get_node, get_node_by_key ...

    async def upsert_edge(self, edge: EdgeRecord) -> int:
        conn = self._require_conn()
        row = await conn.fetchrow(
            """
            INSERT INTO ontology_edge (source_id, target_id, relation, weight, attrs)
            VALUES ($1, $2, $3::ograg_edge_relation, $4, $5::jsonb)
            ON CONFLICT (source_id, target_id, relation) DO UPDATE
                SET weight = EXCLUDED.weight,
                    attrs = EXCLUDED.attrs
            RETURNING id
            """,
            edge.source_id, edge.target_id, edge.relation, edge.weight, json.dumps(edge.attrs),
        )
        return int(row["id"])

    async def batch_upsert_nodes(self, nodes: list[NodeRecord]) -> list[int]:
        conn = self._require_conn()
        ids: list[int] = []
        async with conn.transaction():
            for n in nodes:
                row = await conn.fetchrow(
                    """
                    INSERT INTO ontology_node (node_type, natural_key, attrs, embedding, source_doc_id)
                    VALUES ($1::ograg_node_type, $2, $3::jsonb, $4, $5)
                    ON CONFLICT (node_type, natural_key) DO UPDATE
                        SET attrs = EXCLUDED.attrs,
                            updated_at = now()
                    RETURNING id
                    """,
                    n.node_type, n.natural_key, json.dumps(n.attrs), n.embedding, n.source_doc_id,
                )
                ids.append(int(row["id"]))
        return ids

    async def get_edges_from(
        self, node_id: int, relation: str | None = None, reverse: bool = False,
    ) -> list[EdgeRecord]:
        conn = self._require_conn()
        if reverse:
            sql = "SELECT id, source_id, target_id, relation::text, weight, attrs FROM ontology_edge WHERE target_id = $1"
        else:
            sql = "SELECT id, source_id, target_id, relation::text, weight, attrs FROM ontology_edge WHERE source_id = $1"
        args: list[Any] = [node_id]
        if relation is not None:
            sql += " AND relation = $2::ograg_edge_relation"
            args.append(relation)
        rows = await conn.fetch(sql, *args)
        return [
            EdgeRecord(
                id=r["id"], source_id=r["source_id"], target_id=r["target_id"],
                relation=r["relation"], weight=r["weight"],
                attrs=json.loads(r["attrs"]) if isinstance(r["attrs"], str) else r["attrs"],
            )
            for r in rows
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ograg_store_v2.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add adil-rag-api/ograg/store_v2.py adil-rag-api/tests/test_ograg_store_v2.py
git commit -m "feat(rag-api): OntologyStore edge + batch ops (P1)"
```

P1 complete.

---

## Task 7: Acts table alembic migration (P1.5)

**Files:**
- Create: `adil-document-uploader/alembic/versions/b1a2c3d4e5f6_add_acts_table.py`
- Create: `adil-document-uploader/app/models/act.py`
- Modify: `adil-document-uploader/app/models/__init__.py`

- [ ] **Step 1: Find current alembic head**

```bash
cd adil-document-uploader
alembic heads
```

Note the revision id (used as `down_revision` in the new file). Expected: `a3c9e1f70b22` (the solicitor_firms migration).

- [ ] **Step 2: Create the alembic migration**

Create `adil-document-uploader/alembic/versions/b1a2c3d4e5f6_add_acts_table.py`:

```python
"""add acts table

Revision ID: b1a2c3d4e5f6
Revises: a3c9e1f70b22
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1a2c3d4e5f6"
down_revision: str | None = "a3c9e1f70b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "acts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("legislation_url", sa.Text(), nullable=False),
        sa.Column("clml_url", sa.Text(), nullable=True),
        sa.Column("raw_xml", sa.Text(), nullable=True),
        sa.Column("jurisdiction", sa.String(20), nullable=False, server_default="EW"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_title", "year", name="uq_acts_short_title_year"),
    )
    op.create_index("ix_acts_status", "acts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_acts_status", "acts")
    op.drop_table("acts")
```

- [ ] **Step 3: Create the SQLAlchemy model**

Create `adil-document-uploader/app/models/act.py`:

```python
"""SQLAlchemy model for fetched Acts (legislation.gov.uk source rows)."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models import Base


class ActStatus(str, enum.Enum):
    PENDING = "pending"
    FETCHED = "fetched"
    EXTRACTED = "extracted"
    FAILED = "failed"


class Act(Base):
    __tablename__ = "acts"
    __table_args__ = (UniqueConstraint("short_title", "year", name="uq_acts_short_title_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    legislation_url: Mapped[str] = mapped_column(Text, nullable=False)
    clml_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False, default="EW")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ActStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Export the model**

Open `adil-document-uploader/app/models/__init__.py`, add:

```python
from app.models.act import Act, ActStatus  # noqa: F401
```

(Place it alongside the existing `Judgment` and `SolicitorFirm` imports — read the file to find the right pattern.)

- [ ] **Step 5: Apply the migration locally**

```bash
cd adil-document-uploader
alembic upgrade head
```

Expected output: `Running upgrade a3c9e1f70b22 -> b1a2c3d4e5f6, add acts table`.

- [ ] **Step 6: Verify**

```bash
PGPASSWORD=... psql -h ... -c "\d acts"
```

Expected: 11 columns, primary key on id, unique constraint on (short_title, year), index on status.

- [ ] **Step 7: Commit**

```bash
git add adil-document-uploader/alembic/versions/b1a2c3d4e5f6_add_acts_table.py adil-document-uploader/app/models/act.py adil-document-uploader/app/models/__init__.py
git commit -m "feat(document-uploader): acts table for OG-RAG statute source (P1.5)"
```

---

## Task 8: legislation.gov.uk client (P1.5)

**Files:**
- Create: `adil-document-uploader/app/services/legislation_client.py`
- Create: `adil-document-uploader/tests/test_legislation_client.py`
- Create: `adil-document-uploader/tests/fixtures/equality_act_2010_clml.xml`
- Modify: `adil-document-uploader/app/config.py`
- Modify: `adil-document-uploader/requirements.txt`

- [ ] **Step 1: Add lxml dep**

Append to `adil-document-uploader/requirements.txt`:

```
lxml>=5.0
```

```bash
pip install lxml
```

- [ ] **Step 2: Save a fixture (one-off curl from a working machine)**

```bash
mkdir -p adil-document-uploader/tests/fixtures
curl -sL https://www.legislation.gov.uk/ukpga/2010/15/data.xml -o adil-document-uploader/tests/fixtures/equality_act_2010_clml.xml
# Confirm it's CLML (will contain <Legislation ...> root)
head -3 adil-document-uploader/tests/fixtures/equality_act_2010_clml.xml
```

Expected: starts with `<?xml version="1.0"`, has `<Legislation` element.

- [ ] **Step 3: Write the failing test**

Create `adil-document-uploader/tests/test_legislation_client.py`:

```python
"""Tests for legislation.gov.uk CLML client."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response

from app.services.legislation_client import LegislationClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def equality_act_xml() -> bytes:
    return (FIXTURES / "equality_act_2010_clml.xml").read_bytes()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_act_xml_success(equality_act_xml: bytes):
    respx.get("https://www.legislation.gov.uk/ukpga/2010/15/data.xml").mock(
        return_value=Response(200, content=equality_act_xml, headers={"content-type": "application/xml"})
    )
    client = LegislationClient(base_url="https://www.legislation.gov.uk")
    raw = await client.fetch_act_xml(category="ukpga", year=2010, number=15)
    assert raw.startswith(b"<?xml")
    assert b"Legislation" in raw


@pytest.mark.asyncio
@respx.mock
async def test_fetch_act_xml_404_raises():
    respx.get("https://www.legislation.gov.uk/ukpga/2099/9999/data.xml").mock(
        return_value=Response(404, content=b"Not Found")
    )
    client = LegislationClient(base_url="https://www.legislation.gov.uk")
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_act_xml(category="ukpga", year=2099, number=9999)
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd adil-document-uploader
pytest tests/test_legislation_client.py -v
```

Expected: ImportError on `app.services.legislation_client`.

- [ ] **Step 5: Implement the client**

Create `adil-document-uploader/app/services/legislation_client.py`:

```python
"""HTTP client for legislation.gov.uk CLML XML feeds.

The site exposes per-Act XML at /<category>/<year>/<number>/data.xml.
Category examples: ukpga (UK Public General Act), asp (Scotland), nisi (NI SI).
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class LegislationClient:
    def __init__(self, base_url: str = "https://www.legislation.gov.uk", timeout_s: float = 30.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def fetch_act_xml(self, *, category: str, year: int, number: int) -> bytes:
        """Fetch the raw CLML XML for an Act. Raises HTTPStatusError on non-2xx."""
        url = f"{self._base}/{category}/{year}/{number}/data.xml"
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/xml"})
            resp.raise_for_status()
            return resp.content
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_legislation_client.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Wire config**

Open `adil-document-uploader/app/config.py`. Find the `Settings` class. Add (preserving existing style):

```python
legislation_gov_uk_base_url: str = "https://www.legislation.gov.uk"
```

- [ ] **Step 8: Commit**

```bash
git add adil-document-uploader/app/services/legislation_client.py adil-document-uploader/tests/test_legislation_client.py adil-document-uploader/tests/fixtures/equality_act_2010_clml.xml adil-document-uploader/app/config.py adil-document-uploader/requirements.txt
git commit -m "feat(document-uploader): legislation.gov.uk CLML XML client (P1.5)"
```

---

## Task 9: Acts XML → nodes parser (P1.5)

**Files:**
- Create: `adil-document-uploader/app/services/acts_parser.py`
- Create: `adil-document-uploader/tests/test_acts_parser.py`

- [ ] **Step 1: Write the failing test**

Create `adil-document-uploader/tests/test_acts_parser.py`:

```python
"""Tests for CLML XML parser → Statute/Section/Subsection node records."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.acts_parser import ParsedAct, parse_clml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def equality_act_xml() -> bytes:
    return (FIXTURES / "equality_act_2010_clml.xml").read_bytes()


def test_parse_clml_returns_statute(equality_act_xml: bytes):
    result = parse_clml(equality_act_xml)
    assert isinstance(result, ParsedAct)
    assert result.statute.short_title == "Equality Act 2010"
    assert result.statute.year == 2010


def test_parse_clml_extracts_sections(equality_act_xml: bytes):
    result = parse_clml(equality_act_xml)
    # Equality Act has 218 sections + schedules; at minimum expect >100 sections
    assert len(result.sections) >= 100
    # Section 13 is "Direct discrimination" — must be present
    s13 = next((s for s in result.sections if s.number == "13"), None)
    assert s13 is not None
    assert "discrimination" in s13.title.lower()


def test_parse_clml_extracts_subsections(equality_act_xml: bytes):
    result = parse_clml(equality_act_xml)
    # s.13 has multiple subsections (1), (2), ...
    s13_subs = [sub for sub in result.subsections if sub.section_number == "13"]
    assert len(s13_subs) >= 2


def test_parse_clml_natural_keys_are_stable(equality_act_xml: bytes):
    result = parse_clml(equality_act_xml)
    assert result.statute.natural_key == "statute:equality-act-2010"
    s13 = next(s for s in result.sections if s.number == "13")
    assert s13.natural_key == "section:equality-act-2010-s13"


def test_parse_clml_invalid_xml_raises():
    with pytest.raises(ValueError, match="invalid"):
        parse_clml(b"not xml at all")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_acts_parser.py -v
```

Expected: ImportError on `app.services.acts_parser`.

- [ ] **Step 3: Implement the parser**

Create `adil-document-uploader/app/services/acts_parser.py`:

```python
"""Parse legislation.gov.uk CLML XML into ontology node records.

CLML namespace: http://www.legislation.gov.uk/namespaces/legislation
Top-level structure:
  <Legislation>
    <ukm:Metadata>
      <dc:title>Equality Act 2010</dc:title>
      ...
    </ukm:Metadata>
    <Primary>
      <Body>
        <Part>...</Part>
        <P1 id="section-13">
          <Pnumber>13</Pnumber>
          <Title>Direct discrimination</Title>
          <P2 id="section-13-1">
            <Pnumber>1</Pnumber>
            <P2para><Text>A person (A) discriminates...</Text></P2para>
          </P2>
        </P1>
      </Body>
    </Primary>
  </Legislation>
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

NS = {
    "leg": "http://www.legislation.gov.uk/namespaces/legislation",
    "ukm": "http://www.legislation.gov.uk/namespaces/metadata",
    "dc": "http://purl.org/dc/elements/1.1/",
}


@dataclass
class StatuteNode:
    natural_key: str
    short_title: str
    year: int
    url: str


@dataclass
class SectionNode:
    natural_key: str
    statute_key: str
    number: str
    title: str


@dataclass
class SubsectionNode:
    natural_key: str
    section_key: str
    section_number: str
    number: str
    text: str


@dataclass
class ParsedAct:
    statute: StatuteNode
    sections: list[SectionNode]
    subsections: list[SubsectionNode]


def _slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s


def parse_clml(xml_bytes: bytes) -> ParsedAct:
    """Parse a CLML Act into a ParsedAct.

    Raises ValueError if the XML is malformed or not a recognisable Act.
    """
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"invalid CLML XML: {exc}") from exc

    title_el = root.find(".//dc:title", NS)
    year_el = root.find(".//ukm:Year", NS)
    if title_el is None or year_el is None:
        raise ValueError("invalid CLML: missing dc:title or ukm:Year")

    short_title = (title_el.text or "").strip()
    year = int(year_el.get("Value", "0"))

    # Build URL — leg.gov.uk doesn't include a canonical URL in the XML; reconstruct.
    metadata_uri_el = root.find(".//ukm:DocumentUri", NS)
    url = (metadata_uri_el.text or "").strip() if metadata_uri_el is not None else ""

    statute_key = f"statute:{_slugify(short_title)}"
    statute = StatuteNode(natural_key=statute_key, short_title=short_title, year=year, url=url)

    sections: list[SectionNode] = []
    subsections: list[SubsectionNode] = []

    # P1 = top-level section; P2 = subsection; P3 = paragraph.
    for p1 in root.iter("{http://www.legislation.gov.uk/namespaces/legislation}P1"):
        num_el = p1.find("leg:Pnumber", NS)
        title_el = p1.find("leg:Title", NS)
        if num_el is None or num_el.text is None:
            continue
        sec_num = num_el.text.strip()
        sec_title = (title_el.text or "").strip() if title_el is not None else ""
        sec_key = f"section:{_slugify(short_title)}-s{sec_num}"
        sections.append(SectionNode(
            natural_key=sec_key, statute_key=statute_key,
            number=sec_num, title=sec_title,
        ))

        for p2 in p1.iter("{http://www.legislation.gov.uk/namespaces/legislation}P2"):
            sub_num_el = p2.find("leg:Pnumber", NS)
            if sub_num_el is None or sub_num_el.text is None:
                continue
            sub_num = sub_num_el.text.strip()
            text_el = p2.find(".//leg:Text", NS)
            sub_text = (text_el.text or "").strip() if text_el is not None else ""
            sub_key = f"subsection:{_slugify(short_title)}-s{sec_num}-{sub_num}"
            subsections.append(SubsectionNode(
                natural_key=sub_key, section_key=sec_key,
                section_number=sec_num, number=sub_num, text=sub_text,
            ))

    return ParsedAct(statute=statute, sections=sections, subsections=subsections)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_acts_parser.py -v
```

Expected: 5 passed. If section count assertion fails, inspect the fixture XML to confirm element naming — CLML has had minor schema variants over the years.

- [ ] **Step 5: Commit**

```bash
git add adil-document-uploader/app/services/acts_parser.py adil-document-uploader/tests/test_acts_parser.py
git commit -m "feat(document-uploader): CLML XML → Statute/Section/Subsection parser (P1.5)"
```

---

## Task 10: Cross-DB ograg writer (P1.5)

**Files:**
- Create: `adil-document-uploader/app/services/ograg_writer.py`
- Create: `adil-document-uploader/tests/test_ograg_writer.py`

The writer holds asyncpg connections to **both** DBs: reads from uploader's `acts` table (already covered by SQLAlchemy session in the worker), writes nodes/edges to **rag-api's DB** via raw asyncpg using `RAG_API_DATABASE_URL`.

For unit testing, we point both DSNs at the same test Postgres (with both schemas applied).

- [ ] **Step 1: Write the failing test**

Create `adil-document-uploader/tests/test_ograg_writer.py`:

```python
"""Tests for cross-DB ograg writer (writes ontology rows to rag-api's DB)."""
from __future__ import annotations

import os

import pytest

from app.services.acts_parser import ParsedAct, SectionNode, StatuteNode, SubsectionNode
from app.services.ograg_writer import OgragWriter


@pytest.fixture
def rag_api_database_url() -> str:
    return os.environ.get("RAG_API_DATABASE_URL") or os.environ["DATABASE_URL"]


@pytest.fixture
def sample_parsed_act() -> ParsedAct:
    return ParsedAct(
        statute=StatuteNode(
            natural_key="statute:test-act-1999",
            short_title="Test Act 1999",
            year=1999,
            url="https://example.test/ukpga/1999/1",
        ),
        sections=[
            SectionNode(natural_key="section:test-act-1999-s1", statute_key="statute:test-act-1999", number="1", title="First section"),
        ],
        subsections=[
            SubsectionNode(natural_key="subsection:test-act-1999-s1-1", section_key="section:test-act-1999-s1", section_number="1", number="1", text="The subsection text."),
        ],
    )


@pytest.mark.asyncio
async def test_write_parsed_act_creates_nodes(rag_api_database_url: str, sample_parsed_act: ParsedAct):
    writer = OgragWriter(rag_api_database_url)
    await writer.connect()
    try:
        result = await writer.write_parsed_act(sample_parsed_act)
        assert result.statute_id > 0
        assert len(result.section_ids) == 1
        assert len(result.subsection_ids) == 1
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_write_parsed_act_creates_part_of_edges(rag_api_database_url: str, sample_parsed_act: ParsedAct):
    writer = OgragWriter(rag_api_database_url)
    await writer.connect()
    try:
        result = await writer.write_parsed_act(sample_parsed_act)
        # Verify part_of edges: section → statute, subsection → section
        edges = await writer._dbg_count_edges_for(result.section_ids[0])
        assert edges["part_of_outgoing"] == 1  # section → statute
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_write_parsed_act_idempotent(rag_api_database_url: str, sample_parsed_act: ParsedAct):
    writer = OgragWriter(rag_api_database_url)
    await writer.connect()
    try:
        r1 = await writer.write_parsed_act(sample_parsed_act)
        r2 = await writer.write_parsed_act(sample_parsed_act)
        assert r1.statute_id == r2.statute_id
        assert r1.section_ids == r2.section_ids
        assert r1.subsection_ids == r2.subsection_ids
    finally:
        await writer.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd adil-document-uploader
pytest tests/test_ograg_writer.py -v
```

Expected: ImportError on `app.services.ograg_writer`.

- [ ] **Step 3: Implement the writer**

Create `adil-document-uploader/app/services/ograg_writer.py`:

```python
"""Cross-DB writer for ontology rows in rag-api's Postgres.

Uses raw asyncpg. Pattern matches `rate_limit_cleanup` in workers/tasks.py
which already writes cross-DB to rag-api's DB.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import asyncpg

from app.services.acts_parser import ParsedAct

logger = logging.getLogger(__name__)


@dataclass
class WrittenAct:
    statute_id: int
    section_ids: list[int]
    subsection_ids: list[int]


class OgragWriter:
    def __init__(self, rag_api_database_url: str):
        self._dsn = rag_api_database_url
        self._conn: asyncpg.Connection | None = None

    async def connect(self) -> None:
        self._conn = await asyncpg.connect(self._dsn)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _conn_or_fail(self) -> asyncpg.Connection:
        if self._conn is None:
            raise RuntimeError("OgragWriter not connected")
        return self._conn

    async def _upsert_node(self, conn: asyncpg.Connection, node_type: str, natural_key: str, attrs: dict) -> int:
        row = await conn.fetchrow(
            """
            INSERT INTO ontology_node (node_type, natural_key, attrs)
            VALUES ($1::ograg_node_type, $2, $3::jsonb)
            ON CONFLICT (node_type, natural_key) DO UPDATE
                SET attrs = EXCLUDED.attrs, updated_at = now()
            RETURNING id
            """,
            node_type, natural_key, json.dumps(attrs),
        )
        return int(row["id"])

    async def _upsert_edge(self, conn: asyncpg.Connection, source_id: int, target_id: int, relation: str) -> None:
        await conn.execute(
            """
            INSERT INTO ontology_edge (source_id, target_id, relation)
            VALUES ($1, $2, $3::ograg_edge_relation)
            ON CONFLICT (source_id, target_id, relation) DO NOTHING
            """,
            source_id, target_id, relation,
        )

    async def write_parsed_act(self, parsed: ParsedAct) -> WrittenAct:
        conn = self._conn_or_fail()
        async with conn.transaction():
            statute_id = await self._upsert_node(
                conn, "statute", parsed.statute.natural_key,
                {"short_title": parsed.statute.short_title, "year": parsed.statute.year, "url": parsed.statute.url},
            )

            section_ids_by_key: dict[str, int] = {}
            for s in parsed.sections:
                sid = await self._upsert_node(
                    conn, "section", s.natural_key,
                    {"number": s.number, "title": s.title},
                )
                section_ids_by_key[s.natural_key] = sid
                await self._upsert_edge(conn, source_id=sid, target_id=statute_id, relation="part_of")

            subsection_ids: list[int] = []
            for sub in parsed.subsections:
                sub_id = await self._upsert_node(
                    conn, "subsection", sub.natural_key,
                    {"number": sub.number, "section_number": sub.section_number, "text": sub.text},
                )
                subsection_ids.append(sub_id)
                parent_sid = section_ids_by_key.get(sub.section_key)
                if parent_sid is not None:
                    await self._upsert_edge(conn, source_id=sub_id, target_id=parent_sid, relation="part_of")

            return WrittenAct(
                statute_id=statute_id,
                section_ids=list(section_ids_by_key.values()),
                subsection_ids=subsection_ids,
            )

    async def _dbg_count_edges_for(self, node_id: int) -> dict[str, int]:
        """Test-only helper. Counts edges with this node as source."""
        conn = self._conn_or_fail()
        rows = await conn.fetch(
            "SELECT relation::text AS r, COUNT(*) AS c FROM ontology_edge WHERE source_id = $1 GROUP BY relation",
            node_id,
        )
        return {f"{r['r']}_outgoing": int(r["c"]) for r in rows}
```

- [ ] **Step 4: Apply rag-api's migration 004 to the test DB**

If you haven't already:

```bash
cd adil-rag-api
DATABASE_URL=$TEST_DATABASE_URL python -c "import asyncio; from db_migrate import run_migrations; asyncio.run(run_migrations('$TEST_DATABASE_URL'))"
```

Or with the docker pgvector container from Task 4:

```bash
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -f adil-rag-api/migrations/004_ograg_ontology_init.sql
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd adil-document-uploader
RAG_API_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres pytest tests/test_ograg_writer.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add adil-document-uploader/app/services/ograg_writer.py adil-document-uploader/tests/test_ograg_writer.py
git commit -m "feat(document-uploader): cross-DB OgragWriter for ontology rows (P1.5)"
```

---

## Task 11: fetch_acts arq task (P1.5)

**Files:**
- Modify: `adil-document-uploader/app/workers/tasks.py`
- Modify: `adil-document-uploader/app/workers/settings.py`

**Seed list of Acts to fetch (from existing `UK_LEGISLATION_URLS` in `rag_service.py`):**

| short_title | category | year | number |
|---|---|---|---|
| Equality Act 2010 | ukpga | 2010 | 15 |
| Public Order Act 1986 | ukpga | 1986 | 64 |
| Crime and Disorder Act 1998 | ukpga | 1998 | 37 |
| Online Safety Act 2023 | ukpga | 2023 | 50 |
| Human Rights Act 1998 | ukpga | 1998 | 42 |
| Employment Rights Act 1996 | ukpga | 1996 | 18 |
| Racial and Religious Hatred Act 2006 | ukpga | 2006 | 1 |
| Mental Capacity Act 2005 | ukpga | 2005 | 9 |

- [ ] **Step 1: Add fetch_acts task**

Open `adil-document-uploader/app/workers/tasks.py`. Append at the end (after `scrape_solicitors`):

```python
async def fetch_acts(ctx: dict) -> dict:
    """arq task: fetch the seed list of UK Acts from legislation.gov.uk,
    parse, and write ontology nodes to rag-api's DB.

    Idempotent: re-runs upsert by (node_type, natural_key).
    """
    import os

    from app.services.legislation_client import LegislationClient
    from app.services.acts_parser import parse_clml
    from app.services.ograg_writer import OgragWriter

    settings = get_settings()

    # Seed list. Extend by adding rows; existing rows are upserted.
    SEED_ACTS = [
        ("Equality Act 2010", "ukpga", 2010, 15),
        ("Public Order Act 1986", "ukpga", 1986, 64),
        ("Crime and Disorder Act 1998", "ukpga", 1998, 37),
        ("Online Safety Act 2023", "ukpga", 2023, 50),
        ("Human Rights Act 1998", "ukpga", 1998, 42),
        ("Employment Rights Act 1996", "ukpga", 1996, 18),
        ("Racial and Religious Hatred Act 2006", "ukpga", 2006, 1),
        ("Mental Capacity Act 2005", "ukpga", 2005, 9),
    ]

    rag_api_db_url = os.getenv("RAG_API_DATABASE_URL")
    if not rag_api_db_url:
        logger.error("fetch_acts: RAG_API_DATABASE_URL not set; skipping")
        return {"fetched": 0, "failed": 0, "error": "RAG_API_DATABASE_URL not set"}

    client = LegislationClient(base_url=settings.legislation_gov_uk_base_url)
    writer = OgragWriter(rag_api_db_url)
    await writer.connect()

    fetched = 0
    failed = 0
    failures: list[tuple[str, str]] = []
    try:
        for short_title, category, year, number in SEED_ACTS:
            try:
                xml = await client.fetch_act_xml(category=category, year=year, number=number)
                parsed = parse_clml(xml)
                written = await writer.write_parsed_act(parsed)
                logger.info(
                    "fetch_acts: %s — wrote 1 statute + %d sections + %d subsections",
                    short_title, len(written.section_ids), len(written.subsection_ids),
                )
                fetched += 1
            except Exception as exc:
                logger.exception("fetch_acts: %s failed", short_title)
                failed += 1
                failures.append((short_title, str(exc)[:200]))
    finally:
        await writer.close()

    return {"fetched": fetched, "failed": failed, "failures": failures}
```

- [ ] **Step 2: Register the task**

Open `adil-document-uploader/app/workers/settings.py`. Find the `WorkerSettings.functions` list and add `fetch_acts` to it. Add a cron entry too — monthly, 1st of month, 03:00 UTC, ahead of the existing solicitor scrape at 04:00 UTC:

```python
# (in WorkerSettings.functions)
from app.workers.tasks import (
    ...,
    fetch_acts,
)

functions = [
    ...,
    fetch_acts,
]

# (in cron_jobs)
from arq import cron

cron_jobs = [
    ...,
    cron(fetch_acts.__name__, name="fetch_acts_monthly", month=None, day=1, hour=3, minute=0),
]
```

(Exact syntax depends on existing patterns in `settings.py` — read the file and match its style.)

- [ ] **Step 3: Manual smoke test against a test Postgres**

```bash
cd adil-document-uploader
# Point at the test pgvector container with both schemas applied
RAG_API_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres \
DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres \
python -c "
import asyncio
from app.workers.tasks import fetch_acts
print(asyncio.run(fetch_acts({})))
"
```

Expected: `{'fetched': 8, 'failed': 0, 'failures': []}` after a few seconds (one HTTP call per Act).

- [ ] **Step 4: Verify nodes landed in rag-api's DB**

```bash
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -c "
SELECT node_type, COUNT(*) FROM ontology_node GROUP BY node_type ORDER BY 1;
"
```

Expected:
```
 node_type   | count
-------------+-------
 section     |  ~600
 statute     |     8
 subsection  |  ~3000
```

(Counts vary; Equality Act alone has ~218 sections.)

```bash
PGPASSWORD=test psql -h localhost -p 55432 -U postgres -d postgres -c "
SELECT relation, COUNT(*) FROM ontology_edge GROUP BY relation ORDER BY 1;
"
```

Expected: `part_of | ~3600` (each section + subsection has a part_of edge).

- [ ] **Step 5: Run all relevant tests one more time**

```bash
cd adil-document-uploader
pytest tests/test_legislation_client.py tests/test_acts_parser.py tests/test_ograg_writer.py -v
```

Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add adil-document-uploader/app/workers/tasks.py adil-document-uploader/app/workers/settings.py
git commit -m "feat(document-uploader): fetch_acts arq task for OG-RAG statute backfill (P1.5)"
```

P1.5 complete.

---

## Task 12: Provision Railway envs + production smoke

**Files:**
- None (operational task)

- [ ] **Step 1: Confirm `RAG_API_DATABASE_URL` is set on the worker service**

```bash
railway variables --service adil-document-uploader-worker | grep RAG_API_DATABASE_URL
```

If unset (it's used today by `rate_limit_cleanup` — should already exist):

```bash
# Get rag-api's DATABASE_URL from rag-api's env
RAG_DB=$(railway variables --service adil-rag-api -k | grep '^DATABASE_URL=' | cut -d= -f2-)
railway variables --service adil-document-uploader-worker --set RAG_API_DATABASE_URL=$RAG_DB
```

- [ ] **Step 2: Deploy rag-api first (schema migration must land before worker uses it)**

```bash
cd adil-rag-api
railway up
```

Wait for deploy to complete. Migration `004_ograg_ontology_init.sql` runs on startup via `db_migrate.run_migrations`.

- [ ] **Step 3: Verify schema in production**

```bash
railway run --service adil-rag-api psql $DATABASE_URL -c "\dt ontology_node"
```

Expected: table listed.

- [ ] **Step 4: Deploy document-uploader-worker**

```bash
cd ../adil-document-uploader
./deploy.sh adil-document-uploader-worker
```

Wait for deploy.

- [ ] **Step 5: Trigger fetch_acts in production**

The task is registered as a monthly cron — to run it now without waiting:

```bash
railway run --service adil-document-uploader-worker python -c "
import asyncio
from app.workers.tasks import fetch_acts
print(asyncio.run(fetch_acts({})))
"
```

Expected: `{'fetched': 8, 'failed': 0, 'failures': []}`.

- [ ] **Step 6: Verify production data**

```bash
railway run --service adil-rag-api psql $DATABASE_URL -c "
SELECT node_type, COUNT(*) FROM ontology_node GROUP BY node_type ORDER BY 1;
"
```

Expected: counts as in Task 11 Step 4.

- [ ] **Step 7: Mark ClickUp sub-tasks complete**

In ClickUp, set status of `869dbqa0u` (P0.5), `869dbqa1c` (P1), `869dbqa1w` (P1.5) to **done**.

---

## Self-Review

Coverage check vs spec sections:

- §4 Architecture (cross-DB split) ✓ — Tasks 5–11
- §5 Ontology (node types, edge types, hyperedge schema) ✓ — Task 4 (schema), Tasks 9, 11 (Statute/Section/Subsection nodes)
- §6 Extraction pipeline — **out of scope** (P2–P4, plan 2/4)
- §7 Retrieval — **out of scope** (P6, plan 3/4)
- §8 API parity — **out of scope** (P7, plan 3/4)
- §9 Eval gate — partial (P0.5 baseline only; P8 in plan 3/4)
- §10 Phasing — covered for P0.5/P1/P1.5
- §11 Error handling — covered for the in-scope tasks (HTTPStatusError on fetch, idempotent upserts on writer)
- §12 Testing strategy — TDD throughout, real-Postgres integration tests
- §13 Deferred to v2 — covered by spec
- §14 Decision log — covered by spec

Placeholder scan: none found. All code blocks are complete; no "TODO", no "TBD".

Type consistency: `NodeRecord`, `EdgeRecord`, `ParsedAct`, `WrittenAct`, `BaselineRunner`, `OntologyStore`, `OgragWriter`, `LegislationClient` are defined where first used and used consistently downstream.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-19-og-rag-foundation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best fit for a 12-task plan with clean independent boundaries.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
