CREATE TABLE IF NOT EXISTS rate_limit_counters (
  bucket_key   TEXT        NOT NULL,
  bucket_start TIMESTAMPTZ NOT NULL,
  count        INT         NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket_key, bucket_start)
);

CREATE INDEX IF NOT EXISTS rate_limit_counters_bucket_start_idx
  ON rate_limit_counters (bucket_start);
