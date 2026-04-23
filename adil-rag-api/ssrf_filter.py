"""Block outbound fetches to private/internal IP ranges (SSRF protection)."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BLOCKED_CIDRS: list[ipaddress._BaseNetwork] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_blocked(ip: str) -> bool:
    """Return True if the IP is in any blocked range. Unparseable IPs are blocked."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        logger.warning("Unparseable IP treated as blocked: %r", ip)
        return True
    return any(addr in cidr for cidr in BLOCKED_CIDRS)


async def resolve_and_check(url: str) -> None:
    """Resolve the URL's hostname and raise if any answer is blocked."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no host: {url!r}")

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {host!r}: {exc}") from exc

    for _family, _type, _proto, _canon, sockaddr in addrinfo:
        ip = sockaddr[0]
        if is_blocked(ip):
            raise ValueError(f"URL resolves to blocked IP {ip} ({host})")
