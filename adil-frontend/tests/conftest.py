"""Playwright E2E test configuration."""

import pytest


@pytest.fixture(scope="session")
def browser_context_args():
    return {"ignore_https_errors": True}
