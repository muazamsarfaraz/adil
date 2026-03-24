"""Curated solicitor directory for AskAdil.

Loads the seed database of Muslim solicitors and provides filtering functions.
All firms are pending outreach - none have consented to be listed yet.
Contact details are from publicly available sources only.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Disclaimer text returned with every directory response
DISCLAIMER = (
    "AskAdil does not endorse or guarantee any solicitor. All firms listed are "
    "pending outreach — none have consented to be listed yet. Contact details "
    "are from publicly available sources only."
)

# Fields to expose in the API response (exclude internal/sensitive fields)
PUBLIC_FIELDS = [
    "id",
    "name",
    "category",
    "website",
    "locations",
    "jurisdiction",
    "specialisms",
    "muslim_focus",
    "notable",
    "contact_url",
    "outreach_status",
]

# --- Load seed database ---

_firms: list[dict] = []


def _load_seed_database() -> list[dict]:
    """Load the solicitor seed database from the JSON file.

    Searches for the file relative to this module's directory.
    """
    # Try relative to this module first
    module_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        module_dir / "docs" / "plans" / "muslim-solicitors-seed-database.json",
    ]

    for path in candidates:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                firms = data.get("firms", [])
                logger.info("Loaded %d firms from %s", len(firms), path)
                return firms
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to load seed database from %s: %s", path, e)
                return []

    logger.warning("Solicitor seed database not found. Tried: %s", [str(p) for p in candidates])
    return []


def _ensure_loaded() -> list[dict]:
    """Lazily load firms on first access."""
    global _firms
    if not _firms:
        _firms = _load_seed_database()
    return _firms


def _public_firm(firm: dict) -> dict:
    """Return only the public-facing fields for a firm."""
    return {k: firm[k] for k in PUBLIC_FIELDS if k in firm}


def get_solicitors(
    jurisdiction: str | None = None,
    specialism: str | None = None,
    location: str | None = None,
) -> list[dict]:
    """Return solicitors matching the given filters.

    All filters are optional. If no filters are provided, all firms are returned.

    Args:
        jurisdiction: Case-insensitive partial match on the firm's jurisdiction field.
        specialism: Case-insensitive check if this term appears in any of the firm's specialisms.
        location: Case-insensitive partial match on any of the firm's locations.

    Returns:
        List of firm dicts with public fields only.
    """
    firms = _ensure_loaded()
    results = firms

    if jurisdiction:
        jurisdiction_lower = jurisdiction.lower()
        results = [f for f in results if jurisdiction_lower in f.get("jurisdiction", "").lower()]

    if specialism:
        specialism_lower = specialism.lower()
        results = [f for f in results if any(specialism_lower in s.lower() for s in f.get("specialisms", []))]

    if location:
        location_lower = location.lower()
        results = [f for f in results if any(location_lower in loc.lower() for loc in f.get("locations", []))]

    return [_public_firm(f) for f in results]
