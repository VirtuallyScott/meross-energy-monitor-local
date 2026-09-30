"""FastAPI dependencies for authentication and authorization (RBAC-001, RBAC-002, AUTH-008)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service, tokens
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import ApiError, not_found
from app.db.session import get_session

SESSION_COOKIE = "ehub_session"
CSRF_COOKIE = "ehub_csrf"
CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_principal(request: Request, session: SessionDep) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        principal = await service.principal_from_token(session, auth[7:].strip())
        if principal is None:
            raise ApiError(401, "unauthenticated", "invalid or expired token")
        return principal
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise ApiError(401, "unauthenticated", "sign in required")
    principal = await service.principal_from_session(session, raw)
    if principal is None:
        raise ApiError(401, "unauthenticated", "session expired")
    if request.method not in _SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not principal.session_csrf or not tokens.constant_time_equals(
            header, principal.session_csrf
        ):
            raise ApiError(403, "csrf_failed", "missing or invalid CSRF token")
    return principal


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require(perm: P) -> Callable[..., Awaitable[Principal]]:
    """Dependency that requires ``perm`` in at least one scope.

    Handlers then call :func:`ensure_site` or filter with ``principal.sites_with(perm)`` for
    the specific resource (RBAC-003).
    """

    async def dependency(principal: PrincipalDep) -> Principal:
        if not principal.has_anywhere(perm):
            raise ApiError(403, "forbidden", f"requires {perm.value}")
        return principal

    dependency.required_permission = perm  # type: ignore[attr-defined]
    return dependency


async def public() -> None:
    """Marker dependency for routes that need no authentication."""


public.is_public = True  # type: ignore[attr-defined]


async def authenticated(principal: PrincipalDep) -> Principal:
    """Any signed-in caller; used for self-service routes such as ``/auth/me``."""
    return principal


authenticated.is_authenticated_only = True  # type: ignore[attr-defined]


def ensure_site(principal: Principal, perm: P, site_id: uuid.UUID, what: str = "resource") -> None:
    """404 when the resource's site is out of scope, to avoid revealing it (RBAC-003)."""
    if not principal.has(perm, site_id):
        raise not_found(what)


def client_ip(request: Request) -> str | None:
    """Client IP as seen by the app. Traefik sets X-Forwarded-For; uvicorn trusts the proxy."""
    return request.client.host if request.client else None
