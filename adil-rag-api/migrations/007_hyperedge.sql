-- 007 — OG-RAG hyperedge table.
--
-- A hyperedge groups a paragraph with all the ontology entities it references.
-- Retrieval ranks over hyperedge.embedding (cosine ANN over the paragraph text).
--
-- Schema aligned with 004_ontology_init.sql (UUID node_ids).
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS hyperedge (
  id              UUID         PRIMARY KEY,
  node_ids        UUID[]       NOT NULL,
  paragraph_text  TEXT         NOT NULL,
  source_node_id  UUID         NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
  embedding       vector(768)  NOT NULL,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS hyperedge_source_idx
  ON hyperedge (source_node_id);

-- ivfflat index on the embedding — lists=100 is conservative for <10k rows.
-- Re-tune (lists ~= sqrt(N)) once backfill completes.
DO $$ BEGIN
  CREATE INDEX hyperedge_embedding_idx
    ON hyperedge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
EXCEPTION WHEN duplicate_table THEN NULL;
END $$;
