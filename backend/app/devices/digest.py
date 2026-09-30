"""SHA-256 digest auth for the device RPC frame (API spec §2).

Derived from the device web UI code. Marked UNVERIFIED-API until tested on a device with
auth enabled.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

USERNAME = "admin"
_HA2_INPUT = "dummy_method:dummy_uri"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_auth(
    dev_id: str, password: str, nonce: int | str, nc: int, cnonce: str | None = None
) -> dict[str, Any]:
    """Build the ``auth`` object added to an RPC frame."""
    cnonce = cnonce or secrets.token_hex(8)
    ha1 = _sha256_hex(f"{USERNAME}:{dev_id}:{password}")
    ha2 = _sha256_hex(_HA2_INPUT)
    response = _sha256_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}")
    return {
        "username": USERNAME,
        "realm": dev_id,
        "nonce": nonce,
        "cnonce": cnonce,
        "response": response,
        "algorithm": "SHA-256",
        "nc": nc,
    }


def parse_challenge(error: dict[str, Any]) -> tuple[int | str, int, str | None]:
    """Parse a 401 error whose ``message`` is a JSON string with ``nonce`` and ``nc``.

    Returns ``(nonce, nc, realm)``. Raises ``ValueError`` if the challenge is malformed.
    """
    raw = error.get("message")
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict) or "nonce" not in data:
        raise ValueError("401 challenge without nonce")
    return data["nonce"], int(data.get("nc", 1)), data.get("realm")
