"""Permission catalog and built-in roles (SRD 04 §1.3, §1.4)."""

from __future__ import annotations

from enum import StrEnum


class P(StrEnum):
    SYSTEM_SETTINGS = "system:settings"
    SYSTEM_BACKUP = "system:backup"
    SYSTEM_HEALTH = "system:health"
    USER_READ = "user:read"
    USER_MANAGE = "user:manage"
    ROLE_ASSIGN = "role:assign"
    AUDIT_READ = "audit:read"
    SITE_READ = "site:read"
    SITE_MANAGE = "site:manage"
    DEVICE_READ = "device:read"
    DEVICE_MANAGE = "device:manage"
    DEVICE_CREDENTIAL = "device:credential"
    DEVICE_CONFIGURE = "device:configure"
    DEVICE_REBOOT = "device:reboot"
    DEVICE_DISCOVER = "device:discover"
    CIRCUIT_READ = "circuit:read"
    CIRCUIT_MANAGE = "circuit:manage"
    DATA_READ = "data:read"
    DATA_EXPORT = "data:export"
    TARIFF_READ = "tariff:read"
    TARIFF_MANAGE = "tariff:manage"
    TARIFF_ASSIGN = "tariff:assign"
    BILL_READ = "bill:read"
    BILL_RUN = "bill:run"
    BILL_ACTUAL = "bill:actual"
    ALERT_READ = "alert:read"
    ALERT_ACK = "alert:ack"
    ALERT_MANAGE = "alert:manage"
    TOKEN_SELF = "token:self"


GLOBAL_ONLY: frozenset[P] = frozenset(
    {
        P.SYSTEM_SETTINGS,
        P.SYSTEM_BACKUP,
        P.USER_READ,
        P.USER_MANAGE,
        P.ROLE_ASSIGN,
        P.AUDIT_READ,
        P.DEVICE_DISCOVER,
        P.TARIFF_MANAGE,
    }
)


class Role(StrEnum):
    ADMIN = "admin"
    SITE_MANAGER = "site_manager"
    ENERGY_ANALYST = "energy_analyst"
    VIEWER = "viewer"
    KIOSK = "kiosk"


_VIEWER = {
    P.SITE_READ,
    P.DEVICE_READ,
    P.CIRCUIT_READ,
    P.DATA_READ,
    P.TARIFF_READ,
    P.BILL_READ,
    P.ALERT_READ,
    P.ALERT_ACK,
    P.TOKEN_SELF,
}
_ANALYST = _VIEWER | {
    P.DATA_EXPORT,
    P.TARIFF_MANAGE,
    P.BILL_RUN,
    P.BILL_ACTUAL,
}
_SITE_MANAGER = _VIEWER | {
    P.SYSTEM_HEALTH,
    P.SITE_MANAGE,
    P.DEVICE_MANAGE,
    P.DEVICE_CREDENTIAL,
    P.DEVICE_CONFIGURE,
    P.CIRCUIT_MANAGE,
    P.DATA_EXPORT,
    P.TARIFF_ASSIGN,
    P.BILL_RUN,
    P.BILL_ACTUAL,
    P.ALERT_MANAGE,
}

ROLE_PERMISSIONS: dict[Role, frozenset[P]] = {
    Role.ADMIN: frozenset(P),
    Role.SITE_MANAGER: frozenset(_SITE_MANAGER),
    Role.ENERGY_ANALYST: frozenset(_ANALYST),
    Role.VIEWER: frozenset(_VIEWER),
    Role.KIOSK: frozenset({P.SITE_READ, P.CIRCUIT_READ, P.DATA_READ, P.BILL_READ}),
}


def role_permissions(role: Role | str, *, global_scope: bool) -> frozenset[P]:
    """Permissions a role grants at a scope. Global-only permissions drop at site scope."""
    perms = ROLE_PERMISSIONS[Role(role)]
    return perms if global_scope else perms - GLOBAL_ONLY
