"""Password hashing and policy (AUTH-001, AUTH-002)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LEN = 12
MAX_LEN = 128

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

# Small bundled list; extend with a larger file later (AUTH-002).
_COMMON = frozenset(
    {
        "password1234",
        "123456789012",
        "qwertyuiopas",
        "passwordpassword",
        "letmeinletmein",
        "iloveyou1234",
        "adminadmin12",
        "welcome12345",
        "energyenergy",
        "changeme1234",
    }
)

# A precomputed hash used to keep login timing flat when the user does not exist.
DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


class PasswordPolicyError(ValueError):
    pass


def check_policy(password: str) -> None:
    if len(password) < MIN_LEN:
        raise PasswordPolicyError(f"password must be at least {MIN_LEN} characters")
    if len(password) > MAX_LEN:
        raise PasswordPolicyError(f"password must be at most {MAX_LEN} characters")
    if password.lower() in _COMMON:
        raise PasswordPolicyError("password is too common")


def hash_password(password: str) -> str:
    check_policy(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
