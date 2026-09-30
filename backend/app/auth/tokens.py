"""Random secrets for sessions and API tokens (AUTH-005, RBAC-008)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_PREFIX = "ehub_"


def new_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_secret(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def new_api_token() -> tuple[str, str, bytes]:
    """Return ``(token, display_prefix, hash)``. Only the hash is stored."""
    token = TOKEN_PREFIX + new_secret(32)
    return token, token[: len(TOKEN_PREFIX) + 6], hash_secret(token)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
