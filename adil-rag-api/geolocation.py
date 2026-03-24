"""IP-based jurisdiction detection for the UK.

Uses ip-api.com (free, no key needed) to resolve IP -> city/region,
then maps to UK legal jurisdiction.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

# Map UK regions/countries to legal jurisdictions
_SCOTLAND_REGIONS = {"scotland"}
_NI_REGIONS = {"northern ireland"}
_WALES_REGIONS = {"wales"}
# Everything else in GB/UK -> England and Wales (which share a legal system)

_SCOTLAND_CITIES = {
    "edinburgh",
    "glasgow",
    "aberdeen",
    "dundee",
    "inverness",
    "stirling",
    "perth",
    "falkirk",
    "paisley",
    "kilmarnock",
    "ayr",
    "dunfermline",
}
_NI_CITIES = {
    "belfast",
    "derry",
    "londonderry",
    "lisburn",
    "newry",
    "bangor",
    "craigavon",
    "ballymena",
    "newtownabbey",
    "carrickfergus",
}
_WALES_CITIES = {
    "cardiff",
    "swansea",
    "newport",
    "wrexham",
    "barry",
    "neath",
    "bridgend",
    "llanelli",
    "cwmbran",
    "rhondda",
    "merthyr tydfil",
    "caerphilly",
    "aberystwyth",
    "bangor",
    "colwyn bay",
}


async def detect_jurisdiction_from_ip(ip: str) -> str | None:
    """Detect UK jurisdiction from an IP address.

    Returns one of: "England and Wales", "Scotland", "Northern Ireland", or None.
    Returns None if the IP is not in the UK or detection fails.
    """
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode,regionName,city")
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as e:
        logger.debug("IP geolocation failed for %s: %s", ip, e)
        return None

    if data.get("status") != "success":
        return None

    country = data.get("countryCode", "")
    if country not in ("GB", "UK"):
        return None  # Not in the UK

    region = (data.get("regionName") or "").lower()
    city = (data.get("city") or "").lower()

    # Check Scotland
    if region in _SCOTLAND_REGIONS or city in _SCOTLAND_CITIES:
        return "Scotland"

    # Check Northern Ireland
    if region in _NI_REGIONS or city in _NI_CITIES:
        return "Northern Ireland"

    # Check Wales — returns "England and Wales" since they share a legal jurisdiction
    if region in _WALES_REGIONS or city in _WALES_CITIES:
        return "England and Wales"

    # Default for UK: England and Wales
    return "England and Wales"


def extract_client_ip(headers: dict) -> str | None:
    """Extract the real client IP from proxy headers.

    Priority: CF-Connecting-IP -> X-Forwarded-For (first) -> X-Real-IP
    """
    # Cloudflare
    cf_ip = headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    # Standard proxy header
    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()

    # Nginx
    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return None
