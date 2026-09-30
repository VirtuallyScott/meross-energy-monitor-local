import time
import uuid

import pytest

from app.auth import passwords
from app.db.base import uuid7


def test_uuid7_version_and_order():
    a = uuid7()
    time.sleep(0.002)
    b = uuid7()
    assert a.version == 7 and b.version == 7
    assert a.variant == uuid.RFC_4122
    assert a < b


def test_password_policy():
    with pytest.raises(passwords.PasswordPolicyError):
        passwords.hash_password("short")
    with pytest.raises(passwords.PasswordPolicyError):
        passwords.hash_password("password1234")
    h = passwords.hash_password("correct horse battery")
    assert passwords.verify_password(h, "correct horse battery")
    assert not passwords.verify_password(h, "wrong horse battery")
    assert not passwords.verify_password("not-a-hash", "x")


def test_channel_name_fallbacks():
    from app.db.models import Channel

    assert Channel(channel_no=3, device_label="em_channel_3", phase_label="A3").name == "A3"
    assert Channel(channel_no=2, device_label="Pool", phase_label="A2").name == "Pool"
    assert Channel(channel_no=2, device_label="Pool", display_name="Spa").name == "Spa"
    assert Channel(channel_no=9).name == "Channel 9"
