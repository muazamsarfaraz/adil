"""
Solicitor directory scraper for AskAdil.

PRIMARY SOURCE (preferred): Law Society Find a Solicitor
  URL: https://solicitors.lawsociety.org.uk/
  Features: legal aid filter, practice area codes, language filter
  Status: WAF-blocked as of 2026-04 — returns 403 on all programmatic requests.
           When their WAF relaxes or API key is available, switch to LS source.
  Law Society practice area codes for Adil's scope:
    322 = Employment           72 = Civil liberties / Human rights
    319 = Discrimination       96 = Mental capacity
     49 = Crime (incl. hate)  120 = Immigration
  LS search URL pattern (for reference):
    https://solicitors.lawsociety.org.uk/search/results?Pro=1&AreaOfLaw=322&LegalAid=true&Radius=500

FALLBACK SOURCE (working): SRA Public Register
  URL: https://www.sra.org.uk/consumers/register/
  Features: text search, 277 relevant firms found across 8 practice area queries
  Attribution required: "data supplied by the Solicitors Regulation Authority"

Outputs: scripts/sra_firms.json  (ready to review and import)

Usage:
    python scripts/scrape_sra.py                           # SRA fallback (works now)
    python scripts/scrape_sra.py --source ls               # Law Society (try first)
    python scripts/scrape_sra.py --out adil-rag-api/docs/sra_firms.json
"""

import argparse
import json
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# --- Law Society (preferred, currently WAF-blocked) ---
LS_BASE = "https://solicitors.lawsociety.org.uk"
LS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": f"{LS_BASE}/",
    "X-Requested-With": "XMLHttpRequest",
}
# Practice area IDs for Adil's scope
LS_AREA_IDS = [
    ("322", "Employment"),
    ("319", "Discrimination"),
    ("72", "Civil liberties / Human rights"),
    ("96", "Mental capacity"),
    ("49", "Crime"),
]

# --- SRA Register (fallback, currently working) ---
BASE = "https://www.sra.org.uk"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/consumers/register/",
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


def _get(url: str, params: dict | None = None, timeout: int = 15, headers: dict | None = None) -> str:
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers=headers or HEADERS)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Law Society source (preferred, WAF-blocked as of 2026-04)
# ---------------------------------------------------------------------------


def search_law_society(area_id: str, area_name: str, legal_aid: bool = False) -> list[dict]:
    """Search Law Society by practice area ID. Returns parsed firms or raises HTTPError."""
    params = {
        "Pro": "1",
        "AreaOfLaw": area_id,
        "LegalAid": "true" if legal_aid else "false",
        "Postcode": "",
        "Radius": "500",
        "Type": "0",
        "UndertakingSearch": "false",
    }
    html = _get(f"{LS_BASE}/search/results", params=params, headers=LS_HEADERS)
    # Parse firm results from Law Society HTML
    # Format: <h2 class="...">FIRM NAME</h2> with data attributes
    firms = []
    sra_matches = re.findall(r'data-sra-id="(\d+)"[^>]*>|goToOrg\((\d+)\)', html)
    name_matches = re.findall(r'<h2[^>]*class="[^"]*result-title[^"]*"[^>]*>\s*([^<]+)', html)
    for i, (m1, m2) in enumerate(sra_matches):
        sra_num = int(m1 or m2)
        name = name_matches[i].strip() if i < len(name_matches) else ""
        firms.append({"sra_number": sra_num, "name": name, "source_area": area_name})
    return firms


def run_law_society_scrape(args) -> list[dict]:
    """Try Law Society source. Falls back to SRA if blocked."""
    all_firms: dict[int, dict] = {}
    ls_blocked = False

    for area_id, area_name in LS_AREA_IDS:
        for legal_aid in [False, True]:
            label = f"LS area={area_id} ({area_name})" + (" legal-aid" if legal_aid else "")
            print(f"Searching: '{label}' ...", end=" ", flush=True)
            try:
                results = search_law_society(area_id, area_name, legal_aid)
                new = sum(1 for r in results if r["sra_number"] not in all_firms)
                all_firms.update({r["sra_number"]: r for r in results})
                print(f"{len(results)} results ({new} new), total: {len(all_firms)}")
            except HTTPError as e:
                print(f"BLOCKED ({e.code}) - Law Society WAF active", file=sys.stderr)
                ls_blocked = True
                break
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
            time.sleep(args.delay)
        if ls_blocked:
            break

    if ls_blocked or not all_firms:
        print("\nLaw Society blocked. Falling back to SRA register...")
        return run_sra_scrape(args)

    return list(all_firms.values())


def search_sra(search_text: str) -> list[tuple[int, str]]:
    """Return list of (sra_number, firm_name) matching the search term."""
    html = _get(
        f"{BASE}/consumers/register/",
        params={
            "searchText": search_text,
            "searchBy": "Organisation",
            "numberOfResults": 500,
            "X-Requested-With": "XMLHttpRequest",
            "_": int(time.time() * 1000),
        },
    )
    sra_numbers = re.findall(r"goToOrgDetails\((\d+)\)", html)
    names = re.findall(r'<h2 class="h5 h2-no-border">\s*(.+?)\s*</h2>', html)

    results = []
    for i, sra_num in enumerate(sra_numbers):
        name = names[i] if i < len(names) else ""
        results.append((int(sra_num), name.strip()))
    return results


def parse_firm_detail(sra_number: int, html: str) -> dict:
    """Parse key fields from firm detail HTML."""
    import html as html_lib

    # Name
    m = re.search(r"<h1[^>]*>\s*(.+?)\s*</h1>", html, re.S)
    name = m.group(1).strip() if m else None
    name = html_lib.unescape(re.sub(r"<[^>]+>", "", name or "").strip())

    # Address and phone: .address-grey-text spans
    # First = full address, second = phone number
    grey_texts = re.findall(r'<span class="address-grey-text">([^<]+)</span>', html)
    address = grey_texts[0].strip() if len(grey_texts) > 0 else None
    # Second grey-text is phone if it looks like a number
    raw_phone = grey_texts[1].strip() if len(grey_texts) > 1 else None
    phone = raw_phone if raw_phone and re.search(r"\d{5,}", raw_phone) else None

    # Email: first mailto: link
    email_match = re.search(r'href="mailto:([^"]+)"', html, re.I)
    email = email_match.group(1).strip() if email_match else None

    # City: from <dt>Head office address</dt> -> <dd>CITY_TEXT
    city = None
    # Extract city from full address (UK format: ..., City, County, Postcode, Country)
    if address:
        parts = [p.strip() for p in address.split(",")]
        # City is 4th from end: [city, county, postcode, country]
        if len(parts) >= 4:
            city = parts[-4]
        elif len(parts) >= 2:
            city = parts[-2]  # fallback: second-to-last
        # Strip any stray numbers/postcodes
        if city and re.search(r"\d", city):
            city = None

    # Legal aid — check for "legal aid" in the firm's practice areas/info
    # Exclude script/CSS references by looking in body text sections
    legal_aid_body = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    legal_aid_body = re.sub(r"<style[^>]*>.*?</style>", "", legal_aid_body, flags=re.S | re.I)
    legal_aid = bool(re.search(r"\blegal aid\b", legal_aid_body, re.I))

    # Website — plain text in <dd> after <dt>Website</dt>
    website_match = re.search(
        r"<dt[^>]*>\s*<strong>Website</strong>\s*</dt>\s*<dd[^>]*>\s*([^\s<]{4,100})\s*</dd>", html, re.S | re.I
    )
    website = website_match.group(1).strip() if website_match else None
    if website and not website.startswith("http"):
        website = "https://" + website

    # Firm type — used for filtering non-law entities
    type_match = re.search(
        r"<dt[^>]*>\s*<strong>Type of firm</strong>\s*</dt>\s*<dd[^>]*>\s*([^<]{5,200})\s*</dd>", html, re.S | re.I
    )
    firm_type = type_match.group(1).strip() if type_match else None

    # Also known as: trading names section
    aka_match = re.search(r'class="[^"]*trading-name[^"]*"[^>]*>([^<]{3,100})', html, re.I)
    if not aka_match:
        aka_match = re.search(r"Also known as[:\s]*([A-Z][^<\n]{2,100})", html)
    also_known_as = aka_match.group(1).strip() if aka_match else None

    return {
        "sra_number": sra_number,
        "name": name,
        "also_known_as": also_known_as,
        "address": address,
        "city": city,
        "phone": phone,
        "email": email,
        "website": website,
        "legal_aid": legal_aid,
        "firm_type": firm_type,
        "sra_url": f"{BASE}/consumers/register/organisation/?sraNumber={sra_number}",
    }


def get_firm_detail(sra_number: int) -> dict | None:
    try:
        html = _get(
            f"{BASE}/consumers/register/organisation/",
            params={"sraNumber": sra_number},
        )
        return parse_firm_detail(sra_number, html)
    except Exception as e:
        print(f"  WARNING: failed to fetch {sra_number}: {e}", file=sys.stderr)
        return None


def run_sra_scrape(args) -> list[dict]:
    """Collect firm SRA numbers via SRA register text search, then fetch details."""
    all_firms: dict[int, str] = {}
    for term in SEARCH_TERMS:
        print(f"Searching SRA: '{term}' ...", end=" ", flush=True)
        try:
            results = search_sra(term)
            new = sum(1 for n, _ in results if n not in all_firms)
            all_firms.update({n: name for n, name in results})
            print(f"{len(results)} results ({new} new), total: {len(all_firms)}")
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
        time.sleep(args.delay)

    print(f"\nTotal unique firms to process: {len(all_firms)}")

    if args.no_details:
        return [{"sra_number": n, "name": name} for n, name in sorted(all_firms.items())]

    firms = []
    for i, (sra_number, name) in enumerate(sorted(all_firms.items()), 1):
        print(f"[{i}/{len(all_firms)}] {sra_number} {name[:50]}", end=" ... ", flush=True)
        detail = get_firm_detail(sra_number)
        if detail:
            firms.append(detail)
            legal = "[legal aid]" if detail["legal_aid"] else ""
            print(f"{detail.get('city', '?')} {legal}")
        else:
            print("SKIP")
        if i % 50 == 0:
            with open(args.out, "w") as f:
                json.dump(firms, f, indent=2, ensure_ascii=False)
            print(f"  [checkpoint: saved {len(firms)} firms]")
        time.sleep(args.delay)

    return firms


def main():
    parser = argparse.ArgumentParser(description="Solicitor directory scraper for AskAdil.")
    parser.add_argument("--out", default="scripts/sra_firms.json")
    parser.add_argument("--no-details", action="store_true", help="Skip detail fetch, list SRA numbers only")
    parser.add_argument("--delay", type=float, default=0.4, help="Delay between requests (s)")
    parser.add_argument(
        "--source",
        choices=["auto", "ls", "sra"],
        default="auto",
        help="Data source: 'ls' = Law Society (preferred, currently WAF-blocked), "
        "'sra' = SRA register (working fallback), "
        "'auto' = try LS first, fall back to SRA (default)",
    )
    args = parser.parse_args()

    if args.source == "ls":
        print("Source: Law Society Find a Solicitor (may be WAF-blocked)")
        firms = run_law_society_scrape(args)
    elif args.source == "sra":
        print("Source: SRA Public Register")
        firms = run_sra_scrape(args)
    else:  # auto
        print("Source: Law Society (auto, falling back to SRA if blocked)")
        firms = run_law_society_scrape(args)

    with open(args.out, "w") as f:
        json.dump(firms, f, indent=2, ensure_ascii=False)

    legal_aid_count = sum(1 for f in firms if f.get("legal_aid"))
    print(f"\nDone. {len(firms)} firms saved to {args.out}")
    print(f"Legal aid available: {legal_aid_count}")


if __name__ == "__main__":
    main()
