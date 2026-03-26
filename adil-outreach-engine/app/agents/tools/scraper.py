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

_MAX_OUTPUT_CHARS = 4000


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
        title = title_tag.get_text(strip=True) if title_tag else "No title"

        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"]

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

        # Build output
        output = f"Title: {title}\n" f"Description: {meta_desc}\n" f"Contact: {contact_section}\n" f"Content: {text}"

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
