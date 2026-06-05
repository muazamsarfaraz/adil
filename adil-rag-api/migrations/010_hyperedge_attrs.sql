-- 010 — reconcile the hyperedge.attrs column.
--
-- Two earlier migrations both `CREATE TABLE IF NOT EXISTS hyperedge`:
--   006_hyperedge.sql — WITH an `attrs JSONB` column
--   007_hyperedge.sql — WITHOUT it
-- The runner (db_migrate.py) has no applied-migrations tracking and re-runs
-- every file in filename order on each boot. Databases whose hyperedge table
-- was first created by 007 (before 006 existed) never gain `attrs`: 006's
-- CREATE IF NOT EXISTS no-ops against the already-present table. The retrieval
-- path (Store.ann_search_hyperedges) SELECTs `attrs`, so those DBs raised
--   column "attrs" does not exist
-- surfaced as the ograg.retrieval_probe error.
--
-- ADD COLUMN IF NOT EXISTS reconciles both schemas regardless of which CREATE
-- won. Idempotent: safe to re-run.

ALTER TABLE hyperedge
  ADD COLUMN IF NOT EXISTS attrs JSONB NOT NULL DEFAULT '{}'::jsonb;
