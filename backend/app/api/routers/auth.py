"""Login, logout and current user (AUTH-004 to AUTH-006)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth import audit, service
from app.auth.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    PrincipalDep,
    SessionDep,
    authenticated,
    client_ip,
    public,
)
from app.core.config import get_settings
from app.core.errors import ApiError, envelope

router = APIRouter(prefix="/auth", tags=["auth"])

_WINDOW_S = 15 * 60
_MAX_FAILURES = 5
_failures: dict[str, deque[float]] = defaultdict(deque)


def _throttled(key: str) -> bool:
    """Per-replica login throttle (AUTH-004). Good enough for a single API replica."""
    now = time.monotonic()
    window = _failures[key]
    while window and now - window[0] > _WINDOW_S:
        window.popleft()
    return len(window) >= _MAX_FAILURES


def _fail(key: str) -> None:
    _failures[key].append(time.monotonic())


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


@router.post("/login", dependencies=[Depends(public)])
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> dict[str, Any]:
    ip = client_ip(request) or "unknown"
    keys = (f"ip:{ip}", f"user:{body.username.lower()}")
    if any(_throttled(k) for k in keys):
        raise ApiError(429, "too_many_attempts", "too many failed sign-ins; try again later")
    user = await service.authenticate(session, body.username, body.password)
    if user is None:
        for key in keys:
            _fail(key)
        await audit.record(
            session,
            "auth.login",
            source_ip=client_ip(request),
            outcome="failure",
            detail={"username": body.username[:64]},
        )
        await session.commit()
        raise ApiError(401, "invalid_credentials", "invalid username or password")
    new = await service.create_session(
        session, user, client_ip(request), request.headers.get("user-agent")
    )
    await audit.record(session, "auth.login", actor_user_id=user.id, source_ip=client_ip(request))
    await session.commit()

    secure = get_settings().cookie_secure
    max_age = int(new.expires_at.timestamp() - time.time())
    response.set_cookie(
        SESSION_COOKIE,
        new.raw_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        new.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )
    return envelope({"user_id": str(user.id), "csrf_token": new.csrf_token})


@router.post("/logout", status_code=204, dependencies=[Depends(authenticated)])
async def logout(request: Request, response: Response, session: SessionDep) -> Response:
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        await service.delete_session(session, raw)
        await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.post("/logout-all", status_code=204, dependencies=[Depends(authenticated)])
async def logout_all(principal: PrincipalDep, response: Response, session: SessionDep) -> Response:
    await service.delete_user_sessions(session, principal.user_id)
    await audit.record(session, "auth.logout_all", principal=principal)
    await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", dependencies=[Depends(authenticated)])
async def me(principal: PrincipalDep) -> dict[str, Any]:
    return envelope(
        {
            "user_id": str(principal.user_id),
            "username": principal.username,
            "global_permissions": sorted(p.value for p in principal.global_perms),
            "site_permissions": {
                str(site): sorted(p.value for p in perms)
                for site, perms in principal.site_perms.items()
            },
            "csrf_token": principal.session_csrf,
        }
    )
