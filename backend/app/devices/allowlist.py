"""Device RPC method allow-list (SEC-030).

Anything not listed here is rejected before it reaches the network. Destructive methods such
as ``Refoss.Factory.Reset`` and ``Em.Data.Del`` are never sent.
"""

from __future__ import annotations

from enum import StrEnum


class MethodClass(StrEnum):
    READ = "read"
    CONFIGURE = "configure"
    REBOOT = "reboot"


ALLOWED_METHODS: dict[str, MethodClass] = {
    "Refoss.DeviceInfo.Get": MethodClass.READ,
    "Refoss.Status.Get": MethodClass.READ,
    "Refoss.Config.Get": MethodClass.READ,
    "Sys.Config.Get": MethodClass.READ,
    "Em.Data.Get": MethodClass.READ,
    "Em.Chmerge.List": MethodClass.READ,
    "Cloud.Config.Get": MethodClass.READ,
    "Webhook.List": MethodClass.READ,
    "Webhook.Supported.List": MethodClass.READ,
    "Em.Config.Set": MethodClass.CONFIGURE,
    "Em.Chmerge.Create": MethodClass.CONFIGURE,
    "Em.Chmerge.Update": MethodClass.CONFIGURE,
    "Em.Chmerge.Del": MethodClass.CONFIGURE,
    "Sys.Config.Set": MethodClass.CONFIGURE,
    "Refoss.Device.Reboot": MethodClass.REBOOT,
}


class MethodNotAllowedError(PermissionError):
    pass


def check_method(method: str, params: dict[str, object] | None) -> MethodClass:
    """Return the method's class, or raise if the method is not allowed."""
    method_class = ALLOWED_METHODS.get(method)
    if method_class is None:
        raise MethodNotAllowedError(f"device method {method!r} is not on the allow-list")
    if method == "Sys.Config.Set":
        _check_sys_config_payload(params)
    return method_class


def _check_sys_config_payload(params: dict[str, object] | None) -> None:
    """Only ``{"config": {"device": {"name": ...}}}`` may be written (SEC-030)."""
    config = (params or {}).get("config")
    if not isinstance(config, dict) or set(config) != {"device"}:
        raise MethodNotAllowedError("Sys.Config.Set may only change device.name")
    device = config["device"]
    if not isinstance(device, dict) or set(device) != {"name"}:
        raise MethodNotAllowedError("Sys.Config.Set may only change device.name")
