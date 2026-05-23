"""`/api/v1/solicitors/near-me` — geo-ranked solicitor finder.

Pipeline:
  1. Validate + geocode user's postcode (postcodes.io, Postgres-cached).
  2. Pull candidate solicitors from the bundled LegalScraper directory
     (filtered by area / language).
  3. Bulk-geocode their postcodes (same cache; mostly hot after first run).
  4. One OSRM `/table` call for the 1×N driving-time matrix.
  5. Sort by duration, drop unreachable, return top `limit`.

Falls back gracefully when OSRM is down: returns results without distances,
ordered alphabetically, with `osrm_available: false` in the response.
"""

from __future__ import annotations

import logging
import re

import osrm_client
import postcodes_io
from solicitor_directory import search_solicitors as ls_search

logger = logging.getLogger(__name__)


SRA_REGISTER_BASE = "https://www.sra.org.uk/consumers/register/person/"


def _sra_url(sra_id: str | None) -> str | None:
    if not sra_id:
        return None
    if not re.match(r"^\d+$", str(sra_id)):
        return None
    return f"{SRA_REGISTER_BASE}?sraNumber={sra_id}"


def _public_solicitor(s: dict) -> dict:
    """Strip to the API contract fields, normalised."""
    return {
        "sra_id": s.get("sra_id"),
        "name": s.get("name"),
        "firm_name": s.get("firm"),
        "role": s.get("role"),
        "address": s.get("address"),
        "postcode": s.get("postcode"),
        "telephone": s.get("telephone"),
        "email": s.get("email"),
        "areas": s.get("areas") or [],
        "languages": s.get("languages") or [],
        "muslim_language": bool(s.get("muslim_language")),
        "regulator_url": _sra_url(s.get("sra_id")),
    }


async def find_near_me(
    *,
    postcode: str,
    pool,
    area: str | None = None,
    language: str | None = None,
    muslim_only: bool = False,
    candidate_pool: int = 50,
    limit: int = 5,
) -> dict:
    """Return the geo-ranked response.

    Args:
        postcode: user's UK postcode (any case/spacing).
        pool: asyncpg Pool or None — used for the postcode cache.
        area: optional practice-area filter (substring, case-insensitive).
        language: optional declared-language filter (exact match).
        muslim_only: restrict to solicitors flagged with a community language.
        candidate_pool: how many candidates to over-fetch before geo-ranking.
        limit: final result count returned to the caller.
    """
    norm_pc = postcodes_io.normalise_postcode(postcode)
    if not postcodes_io.is_valid_uk_postcode(norm_pc):
        return {
            "ok": False,
            "error": "invalid_postcode",
            "message": f"'{postcode}' does not look like a UK postcode.",
            "user": {"postcode": postcode, "lat": None, "lng": None},
            "results": [],
            "osrm_available": False,
        }

    user_coords = await postcodes_io.geocode_postcode(norm_pc, pool=pool)
    if user_coords is None:
        return {
            "ok": False,
            "error": "geocode_failed",
            "message": f"Could not geocode postcode '{postcode}'.",
            "user": {"postcode": norm_pc, "lat": None, "lng": None},
            "results": [],
            "osrm_available": False,
        }
    user_lat, user_lng = user_coords

    candidates = ls_search(
        area=area,
        language=language,
        muslim_only=muslim_only,
        limit=candidate_pool,
    )
    candidates = [c for c in candidates if c.get("postcode")]

    if not candidates:
        return {
            "ok": True,
            "user": {"postcode": norm_pc, "lat": user_lat, "lng": user_lng},
            "results": [],
            "osrm_available": osrm_client.is_enabled(),
            "total_candidates": 0,
        }

    pcs = [c["postcode"] for c in candidates]
    coords_map = await postcodes_io.geocode_postcodes(pcs, pool=pool)

    resolved: list[tuple[dict, tuple[float, float]]] = []
    for c in candidates:
        pc = postcodes_io.normalise_postcode(c.get("postcode"))
        if pc in coords_map:
            resolved.append((c, coords_map[pc]))

    if not resolved:
        return {
            "ok": True,
            "user": {"postcode": norm_pc, "lat": user_lat, "lng": user_lng},
            "results": [],
            "osrm_available": osrm_client.is_enabled(),
            "total_candidates": 0,
        }

    matrix = await osrm_client.driving_table(
        origin=(user_lat, user_lng),
        destinations=[coords for _, coords in resolved],
    )

    rows: list[dict] = []
    if matrix is None:
        # OSRM unavailable — return without distances, alphabetical order.
        for c, _ in resolved:
            item = _public_solicitor(c)
            item["distance_m"] = None
            item["duration_s"] = None
            item["duration_human"] = None
            rows.append(item)
        rows.sort(key=lambda r: (r.get("name") or "").lower())
        return {
            "ok": True,
            "user": {"postcode": norm_pc, "lat": user_lat, "lng": user_lng},
            "results": rows[:limit],
            "osrm_available": False,
            "total_candidates": len(resolved),
        }

    for (c, _), m in zip(resolved, matrix, strict=False):
        item = _public_solicitor(c)
        item["distance_m"] = m.get("distance_m")
        item["duration_s"] = m.get("duration_s")
        item["duration_human"] = osrm_client.duration_human(m.get("duration_s"))
        rows.append(item)

    reachable = [r for r in rows if r["duration_s"] is not None]
    reachable.sort(key=lambda r: r["duration_s"])

    return {
        "ok": True,
        "user": {"postcode": norm_pc, "lat": user_lat, "lng": user_lng},
        "results": reachable[:limit],
        "osrm_available": True,
        "total_candidates": len(resolved),
    }
