"""Async SRA register scraper for the solicitor directory.

Scrapes https://www.sra.org.uk/consumers/register/ for firms practising in
employment, discrimination, human rights, hate crime, mental capacity, and
court of protection. Stores results in the solicitor_firms Postgres table.

The SRA register has no JSON API — all responses are HTML.
Attribution required: "data supplied by the Solicitors Regulation Authority"
"""

from __future__ import annotations

import logging
import re
from html import unescape

import httpx

logger = logging.getLogger(__name__)

SRA_BASE = "https://www.sra.org.uk"
SRA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{SRA_BASE}/consumers/register/",
}
SEARCH_TERMS = [
    "employment discrimination",
    "equality act discrimination",
    "hate crime",
    "mental capacity",
    "human rights civil liberties",
    "religious discrimination",
    "race discrimination",
    "court of protection",
]
# Exclude government bodies, courts, and public authorities by name
_EXCLUDE_RE = re.compile(
    r"court|tribunal|police|ministry|department|council|authority|government|"
    r"commission|parliament|crown|HMRC|judiciary|military|armed forces|"
    r"cabinet|treasury|inland revenue|dvla|dvsa|hmcts|prison|probation|"
    r"civil aviation|companies house|environment agency",
    re.I,
)


async def search_firms(client: httpx.AsyncClient, search_text: str) -> list[tuple[int, str]]:
    """Return (sra_number, firm_name) tuples matching the search term."""
    resp = await client.get(
        f"{SRA_BASE}/consumers/register/",
        params={
            "searchText": search_text,
            "searchBy": "Organisation",
            "numberOfResults": 500,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resp.raise_for_status()
    html = resp.text
    sra_numbers = re.findall(r"goToOrgDetails\((\d+)\)", html)
    names = re.findall(r'<h2 class="h5 h2-no-border">\s*(.+?)\s*</h2>', html)
    return [(int(n), names[i].strip() if i < len(names) else "") for i, n in enumerate(sra_numbers)]


def _parse_detail(sra_number: int, html: str) -> dict:
    """Parse firm detail HTML into a dict."""
    m = re.search(r"<h1[^>]*>\s*(.+?)\s*</h1>", html, re.S)
    name = unescape(re.sub(r"<[^>]+>", "", m.group(1) if m else "").strip())

    grey = re.findall(r'<span class="address-grey-text">([^<]+)</span>', html)
    address = grey[0].strip() if grey else None
    raw_phone = grey[1].strip() if len(grey) > 1 else None
    phone = raw_phone if raw_phone and re.search(r"\d{5,}", raw_phone) else None

    email_m = re.search(r'href="mailto:([^"]+)"', html, re.I)
    email = email_m.group(1).strip() if email_m else None

    city = None
    if address:
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 4:
            city = parts[-4]
        elif len(parts) >= 2:
            city = parts[-2]
        if city and re.search(r"\d", city):
            city = None

    body = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S | re.I)
    legal_aid = bool(re.search(r"\blegal aid\b", body, re.I))

    web_m = re.search(
        r"<dt[^>]*>\s*<strong>Website</strong>\s*</dt>\s*<dd[^>]*>\s*([^\s<]{4,100})\s*</dd>",
        html,
        re.S | re.I,
    )
    website = web_m.group(1).strip() if web_m else None
    if website and not website.startswith("http"):
        website = "https://" + website

    type_m = re.search(
        r"<dt[^>]*>\s*<strong>Type of firm</strong>\s*</dt>\s*<dd[^>]*>\s*([^<]{5,200})\s*</dd>",
        html,
        re.S | re.I,
    )
    firm_type = type_m.group(1).strip() if type_m else None

    return {
        "sra_number": sra_number,
        "name": name,
        "address": address,
        "city": city,
        "phone": phone,
        "email": email,
        "website": website,
        "legal_aid": legal_aid,
        "firm_type": firm_type,
        "sra_url": f"{SRA_BASE}/consumers/register/organisation/?sraNumber={sra_number}",
    }


async def run_scrape(delay: float = 0.3) -> list[dict]:
    """Scrape the SRA register and return filtered firm dicts."""
    import asyncio

    async with httpx.AsyncClient(headers=SRA_HEADERS, timeout=20, follow_redirects=True) as client:
        # Collect unique SRA numbers
        all_firms: dict[int, str] = {}
        for term in SEARCH_TERMS:
            try:
                results = await search_firms(client, term)
                new = sum(1 for n, _ in results if n not in all_firms)
                all_firms.update({n: name for n, name in results})
                logger.info("SRA search '%s': %d results (%d new), total=%d", term, len(results), new, len(all_firms))
            except Exception:
                logger.exception("SRA search failed for '%s'", term)
            await asyncio.sleep(delay)

        logger.info("Total unique SRA firms to fetch: %d", len(all_firms))

        # Fetch details
        firms = []
        for sra_number, name in sorted(all_firms.items()):
            if _EXCLUDE_RE.search(name):
                continue
            try:
                resp = await client.get(
                    f"{SRA_BASE}/consumers/register/organisation/",
                    params={"sraNumber": sra_number},
                )
                resp.raise_for_status()
                detail = _parse_detail(sra_number, resp.text)
                firms.append(detail)
            except Exception:
                logger.warning("Failed to fetch SRA firm %s", sra_number)
            await asyncio.sleep(delay)

    logger.info("SRA scrape complete: %d firms", len(firms))
    return firms
