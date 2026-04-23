CREATE TABLE IF NOT EXISTS uploads (
  id              UUID         PRIMARY KEY,
  conversation_id UUID         NOT NULL,
  object_key      TEXT         NOT NULL,
  content_type    TEXT         NOT NULL CHECK (content_type IN ('image/png','image/jpeg','image/webp')),
  size_bytes      INT          NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours')
);

CREATE INDEX IF NOT EXISTS uploads_conversation_id_idx ON uploads (conversation_id);
CREATE INDEX IF NOT EXISTS uploads_expires_at_idx ON uploads (expires_at);
