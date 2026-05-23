"""UK postcode geocoder using postcodes.io with a Postgres cache.

postcodes.io is free, no API key, UK-only, sub-100ms. We cache (postcode → lat/lng)
in the `postcode_cache` Postgres table with a 90-day TTL — UK postcode geometry
rarely moves so this gives near-zero cost on subsequent lookups.

The Postgres cache is optional: if `pool` is None or the cache table is missing,
we degrade to direct postcodes.io calls.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

POSTCODES_IO_BASE = "https://api.postcodes.io"
CACHE_TTL_DAYS = 90
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)

_UK_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$")


def normalise_postcode(postcode: str) -> str:
    """Uppercase, no internal whitespace. postcodes.io accepts both forms."""
    return (postcode or "").upper().replace(" ", "").strip()


def is_valid_uk_postcode(postcode: str) -> bool:
    """Loose UK postcode shape check. Real validity is decided by postcodes.io."""
    if not postcode:
        return False
    return bool(_UK_POSTCODE_RE.match(postcode.upper().strip()))


async def _cache_get(pool: Any, postcode: str) -> tuple[float, float] | None:
    if pool is None:
        return None
    cutoff = datetime.now(tz=UTC) - timedelta(days=CACHE_TTL_DAYS)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT lat, lng FROM postcode_cache " "WHERE postcode = $1 AND cached_at > $2",
                postcode,
                cutoff,
            )
    except Exception as e:
        logger.debug("postcode_cache read failed: %s", e)
        return None
    if row is None:
        return None
    return (float(row["lat"]), float(row["lng"]))


async def _cache_put(pool: Any, postcode: str, lat: float, lng: float) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO postcode_cache (postcode, lat, lng, cached_at) "
                "VALUES ($1, $2, $3, NOW()) "
                "ON CONFLICT (postcode) DO UPDATE "
                "SET lat = EXCLUDED.lat, lng = EXCLUDED.lng, cached_at = NOW()",
                postcode,
                lat,
                lng,
            )
    except Exception as e:
        logger.debug("postcode_cache write failed: %s", e)


async def _fetch_single(client: httpx.AsyncClient, postcode: str) -> tuple[float, float] | None:
    try:
        resp = await client.get(f"{POSTCODES_IO_BASE}/postcodes/{postcode}")
    except httpx.HTTPError as e:
        logger.warning("postcodes.io fetch failed for %s: %s", postcode, e)
        return None
    if resp.status_code != 200:
        logger.debug("postcodes.io %s -> %s", postcode, resp.status_code)
        return None
    try:
        data = resp.json().get("result") or {}
    except ValueError:
        return None
    lat, lng = data.get("latitude"), data.get("longitude")
    if lat is None or lng is None:
        return None
    return (float(lat), float(lng))


async def geocode_postcode(postcode: str, pool: Any | None = None) -> tuple[float, float] | None:
    """Geocode a single UK postcode. Returns (lat, lng) or None."""
    pc = normalise_postcode(postcode)
    if not pc:
        return None
    cached = await _cache_get(pool, pc)
    if cached is not None:
        return cached
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        coords = await _fetch_single(client, pc)
    if coords is not None:
        await _cache_put(pool, pc, coords[0], coords[1])
    return coords


async def geocode_postcodes(postcodes: list[str], pool: Any | None = None) -> dict[str, tuple[float, float]]:
    """Bulk geocode. Returns {normalised_postcode: (lat,lng)} only for hits."""
    if not postcodes:
        return {}
    normalised = list({normalise_postcode(p) for p in postcodes if p})
    out: dict[str, tuple[float, float]] = {}
    missing: list[str] = []

    for pc in normalised:
        cached = await _cache_get(pool, pc)
        if cached is not None:
            out[pc] = cached
        else:
            missing.append(pc)

    if not missing:
        return out

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for batch_start in range(0, len(missing), 100):
            batch = missing[batch_start : batch_start + 100]
            try:
                resp = await client.post(
                    f"{POSTCODES_IO_BASE}/postcodes",
                    json={"postcodes": batch},
                )
            except httpx.HTTPError as e:
                logger.warning("postcodes.io bulk fetch failed: %s", e)
                continue
            if resp.status_code != 200:
                logger.debug("postcodes.io bulk -> %s", resp.status_code)
                continue
            try:
                results = resp.json().get("result") or []
            except ValueError:
                continue
            for item in results:
                query = normalise_postcode(item.get("query") or "")
                res = item.get("result") or {}
                lat, lng = res.get("latitude"), res.get("longitude")
                if query and lat is not None and lng is not None:
                    coords = (float(lat), float(lng))
                    out[query] = coords
                    await _cache_put(pool, query, coords[0], coords[1])

    return out
