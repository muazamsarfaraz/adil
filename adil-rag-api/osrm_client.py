"""OSRM /table client for 1×N driving-time matrices.

Env-driven, mirroring the chatbot-service convention:
- `OSRM_SERVICE_URL` — self-hosted endpoint (e.g. the Railway osrmproj service)
- `USE_OSRM` — off-switch for local dev (default: "true")
- Falls back to public `router.project-osrm.org` for development only.

One `/table` request returns a duration matrix in a single round-trip —
typically 100-200ms for 50 destinations.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_URL = "https://router.project-osrm.org"
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


def _osrm_base_url() -> str | None:
    """Return the configured OSRM base URL, or None if disabled."""
    use_osrm = os.environ.get("USE_OSRM", "true").strip().lower()
    if use_osrm in ("0", "false", "no", "off"):
        return None
    return os.environ.get("OSRM_SERVICE_URL", DEFAULT_PUBLIC_URL).rstrip("/")


def is_enabled() -> bool:
    return _osrm_base_url() is not None


async def driving_table(
    origin: tuple[float, float],
    destinations: list[tuple[float, float]],
    *,
    profile: str = "driving",
) -> list[dict] | None:
    """Compute driving distance + duration from `origin` to each destination.

    Returns a list aligned with `destinations`, each item shaped:
        {"distance_m": float | None, "duration_s": float | None}
    OSRM returns null entries for unreachable points.

    Returns `None` if OSRM is disabled or the call fails — callers should
    fall back to returning results without distances.
    """
    if not destinations:
        return []

    base = _osrm_base_url()
    if base is None:
        return None

    # OSRM coords are "lng,lat" — easy to swap by mistake.
    coords = ";".join([f"{origin[1]},{origin[0]}"] + [f"{d[1]},{d[0]}" for d in destinations])
    dest_indices = ";".join(str(i + 1) for i in range(len(destinations)))
    url = f"{base}/table/v1/{profile}/{coords}" f"?sources=0&destinations={dest_indices}&annotations=duration,distance"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning("OSRM /table call failed: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning("OSRM /table -> %s: %s", resp.status_code, resp.text[:200])
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    if data.get("code") != "Ok":
        logger.warning("OSRM /table non-Ok response: %s", data.get("code"))
        return None

    durations = (data.get("durations") or [[]])[0]
    distances = (data.get("distances") or [[]])[0]

    out: list[dict] = []
    for i in range(len(destinations)):
        dur = durations[i] if i < len(durations) else None
        dist = distances[i] if i < len(distances) else None
        out.append(
            {
                "distance_m": float(dist) if dist is not None else None,
                "duration_s": float(dur) if dur is not None else None,
            }
        )
    return out


def duration_human(seconds: float | None) -> str | None:
    """Format a duration in seconds as a compact human label, e.g. "6 min"."""
    if seconds is None:
        return None
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if m else f"{h} h"
