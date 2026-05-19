-- Add meta JSONB to eval_run so the P8 eval harness can tag rows with a
-- run_id, eval-set version, and (after P8 judge) the rubric scores.
--
-- Existing rows (P9 shadow) get the default '{}'::jsonb.
-- Idempotent.

ALTER TABLE eval_run
  ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Index on run_id for fast fetch of all rows from a single eval session.
CREATE INDEX IF NOT EXISTS eval_run_run_id_idx
  ON eval_run ((meta->>'run_id'));
