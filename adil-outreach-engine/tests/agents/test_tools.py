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
        """scrape_website truncates output to 6000 chars."""
        long_text = "A" * 10000
        html = f"<html><head><title>Test</title></head><body><p>{long_text}</p></body></html>"
        respx.get("https://long.example.com/").mock(return_value=httpx.Response(200, text=html))

        result = await scrape_website.ainvoke({"url": "https://long.example.com/"})

        assert len(result) <= 6100  # 6000 + truncation message

    @respx.mock
    async def test_scrape_handles_list_text_from_bs4(self):
        """scrape_website handles BeautifulSoup returning list instead of string.

        Some malformed HTML can cause get_text() to return a list in certain
        BeautifulSoup edge cases. The scraper should coerce to string safely
        rather than raising 'expected string or bytes-like object, got list'.
        """
        html = """
        <html>
        <head><title>Edge Case Firm</title></head>
        <body>
            <p>Contact us at edge@example.com</p>
            <p>Phone: 0161 234 5678</p>
        </body>
        </html>
        """
        respx.get("https://edgecase.example.com/").mock(return_value=httpx.Response(200, text=html))

        # Patch get_text on the body element to return a list (simulating the bug)
        _original_ainvoke = scrape_website.ainvoke

        from unittest.mock import patch as _patch
        from bs4 import Tag

        _original_get_text = Tag.get_text

        call_count = 0

        def patched_get_text(self, *args, **kwargs):
            nonlocal call_count
            result = _original_get_text(self, *args, **kwargs)
            # Only patch the body's get_text call (the one with separator kwarg)
            if self.name == "body" and "separator" in kwargs:
                call_count += 1
                if call_count == 1:
                    # Return a list to simulate the bug
                    return ["Contact us at edge@example.com", "Phone: 0161 234 5678"]
            return result

        with _patch.object(Tag, "get_text", patched_get_text):
            result = await scrape_website.ainvoke({"url": "https://edgecase.example.com/"})

        # Should not raise — should return valid content
        assert "Title: Edge Case Firm" in result
        assert "Error" not in result


# ---------------------------------------------------------------------------
# search_sra_register tests
# ---------------------------------------------------------------------------


class TestSearchSraRegister:
    """Tests for the search_sra_register tool (rag-api backed)."""

    # Matches settings.rag_api_base_url default
    BASE = "https://api.askadil.org"

    @respx.mock
    async def test_sra_returns_results_by_name(self):
        """Name search returns formatted rag-api results."""
        payload = {
            "solicitors": [
                {
                    "sra_id": "123456",
                    "name": "John Smith",
                    "sra_status": "SRA Regulated",
                    "firm_name": "Smith & Partners",
                    "role": "Solicitor",
                    "address": "1 High Street, London",
                    "practice_areas": ["Family - general"],
                    "languages": ["English", "Urdu"],
                    "accreditations": [],
                }
            ],
            "total": 1,
        }
        respx.get(f"{self.BASE}/api/v1/solicitors/search").mock(return_value=httpx.Response(200, json=payload))

        result = await search_sra_register.ainvoke({"name": "John Smith", "firm": "Smith & Partners"})

        assert "SRA Number: 123456" in result
        assert "John Smith" in result
        assert "Smith & Partners" in result
        assert "Urdu" in result

    @respx.mock
    async def test_sra_verify_by_id(self):
        """Numeric input hits the /verify/{sra_id} endpoint."""
        payload = {
            "solicitor": {
                "sra_id": "830948",
                "name": "Faheem Azam Khan",
                "sra_status": "SRA Regulated",
                "firm_name": "A-Z LAW SOLICITORS LIMITED",
                "role": "Director",
                "address": "Enfield",
                "practice_areas": ["Immigration - general"],
                "languages": ["Urdu", "English"],
                "accreditations": [],
            },
            "disclaimer": "test",
        }
        respx.get(f"{self.BASE}/api/v1/solicitors/verify/830948").mock(return_value=httpx.Response(200, json=payload))

        result = await search_sra_register.ainvoke({"name": "830948"})

        assert "SRA Register record for 830948" in result
        assert "Faheem Azam Khan" in result
        assert "Immigration - general" in result

    @respx.mock
    async def test_sra_verify_not_found(self):
        """404 from /verify returns a graceful not-found message."""
        respx.get(f"{self.BASE}/api/v1/solicitors/verify/999999").mock(
            return_value=httpx.Response(404, json={"detail": "not found"})
        )

        result = await search_sra_register.ainvoke({"name": "999999"})

        assert "No SRA registration found" in result
        assert "999999" in result

    @respx.mock
    async def test_sra_no_results(self):
        """Empty search results return the not-found message."""
        respx.get(f"{self.BASE}/api/v1/solicitors/search").mock(
            return_value=httpx.Response(200, json={"solicitors": [], "total": 0})
        )

        result = await search_sra_register.ainvoke({"name": "Nonexistent Person"})

        assert "No SRA registration found" in result

    @respx.mock
    async def test_sra_api_error_returns_graceful_message(self):
        """500 from rag-api returns the graceful 'proceeding without' fallback."""
        respx.get(f"{self.BASE}/api/v1/solicitors/search").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        result = await search_sra_register.ainvoke({"name": "John Smith"})

        assert "Error" in result
        assert "Proceeding without" in result

    @respx.mock
    async def test_sra_timeout_returns_graceful_message(self):
        """Timeout returns the graceful fallback message."""
        respx.get(f"{self.BASE}/api/v1/solicitors/search").mock(side_effect=httpx.TimeoutException("timed out"))

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
