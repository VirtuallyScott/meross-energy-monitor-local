"""Device address validation and SSRF guard (SEC-040, SEC-041)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Sequence
from urllib.parse import urlsplit

_ALWAYS_BLOCKED = [
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("0.0.0.0/8"),
]
_PRIVATE_V4 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]
_PRIVATE_V6 = [ipaddress.ip_network("fc00::/7")]
_MAX_HOST_LEN = 253

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class AddressNotAllowedError(ValueError):
    pass


def normalize_base_url(raw: str) -> tuple[str, str, int]:
    """Turn ``host``, ``host:port`` or ``http://host[:port]`` into ``(base_url, host, port)``."""
    value = raw.strip()
    if not value:
        raise AddressNotAllowedError("address is empty")
    if "://" not in value:
        value = f"http://{value}"
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise AddressNotAllowedError("only http and https are supported")
    if parts.username or parts.password:
        raise AddressNotAllowedError("credentials in the URL are not allowed")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise AddressNotAllowedError("enter the device address without a path")
    host = parts.hostname
    if not host or len(host) > _MAX_HOST_LEN:
        raise AddressNotAllowedError("invalid host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise AddressNotAllowedError("invalid port") from exc
    host_display = f"[{host}]" if ":" in host else host
    default_port = 443 if parts.scheme == "https" else 80
    netloc = host_display if port == default_port else f"{host_display}:{port}"
    return f"{parts.scheme}://{netloc}", host, port


def is_ip_allowed(
    ip: IPAddress,
    allowed_cidrs: Sequence[str] = (),
    blocked_cidrs: Sequence[str] = (),
) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    if any(ip in net for net in _ALWAYS_BLOCKED):
        return False
    if any(ip in ipaddress.ip_network(c, strict=False) for c in blocked_cidrs):
        return False
    extra = [ipaddress.ip_network(c, strict=False) for c in allowed_cidrs]
    private = _PRIVATE_V4 if ip.version == 4 else _PRIVATE_V6
    return any(ip in net for net in [*private, *extra])


async def resolve_and_check(
    host: str,
    allowed_cidrs: Sequence[str] = (),
    blocked_cidrs: Sequence[str] = (),
) -> IPAddress:
    """Resolve ``host`` and check every resolved address. Returns the first address.

    Called at connect time so DNS rebinding cannot swap in a forbidden address (SEC-041).
    """
    try:
        literal = ipaddress.ip_address(host)
        addresses: list[IPAddress] = [literal]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise AddressNotAllowedError(f"cannot resolve {host}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses:
        raise AddressNotAllowedError(f"cannot resolve {host}")
    for address in addresses:
        if not is_ip_allowed(address, allowed_cidrs, blocked_cidrs):
            raise AddressNotAllowedError(f"{host} resolves to a disallowed address")
    return addresses[0]
