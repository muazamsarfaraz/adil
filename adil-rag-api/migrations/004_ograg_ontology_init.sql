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
  natural_key text NOT NULL,
  attrs jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(768),
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
  source_doc_id bigint NOT NULL,
  embedding vector(768) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ivfflat index — needs ANALYZE before being used efficiently; the seeder runs ANALYZE.
DO $$ BEGIN
  CREATE INDEX hyperedge_embedding_idx ON hyperedge
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
EXCEPTION WHEN duplicate_table THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS eval_run (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  backend text NOT NULL,
  query_id text NOT NULL,
  query text NOT NULL,
  answer text,
  sources jsonb,
  latency_ms integer,
  cost_usd numeric(10, 6),
  judge_score jsonb,
  human_grade text
);

CREATE INDEX IF NOT EXISTS eval_run_ts_idx ON eval_run (ts DESC);
CREATE INDEX IF NOT EXISTS eval_run_backend_query_idx ON eval_run (backend, query_id);
