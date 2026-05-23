-- adil-whatsapp-bridge: per-phone session state.
-- Tracks jurisdiction, rolling history, consent, and rate-limit counters
-- on a single row per E.164 phone number. Idempotent.

CREATE TABLE IF NOT EXISTS wa_sessions (
    phone_e164         TEXT PRIMARY KEY,
    jurisdiction       TEXT,
    conversation_id    UUID,
    history            JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_message_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    consent_at         TIMESTAMPTZ,
    msg_count_minute   INTEGER NOT NULL DEFAULT 0,
    msg_minute_start   TIMESTAMPTZ NOT NULL DEFAULT now(),
    msg_count_day      INTEGER NOT NULL DEFAULT 0,
    msg_day_start      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wa_sessions_last_message_idx
    ON wa_sessions(last_message_at);

-- Aggregate daily spend counter for the cost-cap kill switch.
CREATE TABLE IF NOT EXISTS wa_outbound_spend (
    day            DATE PRIMARY KEY,
    messages       INTEGER NOT NULL DEFAULT 0,
    cents_spent    INTEGER NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
