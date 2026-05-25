-- OG-RAG hyperedge table for paper Algorithm-1 cover retrieval.
-- Each row = (set of ontology_node ids that co-occur in a paragraph,
-- the paragraph text itself, its embedding, optional source node link).
-- Idempotent.

CREATE TABLE IF NOT EXISTS hyperedge (
  id              UUID         PRIMARY KEY,
  node_ids        UUID[]       NOT NULL,
  paragraph_text  TEXT         NOT NULL,
  source_node_id  UUID         REFERENCES ontology_node(id) ON DELETE CASCADE,
  embedding       vector(768)  NOT NULL,
  attrs           JSONB        NOT NULL DEFAULT '{}'::jsonb,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS hyperedge_embedding_idx
  ON hyperedge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS hyperedge_node_ids_idx
  ON hyperedge USING GIN (node_ids);

CREATE INDEX IF NOT EXISTS hyperedge_source_node_idx
  ON hyperedge (source_node_id);
