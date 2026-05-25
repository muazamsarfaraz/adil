"""SRA register verification tool.

Queries adil-rag-api's solicitor directory (LegalScraper-backed) instead of
scraping `sra.org.uk` directly. The live SRA portal is captcha-walled,
~3-10s per call with a high failure rate; rag-api serves the same data
locally in ~5ms and returns richer fields (practice areas, languages,
accreditations) sourced from LegalScraper.

Two query modes:
  * Numeric input -> /api/v1/solicitors/verify/{sra_id}
  * Anything else -> /api/v1/solicitors/search?name=...
"""

import re

import httpx
from langchain_core.tools import tool

from app.config import settings

_TIMEOUT = 10.0
_SRA_ID_RE = re.compile(r"^\d{4,8}$")


def _format_record(record: dict) -> str:
    areas = ", ".join(record.get("practice_areas") or []) or "—"
    languages = ", ".join(record.get("languages") or []) or "—"
    accreditations = ", ".join(record.get("accreditations") or []) or "—"
    return (
        f"SRA Number: {record.get('sra_id', 'N/A')}\n"
        f"Name: {record.get('name', '—')}\n"
        f"Status: {record.get('sra_status', '—')}\n"
        f"Firm: {record.get('firm_name', '—')}\n"
        f"Role: {record.get('role', '—')}\n"
        f"Address: {record.get('address', '—')}\n"
        f"Practice Areas: {areas}\n"
        f"Languages: {languages}\n"
        f"Accreditations: {accreditations}"
    )


@tool
async def search_sra_register(name: str, firm: str = "") -> str:
    """Search the SRA (Solicitors Regulation Authority) register for a solicitor or firm.

    Backed by adil-rag-api's LegalScraper-derived directory. Pass a 4-8 digit
    SRA number as ``name`` for an exact verify; otherwise a name substring
    search runs across the bundled per-solicitor index.

    Args:
        name: SRA number, or solicitor/firm name to search for.
        firm: Optional firm name substring to narrow results.

    Returns:
        Plain-text block(s) with SRA number, name, status, firm, address,
        practice areas, and declared languages. On failure, returns a
        graceful "Proceeding without SRA verification" message so the agent
        loop is never broken by a directory outage.
    """
    base = settings.rag_api_base_url.rstrip("/")
    headers = {"X-API-Key": settings.rag_api_key} if settings.rag_api_key else {}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if _SRA_ID_RE.match(name.strip()):
                sra_id = name.strip()
                resp = await client.get(f"{base}/api/v1/solicitors/verify/{sra_id}", headers=headers)
                if resp.status_code == 404:
                    return f"No SRA registration found for SRA ID {sra_id}"
                if resp.status_code != 200:
                    return (
                        f"Error: rag-api returned HTTP {resp.status_code}. "
                        f"Unable to verify registration for {name}. "
                        "Proceeding without SRA verification."
                    )
                payload = resp.json()
                record = payload.get("solicitor") or {}
                if not record:
                    return f"No SRA registration found for SRA ID {sra_id}"
                return f"SRA Register record for {sra_id}:\n\n" + _format_record(record)

            params: dict[str, str] = {"name": name, "limit": "3"}
            if firm:
                params["name"] = f"{name} {firm}".strip()
            resp = await client.get(f"{base}/api/v1/solicitors/search", params=params, headers=headers)
            if resp.status_code != 200:
                return (
                    f"Error: rag-api returned HTTP {resp.status_code}. "
                    f"Unable to verify registration for {name}. "
                    "Proceeding without SRA verification."
                )
            payload = resp.json()
            records = payload.get("solicitors") or []
            if firm:
                firm_lc = firm.lower()
                filtered = [r for r in records if firm_lc in (r.get("firm_name") or "").lower()]
                if filtered:
                    records = filtered
            if not records:
                return f"No SRA registration found for {name}" + (f" at {firm}" if firm else "")
            header = f"SRA Register results for '{name}'" + (f" at '{firm}'" if firm else "") + ":\n\n"
            blocks = [_format_record(r) for r in records[:3]]
            return header + "\n---\n".join(blocks)

    except httpx.TimeoutException:
        return (
            f"Error: rag-api timed out after {_TIMEOUT}s. "
            f"Unable to verify registration for {name}. "
            "Proceeding without SRA verification."
        )
    except httpx.ConnectError:
        return (
            "Error: Could not connect to rag-api solicitor directory. "
            f"Unable to verify registration for {name}. "
            "Proceeding without SRA verification."
        )
    except Exception as e:
        return f"Error querying SRA register: {type(e).__name__}: {e}. " "Proceeding without SRA verification."
