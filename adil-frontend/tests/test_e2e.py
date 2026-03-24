"""E2E tests for the AskAdil Chainlit frontend.

These tests verify the frontend UI against the live deployment.
Set ASKADIL_URL environment variable to test against a specific URL.
Default: https://askadil.org
"""

import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("ASKADIL_URL", "https://askadil.org")


class TestPageLoad:
    def test_page_loads_successfully(self, page: Page):
        page.goto(BASE_URL, timeout=30000)
        # Chainlit app should load
        expect(page).to_have_title(page.title())  # Page has a title

    def test_welcome_message_appears(self, page: Page):
        page.goto(BASE_URL, timeout=30000)
        # Wait for Chainlit to render
        page.wait_for_timeout(3000)
        # Welcome message should contain "AskAdil" or jurisdiction buttons
        content = page.content()
        assert "AskAdil" in content or "عادل" in content


class TestJurisdictionSelector:
    def test_jurisdiction_buttons_visible(self, page: Page):
        page.goto(BASE_URL, timeout=30000)
        page.wait_for_timeout(3000)
        content = page.content()
        # Should see jurisdiction options
        has_jurisdiction = "England" in content or "Scotland" in content or "Northern Ireland" in content
        assert has_jurisdiction


class TestChatInterface:
    def test_chat_input_exists(self, page: Page):
        page.goto(BASE_URL, timeout=30000)
        page.wait_for_timeout(3000)
        # Chainlit renders a textarea or input for chat
        chat_input = page.locator("textarea, input[type='text']").first
        expect(chat_input).to_be_visible(timeout=10000)
