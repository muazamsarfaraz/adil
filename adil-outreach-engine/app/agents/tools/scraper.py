import re

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool


# TODO: robots.txt — respect robots.txt before scraping in production
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

_STRIP_TAGS = {"nav", "footer", "script", "style", "noscript", "header", "aside"}
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+44\s?|0)(?:\d\s?){9,10}"  # UK phone numbers
    r"|(?:\+\d{1,3}\s?)?\(?\d{2,4}\)?[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}"  # international
)

_MAX_OUTPUT_CHARS = 6000


@tool
async def scrape_website(url: str) -> str:
    """Scrape a website and extract text content, contact details, and key information.

    Args:
        url: The URL to scrape.

    Returns:
        Extracted text content with contact details and key information.
    """
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)

        if response.status_code != 200:
            return f"Error: HTTP {response.status_code} when fetching {url}"

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else "No title"
        title = str(title_text) if not isinstance(title_text, str) else title_text

        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            content = meta_tag["content"]
            meta_desc = " ".join(content) if isinstance(content, list) else str(content)

        # Extract OG description as fallback (often contains specialisms)
        if not meta_desc:
            og_tag = soup.find("meta", attrs={"property": "og:description"})
            if og_tag and og_tag.get("content"):
                content = og_tag["content"]
                meta_desc = " ".join(content) if isinstance(content, list) else str(content)

        # Extract H1 and H2 headings (often list practice areas and specialisms)
        headings = []
        for tag_name in ("h1", "h2"):
            for heading in soup.find_all(tag_name):
                heading_text = heading.get_text(strip=True)
                if heading_text and len(heading_text) < 200:
                    headings.append(heading_text)

        # Extract internal links to key pages (About, Team, Services, Practice Areas)
        key_pages = []
        _KEY_PAGE_PATTERNS = re.compile(
            r"(about|team|people|solicitor|lawyer|staff|practice|service|speciali|area.*law|"
            r"expertise|sector|department|accreditation|award|testimonial)",
            re.IGNORECASE,
        )
        base_domain = re.sub(r"https?://", "", url).split("/")[0]
        for link in soup.find_all("a", href=True):
            href = link["href"]
            link_text = link.get_text(strip=True)
            # Match by link text or href path
            if _KEY_PAGE_PATTERNS.search(link_text) or _KEY_PAGE_PATTERNS.search(href):
                # Resolve relative URLs
                if href.startswith("/"):
                    href = f"https://{base_domain}{href}"
                elif not href.startswith("http"):
                    href = f"https://{base_domain}/{href}"
                # Only include links on the same domain
                if base_domain in href and href not in key_pages:
                    key_pages.append(href)

        # Strip unwanted tags
        for tag_name in _STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Extract main text content
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Ensure text is a string — BeautifulSoup can return lists in edge cases
        if isinstance(text, list):
            text = "\n".join(str(item) for item in text)
        elif not isinstance(text, str):
            text = str(text)

        # Clean up whitespace — collapse multiple blank lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)

        # Extract contact details
        emails = list(set(_EMAIL_RE.findall(text)))
        phones = list(set(_PHONE_RE.findall(text)))

        # Build contact section
        contact_parts = []
        if emails:
            contact_parts.append(f"Emails: {', '.join(emails[:5])}")
        if phones:
            contact_parts.append(f"Phones: {', '.join(phones[:5])}")
        contact_section = "; ".join(contact_parts) if contact_parts else "No contact details found"

        # Build headings section
        headings_section = ""
        if headings:
            headings_section = "Headings: " + " | ".join(headings[:15])

        # Build key pages section
        key_pages_section = ""
        if key_pages:
            key_pages_section = "Key pages found: " + ", ".join(key_pages[:8])

        # Build output
        output = (
            f"Title: {title}\n"
            f"Description: {meta_desc}\n"
            f"{headings_section + chr(10) if headings_section else ''}"
            f"Contact: {contact_section}\n"
            f"{key_pages_section + chr(10) if key_pages_section else ''}"
            f"Content: {text}"
        )

        # Truncate to stay within LLM context limits
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n... [truncated]"

        return output

    except httpx.TimeoutException:
        return f"Error: Timeout after 15 seconds when fetching {url}"
    except httpx.ConnectError:
        return f"Error: Could not connect to {url}"
    except Exception as e:
        return f"Error scraping {url}: {type(e).__name__}: {e}"
