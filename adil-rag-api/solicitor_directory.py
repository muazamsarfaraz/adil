"""Curated solicitor directory for AskAdil.

Firm-level sources (priority order):
1. Postgres solicitor_firms table — populated monthly by adil-document-uploader's
   scrape_solicitors arq task. Always preferred when available and non-empty.
2. Bundled SRA JSON — adil-rag-api/docs/sra_firms.json (static fallback).
3. Manually curated seed database — docs/plans/muslim-solicitors-seed-database.json

Solicitor-level (per-person) source for ``search_solicitors`` /
``/api/v1/solicitors/search``:
4. LegalScraper landing export — adil-rag-api/docs/legalscraper_landing.json,
   ~1,500 enriched solicitor profiles with practice areas, languages,
   accreditations and SRA IDs. Provided by the sibling LegalScraper project;
   refresh recipe is in LegalScraper/INTEGRATION.md §4.3.

All firms and solicitors are pending outreach — none have consented to be
listed. Contact details are from publicly available sources only.
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
            # SRA pages occasionally yield Windows smart quotes (0x91/0x92);
            # `errors="replace"` keeps load resilient against odd bytes.
            with open(sra_path, encoding="utf-8", errors="replace") as f:
                sra_raw = json.load(f)
            sra_firms = [_sra_to_firm(r) for r in sra_raw]
            # Deduplicate by name against seed
            seed_names = {f.get("name", "").lower() for f in all_firms}
            new_sra = [f for f in sra_firms if f["name"].lower() not in seed_names]
            all_firms.extend(new_sra)
            logger.info("Loaded %d SRA firms (%d new after dedup)", len(sra_firms), len(new_sra))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
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


# =============================================================================
# Per-solicitor search (LegalScraper landing data)
# =============================================================================

# Languages we treat as "Muslim community" signals — mirrors LegalScraper's
# DirectoryClient.MUSLIM_LANGUAGES. Source: LegalScraper/src/directory_client.py.
MUSLIM_LANGUAGES = (
    "Urdu",
    "Arabic",
    "Bengali",
    "Punjabi",
    "Persian",
    "Turkish",
    "Sylheti",
    "Gujarati",
    "Pashto",
    "Somali",
    "Kurdish",
    "Malay",
    "Indonesian",
)
_MUSLIM_LANGUAGES_LOWER = {lang.lower() for lang in MUSLIM_LANGUAGES}

SOLICITOR_PUBLIC_FIELDS = (
    "sra_id",
    "name",
    "firm",
    "role",
    "address",
    "postcode",
    "telephone",
    "email",
    "areas",
    "languages",
    "accreditations",
    "muslim_language",
)

_solicitors: list[dict] = []


def _load_landing_solicitors() -> list[dict]:
    """Load per-solicitor records from the bundled LegalScraper landing export.

    Returns an empty list if the file is missing or malformed.
    """
    # Allow override for ops / tests.
    override = os.getenv("LEGALSCRAPER_LANDING_PATH")
    if override:
        path = Path(override)
    else:
        module_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        path = module_dir / "docs" / "legalscraper_landing.json"

    if not path.exists():
        logger.warning("LegalScraper landing JSON not found at %s", path)
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load LegalScraper landing JSON: %s", e)
        return []

    raw = data.get("solicitors") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        logger.warning("LegalScraper landing JSON missing 'solicitors' list")
        return []

    logger.info("Loaded %d solicitor profiles from LegalScraper landing export", len(raw))
    return raw


def _ensure_solicitors_loaded() -> list[dict]:
    global _solicitors
    if not _solicitors:
        _solicitors = _load_landing_solicitors()
    return _solicitors


def _public_solicitor(s: dict) -> dict:
    return {k: s.get(k) for k in SOLICITOR_PUBLIC_FIELDS if k in s}


def _postcode_outward(value: str | None) -> str:
    """Normalise a postcode-ish string to its outward code prefix (e.g. 'M11AA' -> 'M1', 'EC2N 4AY' -> 'EC2N')."""
    if not value:
        return ""
    cleaned = re.sub(r"\s+", "", value).upper()
    match = re.match(r"^([A-Z]{1,2}\d[A-Z\d]?)", cleaned)
    return match.group(1) if match else cleaned


def search_solicitors(
    area: str | None = None,
    language: str | None = None,
    postcode_prefix: str | None = None,
    name: str | None = None,
    muslim_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Search the LegalScraper per-solicitor index.

    All filters are case-insensitive partial matches. ``postcode_prefix`` matches
    against the outward portion of each solicitor's postcode (e.g. ``"M"``,
    ``"M1"``, ``"EC2N"``). ``muslim_only`` restricts to solicitors who declared
    any language in :data:`MUSLIM_LANGUAGES`.

    Returns at most ``limit`` records (capped to 200). Each record contains only
    the fields in :data:`SOLICITOR_PUBLIC_FIELDS`.
    """
    capped_limit = max(1, min(int(limit or 50), 200))
    rows = _ensure_solicitors_loaded()
    results: list[dict] = []

    area_lc = area.lower().strip() if area else None
    lang_lc = language.lower().strip() if language else None
    name_lc = name.lower().strip() if name else None
    pc_prefix = _postcode_outward(postcode_prefix) if postcode_prefix else None

    for s in rows:
        if muslim_only and not s.get("muslim_language"):
            continue

        if area_lc:
            if not any(area_lc in (a or "").lower() for a in s.get("areas") or []):
                continue

        if lang_lc:
            if not any(
                lang_lc == (lg or "").lower() or lang_lc in (lg or "").lower() for lg in s.get("languages") or []
            ):
                continue

        if pc_prefix:
            outward = _postcode_outward(s.get("postcode"))
            if not outward.startswith(pc_prefix):
                continue

        if name_lc:
            if name_lc not in (s.get("name") or "").lower():
                continue

        results.append(_public_solicitor(s))
        if len(results) >= capped_limit:
            break

    return results


def list_practice_areas(limit: int = 200) -> list[str]:
    """Return the distinct practice-area strings present in the per-solicitor index."""
    rows = _ensure_solicitors_loaded()
    seen: set[str] = set()
    for s in rows:
        for a in s.get("areas") or []:
            if a:
                seen.add(a)
    return sorted(seen)[:limit]


def list_languages(limit: int = 200) -> list[str]:
    """Return the distinct language strings present in the per-solicitor index."""
    rows = _ensure_solicitors_loaded()
    seen: set[str] = set()
    for s in rows:
        for lg in s.get("languages") or []:
            if lg:
                seen.add(lg)
    return sorted(seen)[:limit]


def verify_solicitor_by_sra_id(sra_id: str) -> dict | None:
    """Return the public record for the given SRA ID, or None if not found.

    Replacement for adil-outreach-engine's live SRA HTTP call when the
    bundled LegalScraper export covers the requested ID. Outreach-engine
    should retain a live fallback for IDs not yet ingested.
    """
    if not sra_id:
        return None
    needle = str(sra_id).strip()
    for s in _ensure_solicitors_loaded():
        if str(s.get("sra_id") or "").strip() == needle:
            return _public_solicitor(s)
    return None
