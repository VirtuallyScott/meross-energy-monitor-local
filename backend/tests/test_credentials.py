"""SEC-020: device password encryption."""

import uuid

import pytest

from app.devices.credentials import CredentialError, decrypt_password, encrypt_password

KEY = b"k" * 32


def test_round_trip():
    device = uuid.uuid4()
    blob = encrypt_password(KEY, device, "s3cret")
    assert b"s3cret" not in blob
    assert decrypt_password(KEY, device, blob) == "s3cret"


def test_ciphertext_bound_to_device():
    blob = encrypt_password(KEY, uuid.uuid4(), "s3cret")
    with pytest.raises(CredentialError):
        decrypt_password(KEY, uuid.uuid4(), blob)


def test_wrong_key_and_tamper_fail():
    device = uuid.uuid4()
    blob = encrypt_password(KEY, device, "s3cret")
    with pytest.raises(CredentialError):
        decrypt_password(b"x" * 32, device, blob)
    with pytest.raises(CredentialError):
        decrypt_password(KEY, device, blob[:-1] + bytes([blob[-1] ^ 1]))


def test_empty_password_rejected():
    with pytest.raises(CredentialError):
        encrypt_password(KEY, uuid.uuid4(), "")
