"""Tests for agent tools: scraper, SRA register, web search."""

import os
from unittest.mock import patch

import httpx
import respx

from app.agents.tools.scraper import scrape_website
from app.agents.tools.sra import search_sra_register
from app.agents.tools.web_search import search_web


# ---------------------------------------------------------------------------
# scrape_website tests
# ---------------------------------------------------------------------------


class TestScrapeWebsite:
    """Tests for the scrape_website tool."""

    @respx.mock
    async def test_scrape_returns_extracted_content(self):
        """scrape_website extracts title, description, and content."""
        html = """
        <html>
        <head>
            <title>Smith & Co Solicitors</title>
            <meta name="description" content="Leading family law firm in Manchester">
        </head>
        <body>
            <nav>Navigation here</nav>
            <main>
                <h1>Welcome to Smith & Co</h1>
                <p>We are a leading family law firm.</p>
                <p>Contact us at info@smithco.com or call 0161 234 5678</p>
            </main>
            <footer>Footer content</footer>
        </body>
        </html>
        """
        respx.get("https://smithco.com/").mock(return_value=httpx.Response(200, text=html))

        result = await scrape_website.ainvoke({"url": "https://smithco.com/"})

        assert "Title: Smith & Co Solicitors" in result
        assert "Leading family law firm in Manchester" in result
        assert "info@smithco.com" in result
        assert "Welcome to Smith & Co" in result

    @respx.mock
    async def test_scrape_timeout_returns_error_string(self):
        """scrape_website returns error string on timeout, not exception."""
        respx.get("https://slow.example.com/").mock(side_effect=httpx.TimeoutException("timed out"))

        result = await scrape_website.ainvoke({"url": "https://slow.example.com/"})

        assert "Error" in result
        assert "Timeout" in result

    @respx.mock
    async def test_scrape_non_200_returns_error_string(self):
        """scrape_website returns error string on non-200 status."""
        respx.get("https://example.com/404").mock(return_value=httpx.Response(404, text="Not Found"))

        result = await scrape_website.ainvoke({"url": "https://example.com/404"})

        assert "Error" in result
        assert "404" in result

    @respx.mock
    async def test_scrape_connect_error_returns_error_string(self):
        """scrape_website returns error string on connection failure."""
        respx.get("https://unreachable.example.com/").mock(side_effect=httpx.ConnectError("connection refused"))

        result = await scrape_website.ainvoke({"url": "https://unreachable.example.com/"})

        assert "Error" in result
        assert "connect" in result.lower()

    @respx.mock
    async def test_scrape_truncates_long_content(self):
        """scrape_website truncates output to 4000 chars."""
        long_text = "A" * 10000
        html = f"<html><head><title>Test</title></head><body><p>{long_text}</p></body></html>"
        respx.get("https://long.example.com/").mock(return_value=httpx.Response(200, text=html))

        result = await scrape_website.ainvoke({"url": "https://long.example.com/"})

        assert len(result) <= 4100  # 4000 + truncation message


# ---------------------------------------------------------------------------
# search_sra_register tests
# ---------------------------------------------------------------------------


class TestSearchSraRegister:
    """Tests for the search_sra_register tool."""

    @respx.mock
    async def test_sra_returns_results(self):
        """search_sra_register returns parsed SRA details."""
        html = """
        <html><body>
        <div class="search-result">
            <span>John Smith - SRA ID: 123456 - Active - Smith & Partners</span>
        </div>
        </body></html>
        """
        respx.get("https://www.sra.org.uk/consumers/register/search/").mock(return_value=httpx.Response(200, text=html))

        result = await search_sra_register.ainvoke({"name": "John Smith", "firm": "Smith & Partners"})

        assert "SRA" in result
        assert "123456" in result

    @respx.mock
    async def test_sra_no_results(self):
        """search_sra_register returns not found message when no results."""
        html = "<html><body><p>No results found</p></body></html>"
        respx.get("https://www.sra.org.uk/consumers/register/search/").mock(return_value=httpx.Response(200, text=html))

        result = await search_sra_register.ainvoke({"name": "Nonexistent Person"})

        assert "No SRA registration found" in result

    @respx.mock
    async def test_sra_api_error_returns_graceful_message(self):
        """search_sra_register returns graceful error on API failure."""
        respx.get("https://www.sra.org.uk/consumers/register/search/").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        result = await search_sra_register.ainvoke({"name": "John Smith"})

        assert "Error" in result
        assert "Proceeding without" in result

    @respx.mock
    async def test_sra_timeout_returns_graceful_message(self):
        """search_sra_register returns graceful error on timeout."""
        respx.get("https://www.sra.org.uk/consumers/register/search/").mock(
            side_effect=httpx.TimeoutException("timed out")
        )

        result = await search_sra_register.ainvoke({"name": "John Smith"})

        assert "Error" in result
        assert "timed out" in result.lower() or "Proceeding without" in result


# ---------------------------------------------------------------------------
# search_web tests
# ---------------------------------------------------------------------------


class TestSearchWeb:
    """Tests for the search_web tool."""

    @respx.mock
    async def test_search_web_returns_formatted_results(self):
        """search_web returns formatted search results from Serper."""
        serper_response = {
            "organic": [
                {
                    "title": "Smith & Co wins award",
                    "snippet": "Manchester firm wins Legal 500 award",
                    "link": "https://example.com/article1",
                },
                {
                    "title": "Smith & Co profile",
                    "snippet": "Leading family law practice",
                    "link": "https://example.com/article2",
                },
            ]
        }
        respx.post("https://google.serper.dev/search").mock(return_value=httpx.Response(200, json=serper_response))

        with patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}):
            result = await search_web.ainvoke({"query": "Smith & Co Manchester"})

        assert "Smith & Co wins award" in result
        assert "Legal 500 award" in result
        assert "https://example.com/article1" in result

    async def test_search_web_no_api_key_returns_fallback(self):
        """search_web returns fallback message when SERPER_API_KEY is not set."""
        env = os.environ.copy()
        env.pop("SERPER_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            result = await search_web.ainvoke({"query": "test query"})

        assert "unavailable" in result.lower()

    @respx.mock
    async def test_search_web_api_error_returns_error_string(self):
        """search_web returns error string on API failure."""
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}):
            result = await search_web.ainvoke({"query": "test query"})

        assert "Error" in result

    @respx.mock
    async def test_search_web_timeout_returns_error_string(self):
        """search_web returns error string on timeout."""
        respx.post("https://google.serper.dev/search").mock(side_effect=httpx.TimeoutException("timed out"))

        with patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}):
            result = await search_web.ainvoke({"query": "test query"})

        assert "Error" in result
        assert "timed out" in result.lower()
