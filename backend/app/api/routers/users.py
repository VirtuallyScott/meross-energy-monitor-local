"""User and role-binding management (ADM-001, RBAC-004 to RBAC-006)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.pagination import CursorQ, LimitQ, apply_cursor, page_meta
from app.auth import audit, passwords, service
from app.auth.deps import SessionDep, require
from app.auth.permissions import P, Role
from app.auth.principal import Principal
from app.core.errors import ApiError, envelope, not_found
from app.db.models import AppUser, RoleBinding, Site

router = APIRouter(prefix="/users", tags=["users"])


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=passwords.MIN_LEN, max_length=passwords.MAX_LEN)
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    password: str | None = Field(
        default=None, min_length=passwords.MIN_LEN, max_length=passwords.MAX_LEN
    )


class BindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
    site_id: uuid.UUID | None = None
    expires_at: datetime | None = None


def _user_out(user: AppUser, bindings: list[RoleBinding]) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "bindings": [
            {
                "id": str(b.id),
                "role": b.role_id,
                "site_id": str(b.site_id) if b.site_id else None,
                "expires_at": b.expires_at.isoformat() if b.expires_at else None,
            }
            for b in bindings
        ],
    }


async def _bindings(session: SessionDep, user_id: uuid.UUID) -> list[RoleBinding]:
    return list(await session.scalars(select(RoleBinding).where(RoleBinding.user_id == user_id)))


@router.get("")
async def list_users(
    session: SessionDep,
    limit: LimitQ = 50,
    cursor: CursorQ = None,
    _p: Principal = Depends(require(P.USER_READ)),
) -> dict[str, Any]:
    rows = list(await session.scalars(apply_cursor(select(AppUser), AppUser.id, cursor, limit)))
    rows, meta = page_meta(rows, limit)
    return envelope([_user_out(u, await _bindings(session, u.id)) for u in rows], meta)


@router.post("", status_code=201)
async def create_user(
    body: UserIn, session: SessionDep, principal: Principal = Depends(require(P.USER_MANAGE))
) -> dict[str, Any]:
    if await session.scalar(select(AppUser).where(AppUser.username == body.username)):
        raise ApiError(409, "conflict", "username already exists")
    try:
        password_hash = passwords.hash_password(body.password)
    except passwords.PasswordPolicyError as exc:
        raise ApiError(422, "weak_password", str(exc)) from exc
    user = AppUser(
        username=body.username,
        password_hash=password_hash,
        display_name=body.display_name,
        email=body.email,
    )
    session.add(user)
    await session.flush()
    await audit.record(
        session,
        "user.create",
        principal=principal,
        resource_type="user",
        resource_id=user.id,
        detail={"username": user.username},
    )
    await session.commit()
    return envelope(_user_out(user, []))


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    session: SessionDep,
    principal: Principal = Depends(require(P.USER_MANAGE)),
) -> dict[str, Any]:
    user = await session.get(AppUser, user_id)
    if user is None:
        raise not_found("user")
    changes: dict[str, Any] = {}
    if body.display_name is not None:
        user.display_name = body.display_name
        changes["display_name"] = body.display_name
    if body.is_active is False and user.is_active:
        await _guard_last_admin(session, user_id)
        user.is_active = False
        await service.delete_user_sessions(session, user_id)  # AUTH-006
        changes["is_active"] = False
    elif body.is_active is True:
        user.is_active = True
        changes["is_active"] = True
    if body.password is not None:
        try:
            user.password_hash = passwords.hash_password(body.password)
        except passwords.PasswordPolicyError as exc:
            raise ApiError(422, "weak_password", str(exc)) from exc
        await service.delete_user_sessions(session, user_id)
        changes["password_changed"] = True
    await audit.record(
        session,
        "user.update",
        principal=principal,
        resource_type="user",
        resource_id=user_id,
        detail=changes,
    )
    await session.commit()
    return envelope(_user_out(user, await _bindings(session, user_id)))


async def _guard_last_admin(session: SessionDep, user_id: uuid.UUID) -> None:
    """RBAC-004: never remove the last active global Admin."""
    admin_bindings = await session.scalars(
        select(RoleBinding).where(
            RoleBinding.user_id == user_id,
            RoleBinding.role_id == Role.ADMIN.value,
            RoleBinding.site_id.is_(None),
        )
    )
    if admin_bindings.first() is not None and await service.count_active_admins(session) <= 1:
        raise ApiError(409, "last_admin", "cannot remove the last active admin")


@router.post("/{user_id}/bindings", status_code=201)
async def add_binding(
    user_id: uuid.UUID,
    body: BindingIn,
    session: SessionDep,
    principal: Principal = Depends(require(P.ROLE_ASSIGN)),
) -> dict[str, Any]:
    if await session.get(AppUser, user_id) is None:
        raise not_found("user")
    if body.site_id is not None and await session.get(Site, body.site_id) is None:
        raise not_found("site")
    if body.role == Role.KIOSK:
        raise ApiError(422, "invalid_role", "kiosk is a token-only role")
    binding = RoleBinding(
        user_id=user_id,
        role_id=body.role.value,
        site_id=body.site_id,
        expires_at=body.expires_at,
        granted_by=principal.user_id,
    )
    session.add(binding)
    await session.flush()
    await audit.record(
        session,
        "binding.add",
        principal=principal,
        resource_type="user",
        resource_id=user_id,
        site_id=body.site_id,
        detail={"role": body.role.value},
    )
    await session.commit()
    return envelope({"id": str(binding.id)})


@router.delete("/{user_id}/bindings/{binding_id}", status_code=204)
async def remove_binding(
    user_id: uuid.UUID,
    binding_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.ROLE_ASSIGN)),
) -> None:
    binding = await session.get(RoleBinding, binding_id)
    if binding is None or binding.user_id != user_id:
        raise not_found("binding")
    if binding.role_id == Role.ADMIN.value and binding.site_id is None:
        await _guard_last_admin(session, user_id)
    await session.delete(binding)
    await audit.record(
        session,
        "binding.remove",
        principal=principal,
        resource_type="user",
        resource_id=user_id,
        detail={"role": binding.role_id},
    )
    await session.commit()
