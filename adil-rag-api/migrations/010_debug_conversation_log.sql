-- Gated raw-content log for debugging specific conversations.
--
-- Population is fully behind the DEBUG_LOG_RAW=1 env var on the rag-api
-- service. With the flag off (the default), no rows are ever written; the
-- table exists but stays empty, identical privacy posture to before.
--
-- Pruned to 7 days of retention by a fire-and-forget cleanup in
-- conversation_log.py — see _maybe_prune_debug_logs().

CREATE TABLE IF NOT EXISTS debug_conversation_logs (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    conversation_id UUID,
    endpoint        VARCHAR(50) NOT NULL,
    query           TEXT,
    response        TEXT,
    sources_json    JSONB,
    error           TEXT,
    response_time_ms INT
);

CREATE INDEX IF NOT EXISTS debug_conversation_logs_created_at_idx
    ON debug_conversation_logs (created_at);

CREATE INDEX IF NOT EXISTS debug_conversation_logs_conversation_id_idx
    ON debug_conversation_logs (conversation_id)
    WHERE conversation_id IS NOT NULL;
