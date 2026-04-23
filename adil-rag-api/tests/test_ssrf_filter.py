import pytest
from ssrf_filter import is_blocked


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.255.255.255",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "169.254.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_blocked_ips_are_rejected(ip):
    assert is_blocked(ip) is True


@pytest.mark.parametrize(
    "ip",
    [
        "1.1.1.1",
        "8.8.8.8",
        "93.184.216.34",
        "2606:4700:4700::1111",
    ],
)
def test_public_ips_are_allowed(ip):
    assert is_blocked(ip) is False


def test_invalid_ip_is_blocked_conservatively():
    assert is_blocked("not-an-ip") is True
