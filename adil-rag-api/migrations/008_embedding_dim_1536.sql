-- 008 — switch embedding dim 768 → 1536 (OpenAI text-embedding-3-small)
--
-- Decision recorded in
-- docs/superpowers/specs/2026-05-19-og-rag-migration-design.md §14 (revised 2026-05-19).
--
-- pgvector's vector(N) types are not auto-castable across dimensions, so we
-- drop and recreate the columns. Existing data is lost — the seeder must
-- re-run after this migration applies. The 66 MVP chunks come from
-- LEGISLATION_SNIPPETS + UK_CASE_LAW in code, so re-seeding is cheap.
--
-- Idempotent guard: we only run the resize when the current dim is 768.

DO $$
DECLARE
  cur_dim integer;
BEGIN
  -- ograg_chunks (MVP table) ------------------------------------------------
  SELECT atttypmod INTO cur_dim
  FROM pg_attribute
  WHERE attrelid = 'ograg_chunks'::regclass AND attname = 'embedding';

  IF cur_dim IS NOT NULL AND cur_dim <> 1536 THEN
    -- Drop ANN index first (depends on the column).
    DROP INDEX IF EXISTS ograg_chunks_embedding_idx;
    ALTER TABLE ograg_chunks DROP COLUMN embedding;
    ALTER TABLE ograg_chunks ADD COLUMN embedding vector(1536);
    CREATE INDEX ograg_chunks_embedding_idx ON ograg_chunks
      USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
  END IF;

  -- ontology_node (P1 schema) ------------------------------------------------
  SELECT atttypmod INTO cur_dim
  FROM pg_attribute
  WHERE attrelid = 'ontology_node'::regclass AND attname = 'embedding';

  IF cur_dim IS NOT NULL AND cur_dim <> 1536 THEN
    ALTER TABLE ontology_node DROP COLUMN embedding;
    ALTER TABLE ontology_node ADD COLUMN embedding vector(1536);
  END IF;

  -- hyperedge (007 schema) ---------------------------------------------------
  SELECT atttypmod INTO cur_dim
  FROM pg_attribute
  WHERE attrelid = 'hyperedge'::regclass AND attname = 'embedding';

  IF cur_dim IS NOT NULL AND cur_dim <> 1536 THEN
    DROP INDEX IF EXISTS hyperedge_embedding_idx;
    ALTER TABLE hyperedge DROP COLUMN embedding;
    ALTER TABLE hyperedge ADD COLUMN embedding vector(1536) NOT NULL DEFAULT (array_fill(0, ARRAY[1536])::vector);
    ALTER TABLE hyperedge ALTER COLUMN embedding DROP DEFAULT;
    CREATE INDEX hyperedge_embedding_idx ON hyperedge
      USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
  END IF;
END $$;

-- Note: existing rows in ograg_chunks now have embedding = NULL after the
-- column was recreated. The seeder must re-run to repopulate. Likewise for
-- hyperedge (which is empty anyway pre-P5 backfill).
