"""The authenticated caller and its effective permissions (SRD 04 §1.1)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from app.auth.permissions import GLOBAL_ONLY, P, Role, role_permissions


@dataclass(frozen=True)
class Binding:
    role: Role
    site_id: uuid.UUID | None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    username: str
    global_perms: frozenset[P] = frozenset()
    site_perms: dict[uuid.UUID, frozenset[P]] = field(default_factory=dict)
    token_id: uuid.UUID | None = None
    session_csrf: str | None = None

    def has(self, perm: P, site_id: uuid.UUID | None = None) -> bool:
        if perm in self.global_perms:
            return True
        if site_id is None or perm in GLOBAL_ONLY:
            return False
        return perm in self.site_perms.get(site_id, frozenset())

    def sites_with(self, perm: P) -> set[uuid.UUID] | None:
        """Site ids where ``perm`` holds, or ``None`` meaning every site (RBAC-003)."""
        if perm in self.global_perms:
            return None
        return {site for site, perms in self.site_perms.items() if perm in perms}

    def has_anywhere(self, perm: P) -> bool:
        scope = self.sites_with(perm)
        return scope is None or bool(scope)

    @property
    def all_permissions(self) -> frozenset[P]:
        merged: set[P] = set(self.global_perms)
        for perms in self.site_perms.values():
            merged |= perms
        return frozenset(merged)


def build_principal(
    user_id: uuid.UUID,
    username: str,
    bindings: Iterable[Binding],
    now: datetime,
    *,
    token_perms: Iterable[str] | None = None,
    token_site: uuid.UUID | None = None,
    token_id: uuid.UUID | None = None,
    session_csrf: str | None = None,
) -> Principal:
    """Union all live bindings, then narrow to the token's permissions if a token is used.

    The token subset is applied at use time, so a user losing a permission also removes it
    from their tokens (RBAC-007). A site-restricted token keeps only that site (RBAC-008).
    """
    global_perms: set[P] = set()
    site_perms: dict[uuid.UUID, set[P]] = {}
    for binding in bindings:
        if binding.expires_at is not None and binding.expires_at <= now:
            continue
        if binding.site_id is None:
            global_perms |= role_permissions(binding.role, global_scope=True)
        else:
            site_perms.setdefault(binding.site_id, set()).update(
                role_permissions(binding.role, global_scope=False)
            )
    if token_perms is not None:
        allowed = {P(p) for p in token_perms if p in P._value2member_map_}
        if token_site is not None:
            site_scoped = (global_perms - GLOBAL_ONLY) | site_perms.get(token_site, set())
            site_perms = {token_site: site_scoped & allowed}
            global_perms = set()
        else:
            global_perms &= allowed
            site_perms = {site: perms & allowed for site, perms in site_perms.items()}
    return Principal(
        user_id=user_id,
        username=username,
        global_perms=frozenset(global_perms),
        site_perms={site: frozenset(perms) for site, perms in site_perms.items() if perms},
        token_id=token_id,
        session_csrf=session_csrf,
    )
