-- 009_postcode_cache.sql
-- Caches UK postcode → (lat, lng) lookups from postcodes.io.
-- Geometry rarely moves; 90-day TTL is plenty.

CREATE TABLE IF NOT EXISTS postcode_cache (
    postcode TEXT PRIMARY KEY,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS postcode_cache_cached_at_idx
    ON postcode_cache (cached_at);
