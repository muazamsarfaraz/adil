"""Curated solicitor directory for AskAdil.

Sources (priority order):
1. Postgres solicitor_firms table — populated monthly by adil-document-uploader's
   scrape_solicitors arq task. Always preferred when available and non-empty.
2. Bundled SRA JSON — adil-rag-api/docs/sra_firms.json (static fallback).
3. Manually curated seed database — docs/plans/muslim-solicitors-seed-database.json

All firms are pending outreach — none have consented to be listed.
Contact details are from publicly available sources only.
SRA data: "data supplied by the Solicitors Regulation Authority"
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Disclaimer text returned with every directory response
DISCLAIMER = (
    "AskAdil does not endorse or guarantee any solicitor. All firms listed are "
    "pending outreach — none have consented to be listed yet. Contact details are "
    "from publicly available sources only. Firm data includes information supplied "
    "by the Solicitors Regulation Authority."
)

# Fields to expose in the API response
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
    "phone",
    "email",
    "sra_url",
]

# --- SRA data mapping ---

_SRA_SPECIALISMS = [
    "employment law",
    "discrimination law",
    "human rights",
    "civil liberties",
    "equality act",
    "hate crime",
    "mental capacity",
    "court of protection",
]


def _sra_to_firm(raw: dict) -> dict:
    """Map a scraped SRA firm record to the internal firm schema."""
    city = raw.get("city") or ""
    address = raw.get("address") or ""
    # Determine jurisdiction from address
    if re.search(r"\bScotland\b|\bScottish\b", address, re.I):
        jurisdiction = "Scotland"
    elif re.search(r"\bWales\b|\bWelsh\b|\bCymru\b", address, re.I):
        jurisdiction = "England and Wales"
    elif re.search(r"\bNorthern Ireland\b", address, re.I):
        jurisdiction = "Northern Ireland"
    else:
        jurisdiction = "England and Wales"  # default for SRA-regulated

    locations = [city] if city else []
    # Add postcode area for broader matching
    pc = re.search(r"([A-Z]{1,2}\d{1,2}[A-Z]?)\s*\d", address)
    if pc:
        locations.append(pc.group(1))

    website = raw.get("website")
    contact_url = website or raw.get("sra_url")

    return {
        "id": f"sra-{raw['sra_number']}",
        "name": raw.get("name", ""),
        "category": "sra_registered",
        "website": website,
        "locations": locations,
        "jurisdiction": jurisdiction,
        "specialisms": _SRA_SPECIALISMS,
        "muslim_focus": False,
        "notable": None,
        "contact_url": contact_url,
        "outreach_status": "pending",
        "phone": raw.get("phone"),
        "email": raw.get("email"),
        "sra_url": raw.get("sra_url"),
        "legal_aid": raw.get("legal_aid", False),
        "address": address,
    }


# --- Load databases ---

_firms: list[dict] = []


def _load_seed_database() -> list[dict]:
    """Load all firm sources: curated seed + SRA register scrape."""
    module_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    all_firms: list[dict] = []

    # 1. Curated seed database (manually maintained)
    seed_path = module_dir / "docs" / "plans" / "muslim-solicitors-seed-database.json"
    if seed_path.exists():
        try:
            with open(seed_path, encoding="utf-8") as f:
                data = json.load(f)
            seed_firms = data.get("firms", [])
            all_firms.extend(seed_firms)
            logger.info("Loaded %d firms from seed database", len(seed_firms))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load seed database: %s", e)

    # 2. SRA register scrape
    sra_path = module_dir / "docs" / "sra_firms.json"
    if sra_path.exists():
        try:
            with open(sra_path, encoding="utf-8") as f:
                sra_raw = json.load(f)
            sra_firms = [_sra_to_firm(r) for r in sra_raw]
            # Deduplicate by name against seed
            seed_names = {f.get("name", "").lower() for f in all_firms}
            new_sra = [f for f in sra_firms if f["name"].lower() not in seed_names]
            all_firms.extend(new_sra)
            logger.info("Loaded %d SRA firms (%d new after dedup)", len(sra_firms), len(new_sra))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load SRA firms: %s", e)

    if not all_firms:
        logger.warning("No solicitor data loaded from any source")
    return all_firms


async def _load_from_db() -> list[dict]:
    """Load SRA firms from the solicitor_firms Postgres table (populated by document-uploader)."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return []
    try:
        import asyncpg

        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch("SELECT * FROM solicitor_firms ORDER BY name")
        finally:
            await conn.close()

        firms = []
        for r in rows:
            row = dict(r)
            firms.append(_sra_to_firm(row))
        logger.info("Loaded %d firms from solicitor_firms Postgres table", len(firms))
        return firms
    except Exception as e:
        logger.warning("Could not load solicitor_firms from DB: %s", e)
        return []


async def refresh_from_db() -> int:
    """Reload _firms from Postgres. Call on startup and after scrape_solicitors runs.

    Returns the number of DB firms loaded (0 means DB unavailable; JSON fallback used).
    """
    global _firms
    db_firms = await _load_from_db()
    if db_firms:
        # Merge: DB firms + curated seed (seed takes precedence for duplicates)
        seed_firms = _load_seed_database()
        db_names = {f["name"].lower() for f in seed_firms}
        merged = seed_firms + [f for f in db_firms if f["name"].lower() not in db_names]
        _firms = merged
        logger.info("solicitor_directory refreshed: %d total firms (%d from DB)", len(_firms), len(db_firms))
        return len(db_firms)
    else:
        # Fall back to JSON files
        _firms = _load_seed_database()
        logger.info("solicitor_directory loaded from JSON: %d firms", len(_firms))
        return 0


def _ensure_loaded() -> list[dict]:
    """Lazily load firms on first access (sync fallback — skips DB)."""
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
