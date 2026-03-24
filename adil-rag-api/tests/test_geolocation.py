"""Tests for IP-based jurisdiction detection."""

import pytest
from geolocation import detect_jurisdiction_from_ip, extract_client_ip


class TestExtractClientIP:
    def test_cf_connecting_ip(self):
        headers = {"cf-connecting-ip": "1.2.3.4"}
        assert extract_client_ip(headers) == "1.2.3.4"

    def test_x_forwarded_for_single(self):
        headers = {"x-forwarded-for": "5.6.7.8"}
        assert extract_client_ip(headers) == "5.6.7.8"

    def test_x_forwarded_for_multiple(self):
        headers = {"x-forwarded-for": "1.1.1.1, 2.2.2.2, 3.3.3.3"}
        assert extract_client_ip(headers) == "1.1.1.1"

    def test_x_real_ip(self):
        headers = {"x-real-ip": "9.9.9.9"}
        assert extract_client_ip(headers) == "9.9.9.9"

    def test_cf_takes_priority(self):
        headers = {"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"}
        assert extract_client_ip(headers) == "1.1.1.1"

    def test_empty_headers(self):
        assert extract_client_ip({}) is None

    def test_strips_whitespace(self):
        headers = {"x-forwarded-for": " 1.2.3.4 , 5.6.7.8"}
        assert extract_client_ip(headers) == "1.2.3.4"


class TestDetectJurisdiction:
    @pytest.mark.asyncio
    async def test_localhost_returns_none(self):
        result = await detect_jurisdiction_from_ip("127.0.0.1")
        assert result is None

    @pytest.mark.asyncio
    async def test_ipv6_localhost_returns_none(self):
        result = await detect_jurisdiction_from_ip("::1")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_ip_returns_none(self):
        result = await detect_jurisdiction_from_ip("")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_ip_returns_none(self):
        result = await detect_jurisdiction_from_ip(None)
        assert result is None
