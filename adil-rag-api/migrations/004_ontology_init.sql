-- OG-RAG ontology schema: node + edge tables for the rich ontology
-- (Statute / Section / Subsection / Case / Paragraph / Topic / ...).
-- Idempotent: safe to re-run. See docs/plans/2026-05-17-ograg-migration.md §5.

CREATE TABLE IF NOT EXISTS ontology_node (
  id          UUID         PRIMARY KEY,
  type        TEXT         NOT NULL,
  attrs       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  embedding   vector(768),
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ontology_node_type_idx
  ON ontology_node (type);

CREATE INDEX IF NOT EXISTS ontology_node_attrs_idx
  ON ontology_node
  USING GIN (attrs jsonb_path_ops);

CREATE TABLE IF NOT EXISTS ontology_edge (
  id          UUID         PRIMARY KEY,
  source_id   UUID         NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
  target_id   UUID         NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
  relation    TEXT         NOT NULL,
  attrs       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ontology_edge_source_idx
  ON ontology_edge (source_id, relation);

CREATE INDEX IF NOT EXISTS ontology_edge_target_idx
  ON ontology_edge (target_id, relation);
