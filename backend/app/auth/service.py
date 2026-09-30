"""Login, sessions and principal loading, backed by the database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import passwords, tokens
from app.auth.permissions import Role
from app.auth.principal import Binding, Principal, build_principal
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.models import ApiToken, AppUser, RoleBinding, UserSession

_TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True)
class NewSession:
    raw_id: str
    csrf_token: str
    expires_at: datetime


async def load_bindings(session: AsyncSession, user_id: uuid.UUID) -> list[Binding]:
    rows = await session.scalars(select(RoleBinding).where(RoleBinding.user_id == user_id))
    return [Binding(Role(r.role_id), r.site_id, r.expires_at) for r in rows]


async def authenticate(session: AsyncSession, username: str, password: str) -> AppUser | None:
    user = await session.scalar(select(AppUser).where(AppUser.username == username))
    if user is None:
        passwords.verify_password(passwords.DUMMY_HASH, password)  # flat timing
        return None
    if not passwords.verify_password(user.password_hash, password) or not user.is_active:
        return None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.last_login_at = utcnow()
    return user


async def create_session(
    session: AsyncSession, user: AppUser, ip: str | None, user_agent: str | None
) -> NewSession:
    settings = get_settings()
    raw_id, csrf = tokens.new_secret(32), tokens.new_secret(24)
    expires = utcnow() + timedelta(days=settings.session_absolute_days)
    session.add(
        UserSession(
            id_hash=tokens.hash_secret(raw_id),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=expires,
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return NewSession(raw_id, csrf, expires)


async def delete_session(session: AsyncSession, raw_id: str) -> None:
    await session.execute(
        delete(UserSession).where(UserSession.id_hash == tokens.hash_secret(raw_id))
    )


async def delete_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(UserSession).where(UserSession.user_id == user_id))


async def principal_from_session(session: AsyncSession, raw_id: str) -> Principal | None:
    settings = get_settings()
    now = utcnow()
    row = await session.get(UserSession, tokens.hash_secret(raw_id))
    if row is None:
        return None
    idle_limit = row.last_seen_at + timedelta(hours=settings.session_idle_hours)
    if row.expires_at <= now or idle_limit <= now:
        await session.delete(row)
        await session.commit()
        return None
    user = await session.get(AppUser, row.user_id)
    if user is None or not user.is_active:
        return None
    if now - row.last_seen_at > _TOUCH_INTERVAL:
        row.last_seen_at = now
        await session.commit()
    bindings = await load_bindings(session, user.id)
    return build_principal(user.id, user.username, bindings, now, session_csrf=row.csrf_token)


async def principal_from_token(session: AsyncSession, raw_token: str) -> Principal | None:
    now = utcnow()
    token = await session.scalar(
        select(ApiToken).where(ApiToken.token_hash == tokens.hash_secret(raw_token))
    )
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        return None
    user = await session.get(AppUser, token.user_id)
    if user is None or not user.is_active:
        return None
    if token.last_used_at is None or now - token.last_used_at > _TOUCH_INTERVAL:
        await session.execute(
            update(ApiToken).where(ApiToken.id == token.id).values(last_used_at=now)
        )
        await session.commit()
    bindings = await load_bindings(session, user.id)
    return build_principal(
        user.id,
        user.username,
        bindings,
        now,
        token_perms=token.permissions,
        token_site=token.site_id,
        token_id=token.id,
    )


async def count_users(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AppUser)) or 0)


async def count_active_admins(session: AsyncSession) -> int:
    stmt = (
        select(func.count(func.distinct(RoleBinding.user_id)))
        .join(AppUser, AppUser.id == RoleBinding.user_id)
        .where(
            RoleBinding.role_id == Role.ADMIN.value,
            RoleBinding.site_id.is_(None),
            AppUser.is_active.is_(True),
        )
    )
    return int(await session.scalar(stmt) or 0)
