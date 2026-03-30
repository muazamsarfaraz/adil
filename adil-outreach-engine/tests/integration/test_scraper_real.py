"""
Real website scraping tests — no mocks.

These verify the scraper tool works against actual websites.
Requires network access.
"""

from __future__ import annotations

import pytest

from app.agents.tools.scraper import scrape_website
from app.agents.tools.sra import search_sra_register

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Scraper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(30)
async def test_scrape_iwill_solicitors():
    """Scrape I Will Solicitors and verify content."""
    result = await scrape_website.ainvoke({"url": "https://www.iwillsolicitors.com"})

    assert isinstance(result, str)
    assert len(result) > 100, "Scraped content is too short"
    assert not result.startswith("Error"), f"Scraper returned error: {result}"

    # Should contain relevant content
    content_lower = result.lower()
    assert (
        "islamic" in content_lower or "will" in content_lower or "solicitor" in content_lower
    ), "Expected to find 'Islamic', 'Will', or 'Solicitor' in scraped content"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(30)
async def test_scrape_aramas():
    """Scrape Aramas Family Law and verify content."""
    result = await scrape_website.ainvoke({"url": "https://www.aramaslaw.com"})

    assert isinstance(result, str)
    assert len(result) > 100, "Scraped content is too short"
    assert not result.startswith("Error"), f"Scraper returned error: {result}"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(30)
async def test_scrape_nonexistent():
    """Scrape a domain that doesn't exist, verify graceful error."""
    result = await scrape_website.ainvoke({"url": "https://thisdomaindoesnotexist12345.com"})

    assert isinstance(result, str)
    # Should return an error message, not crash
    assert (
        "error" in result.lower() or "could not connect" in result.lower() or "timeout" in result.lower()
    ), f"Expected an error message for nonexistent domain, got: {result[:200]}"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(30)
async def test_scrape_large_page():
    """Scrape a large page and verify content is truncated properly."""
    # Wikipedia pages are reliably large
    result = await scrape_website.ainvoke({"url": "https://en.wikipedia.org/wiki/Solicitor"})

    assert isinstance(result, str)

    # The scraper truncates at _MAX_OUTPUT_CHARS (4000)
    # With the truncation marker, the result should be around 4000 chars
    if len(result) > 4000:
        assert "[truncated]" in result, "Large page should be truncated with marker"


# ---------------------------------------------------------------------------
# SRA register lookup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(30)
async def test_sra_register_lookup():
    """Search SRA for I Will Solicitors, verify returns result or graceful fallback."""
    result = await search_sra_register.ainvoke(
        {
            "name": "I Will Solicitors",
            "firm": "I Will Solicitors",
        }
    )

    assert isinstance(result, str)
    assert len(result) > 10, "SRA result is too short"

    # The SRA site may or may not return results, but should not crash
    # Accept either actual results or a graceful "not found" / error message
    is_valid = (
        "SRA" in result
        or "not found" in result.lower()
        or "no sra registration" in result.lower()
        or "error" in result.lower()
        or "register" in result.lower()
    )
    assert is_valid, f"Unexpected SRA response: {result[:300]}"
