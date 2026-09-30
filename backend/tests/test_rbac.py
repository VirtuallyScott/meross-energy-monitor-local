"""TST-004: RBAC matrix (SRD 04 §1.4), scoping and token subsets."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.auth.permissions import GLOBAL_ONLY, P, Role, role_permissions
from app.auth.principal import Binding, build_principal

A, SM, EA, V, K = Role.ADMIN, Role.SITE_MANAGER, Role.ENERGY_ANALYST, Role.VIEWER, Role.KIOSK
# Expected global-scope grants, transcribed from SRD 04 §1.4.
MATRIX: dict[P, set[Role]] = {
    P.SYSTEM_SETTINGS: {A}, P.SYSTEM_BACKUP: {A}, P.SYSTEM_HEALTH: {A, SM},
    P.USER_READ: {A}, P.USER_MANAGE: {A}, P.ROLE_ASSIGN: {A}, P.AUDIT_READ: {A},
    P.SITE_READ: {A, SM, EA, V, K}, P.SITE_MANAGE: {A, SM},
    P.DEVICE_READ: {A, SM, EA, V}, P.DEVICE_MANAGE: {A, SM}, P.DEVICE_CREDENTIAL: {A, SM},
    P.DEVICE_CONFIGURE: {A, SM}, P.DEVICE_REBOOT: {A}, P.DEVICE_DISCOVER: {A},
    P.CIRCUIT_READ: {A, SM, EA, V, K}, P.CIRCUIT_MANAGE: {A, SM},
    P.DATA_READ: {A, SM, EA, V, K}, P.DATA_EXPORT: {A, SM, EA},
    P.TARIFF_READ: {A, SM, EA, V}, P.TARIFF_MANAGE: {A, EA}, P.TARIFF_ASSIGN: {A, SM},
    P.BILL_READ: {A, SM, EA, V, K}, P.BILL_RUN: {A, SM, EA}, P.BILL_ACTUAL: {A, SM, EA},
    P.ALERT_READ: {A, SM, EA, V}, P.ALERT_ACK: {A, SM, EA, V}, P.ALERT_MANAGE: {A, SM},
    P.TOKEN_SELF: {A, SM, EA, V},
}  # fmt: skip
NOW = datetime(2026, 9, 29, tzinfo=UTC)


def test_matrix_covers_every_permission():
    assert set(MATRIX) == set(P)


@pytest.mark.parametrize("perm", list(P))
@pytest.mark.parametrize("role", list(Role))
def test_role_matrix_global(role, perm):
    assert (perm in role_permissions(role, global_scope=True)) is (role in MATRIX[perm])


@pytest.mark.parametrize("role", list(Role))
def test_global_only_dropped_at_site_scope(role):
    assert not role_permissions(role, global_scope=False) & GLOBAL_ONLY


def test_site_scoped_viewer_sees_only_that_site():
    cottage, house = uuid.uuid4(), uuid.uuid4()
    p = build_principal(uuid.uuid4(), "tenant", [Binding(V, cottage)], NOW)
    assert p.has(P.DATA_READ, cottage)
    assert not p.has(P.DATA_READ, house)
    assert not p.has(P.DATA_READ)
    assert p.sites_with(P.DATA_READ) == {cottage}
    assert p.sites_with(P.DATA_EXPORT) == set()


def test_global_binding_means_all_sites():
    p = build_principal(uuid.uuid4(), "admin", [Binding(A, None)], NOW)
    assert p.sites_with(P.DEVICE_MANAGE) is None
    assert p.has(P.DEVICE_MANAGE, uuid.uuid4())


def test_analyst_tariff_manage_only_when_global():
    site = uuid.uuid4()
    scoped = build_principal(uuid.uuid4(), "a", [Binding(EA, site)], NOW)
    assert not scoped.has_anywhere(P.TARIFF_MANAGE)
    glob = build_principal(uuid.uuid4(), "a", [Binding(EA, None)], NOW)
    assert glob.has(P.TARIFF_MANAGE)


def test_rbac006_expired_binding_ignored():
    p = build_principal(uuid.uuid4(), "x", [Binding(A, None, NOW - timedelta(seconds=1))], NOW)
    assert not p.all_permissions


def test_rbac007_token_is_subset_of_owner_at_use_time():
    user = uuid.uuid4()
    p = build_principal(
        user, "v", [Binding(V, None)], NOW, token_perms=["data:read", "device:manage"]
    )
    assert p.has(P.DATA_READ)
    assert not p.has(P.DEVICE_MANAGE)  # owner never held it
    assert not p.has(P.SITE_READ)  # token did not ask for it


def test_rbac008_site_restricted_token():
    site, other = uuid.uuid4(), uuid.uuid4()
    p = build_principal(
        uuid.uuid4(),
        "a",
        [Binding(A, None)],
        NOW,
        token_perms=["data:read", "user:manage"],
        token_site=site,
    )
    assert p.has(P.DATA_READ, site)
    assert not p.has(P.DATA_READ, other)
    assert not p.has_anywhere(P.USER_MANAGE)  # global-only never survives site restriction
