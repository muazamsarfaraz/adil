-- OG-RAG eval / shadow logging table.
--
-- Used by:
--   * P8 eval harness — writes rows with backend in {'fst','ograg'} side-by-side
--     for a fixed eval-set query.
--   * P9 shadow week — writes rows with backend='ograg_shadow' fire-and-forget
--     alongside every real FST-served user query.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS eval_run (
  id                   BIGSERIAL    PRIMARY KEY,
  created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
  backend              TEXT         NOT NULL,
  query_text           TEXT         NOT NULL,
  answer               TEXT,
  sources              JSONB        NOT NULL DEFAULT '[]'::jsonb,
  latency_ms           INTEGER,
  cost_usd             NUMERIC(10, 6),
  prompt_tokens        INTEGER,
  completion_tokens    INTEGER,
  error                TEXT,
  conversation_history JSONB
);

CREATE INDEX IF NOT EXISTS eval_run_backend_created_idx
  ON eval_run (backend, created_at DESC);

CREATE INDEX IF NOT EXISTS eval_run_created_idx
  ON eval_run (created_at DESC);
