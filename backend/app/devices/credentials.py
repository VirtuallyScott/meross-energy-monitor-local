"""Device password encryption at rest (SEC-020 to SEC-023).

Format: ``version (1 byte) || nonce (12 bytes) || AES-256-GCM ciphertext+tag``. The device row
id is the associated data so a ciphertext cannot be moved to another device.
"""

from __future__ import annotations

import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_VERSION = 1
_NONCE_LEN = 12


class CredentialError(ValueError):
    pass


def encrypt_password(key: bytes, device_id: uuid.UUID, password: str) -> bytes:
    if not password:
        raise CredentialError("password must not be empty")
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, password.encode("utf-8"), device_id.bytes)
    return bytes([KEY_VERSION]) + nonce + ciphertext


def decrypt_password(key: bytes, device_id: uuid.UUID, blob: bytes) -> str:
    if len(blob) < 1 + _NONCE_LEN + 16:
        raise CredentialError("ciphertext too short")
    if blob[0] != KEY_VERSION:
        raise CredentialError(f"unknown key version {blob[0]}")
    nonce, ciphertext = blob[1 : 1 + _NONCE_LEN], blob[1 + _NONCE_LEN :]
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, device_id.bytes)
    except Exception as exc:  # cryptography raises InvalidTag
        raise CredentialError("cannot decrypt device credential") from exc
    return plaintext.decode("utf-8")
