"""SEC-040 / SEC-041: device address validation."""

import ipaddress

import pytest

from app.devices.netguard import (
    AddressNotAllowedError,
    is_ip_allowed,
    normalize_base_url,
    resolve_and_check,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.168.2.75", "http://192.168.2.75"),
        ("192.168.2.75:8080", "http://192.168.2.75:8080"),
        ("http://192.168.2.75/", "http://192.168.2.75"),
        (" HTTP://em16p.lan ", "http://em16p.lan"),
        ("https://10.0.0.5:443", "https://10.0.0.5"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_base_url(raw)[0] == expected


@pytest.mark.parametrize(
    "raw", ["", "ftp://1.2.3.4", "http://u:p@10.0.0.1", "http://10.0.0.1/rpc", "http://x:99999"]
)
def test_normalize_rejects(raw):
    with pytest.raises(AddressNotAllowedError):
        normalize_base_url(raw)


@pytest.mark.parametrize(
    ("ip", "allowed"),
    [
        ("192.168.2.75", True),
        ("10.1.2.3", True),
        ("172.20.0.1", True),
        ("fd00::1", True),
        ("127.0.0.1", False),
        ("169.254.169.254", False),
        ("169.254.1.1", False),
        ("8.8.8.8", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("224.0.0.1", False),
    ],
)
def test_ip_policy(ip, allowed):
    assert is_ip_allowed(ipaddress.ip_address(ip)) is allowed


def test_extra_allowed_and_blocked_cidrs():
    public = ipaddress.ip_address("100.64.1.1")
    assert not is_ip_allowed(public)
    assert is_ip_allowed(public, allowed_cidrs=["100.64.0.0/10"])
    overlay = ipaddress.ip_address("10.231.0.7")
    assert not is_ip_allowed(overlay, blocked_cidrs=["10.231.0.0/24"])


async def test_resolve_rejects_loopback_hostname():
    with pytest.raises(AddressNotAllowedError):
        await resolve_and_check("localhost")


async def test_resolve_accepts_private_literal():
    assert str(await resolve_and_check("192.168.2.75")) == "192.168.2.75"
