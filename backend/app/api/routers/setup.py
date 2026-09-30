"""First-run setup (AUTH-003)."""

from __future__ import annotations

from typing import Any
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import audit, passwords, service, tokens
from app.auth.deps import SessionDep, client_ip, public
from app.auth.permissions import Role
from app.core.errors import ApiError, envelope
from app.db.models import AppUser, RoleBinding, Site

router = APIRouter(prefix="/setup", dependencies=[Depends(public)], tags=["setup"])


class SetupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    setup_token: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=passwords.MIN_LEN, max_length=passwords.MAX_LEN)
    site_name: str = Field(default="Home", min_length=1, max_length=120)
    time_zone: str = Field(default="UTC", max_length=64)

    @field_validator("time_zone")
    @classmethod
    def _tz(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("unknown time zone")
        return value


@router.get("/status")
async def status(session: SessionDep) -> dict[str, Any]:
    return envelope({"needs_setup": await service.count_users(session) == 0})


@router.post("", status_code=201)
async def run_setup(body: SetupIn, request: Request, session: SessionDep) -> dict[str, Any]:
    if await service.count_users(session) > 0:
        raise ApiError(409, "already_set_up", "setup has already been completed")
    expected = getattr(request.app.state, "setup_token", None)
    if not expected or not tokens.constant_time_equals(body.setup_token, expected):
        raise ApiError(403, "bad_setup_token", "invalid setup token")
    try:
        password_hash = passwords.hash_password(body.password)
    except passwords.PasswordPolicyError as exc:
        raise ApiError(422, "weak_password", str(exc)) from exc

    user = AppUser(username=body.username, password_hash=password_hash)
    site = Site(name=body.site_name, time_zone=body.time_zone)
    session.add_all([user, site])
    await session.flush()
    session.add(RoleBinding(user_id=user.id, role_id=Role.ADMIN.value, site_id=None))
    await audit.record(
        session,
        "setup.completed",
        actor_user_id=user.id,
        source_ip=client_ip(request),
        resource_type="user",
        resource_id=user.id,
    )
    await session.commit()
    request.app.state.setup_token = None
    return envelope({"user_id": str(user.id), "site_id": str(site.id)})
