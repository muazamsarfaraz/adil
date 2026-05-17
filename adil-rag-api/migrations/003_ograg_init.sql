-- OG-RAG initial schema: pgvector + chunk store.
-- Idempotent: safe to re-run.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ograg_chunks (
  id          UUID         PRIMARY KEY,
  text        TEXT         NOT NULL,
  source      JSONB        NOT NULL DEFAULT '{}'::jsonb,
  embedding   vector(768)  NOT NULL,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- IVFFlat cosine-distance ANN index. lists=10 is appropriate for the
-- few-thousand-chunk MVP corpus; revisit when chunk count >> 50k.
CREATE INDEX IF NOT EXISTS ograg_chunks_embedding_idx
  ON ograg_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 10);
