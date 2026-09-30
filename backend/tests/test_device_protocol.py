"""TST-002: device protocol helpers."""

import hashlib
import json

import pytest

from app.devices import digest
from app.devices.allowlist import MethodClass, MethodNotAllowedError, check_method
from app.devices.bitmask import channels_to_mask, mask_to_channels


@pytest.mark.parametrize(
    ("mask", "channels"),
    [(130, [2, 8]), (1040, [5, 11]), (2080, [6, 12]), (260, [3, 9]), (520, [4, 10]), (0, [])],
)
def test_bitmask_round_trip_matches_spec(mask, channels):
    assert mask_to_channels(mask) == channels
    assert channels_to_mask(channels) == mask


def test_bitmask_rejects_bad_input():
    with pytest.raises(ValueError):
        mask_to_channels(-1)
    with pytest.raises(ValueError):
        channels_to_mask([0])


def test_digest_matches_ui_formula():
    auth = digest.build_auth("meross-em16p-x", "pw", 123, 1, cnonce="abc")
    sha = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731
    ha1 = sha("admin:meross-em16p-x:pw")
    ha2 = sha("dummy_method:dummy_uri")
    assert auth["response"] == sha(f"{ha1}:123:1:abc:auth:{ha2}")
    assert auth["username"] == "admin"
    assert auth["realm"] == "meross-em16p-x"
    assert auth["algorithm"] == "SHA-256"


def test_parse_challenge_reads_json_string_message():
    nonce, nc, realm = digest.parse_challenge(
        {"code": 401, "message": json.dumps({"nonce": 99, "nc": 2, "realm": "r"})}
    )
    assert (nonce, nc, realm) == (99, 2, "r")
    with pytest.raises(ValueError):
        digest.parse_challenge({"code": 401, "message": "{}"})


@pytest.mark.parametrize(
    "method",
    [
        "Refoss.Factory.Reset",
        "Em.Data.Del",
        "Refoss.Upgrade",
        "WiFi.Config.Set",
        "Cloud.Config.Set",
        "Refoss.Auth.Set",
        "Nope.Get",
    ],
)
def test_sec030_denied_methods_never_allowed(method):
    with pytest.raises(MethodNotAllowedError):
        check_method(method, None)


def test_sec030_read_and_write_classes():
    assert check_method("Refoss.Status.Get", None) is MethodClass.READ
    assert check_method("Em.Config.Set", {"config": []}) is MethodClass.CONFIGURE
    assert check_method("Refoss.Device.Reboot", None) is MethodClass.REBOOT


def test_sec030_sys_config_set_only_device_name():
    ok = {"config": {"device": {"name": "x"}}}
    assert check_method("Sys.Config.Set", ok) is MethodClass.CONFIGURE
    for bad in ({"config": {"device": {"name": "x", "mac": "y"}}}, {"config": {"time": {}}}, None):
        with pytest.raises(MethodNotAllowedError):
            check_method("Sys.Config.Set", bad)
