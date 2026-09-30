"""Audit log writer (AUD-001 to AUD-003)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.db.models import AuditLog

_SECRET_KEYS = {"password", "token", "secret", "credential", "password_hash"}


def _redact(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if detail is None:
        return None
    return {k: ("[redacted]" if k in _SECRET_KEYS else v) for k, v in detail.items()}


async def record(
    session: AsyncSession,
    action: str,
    *,
    principal: Principal | None = None,
    source_ip: str | None = None,
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    """Add an audit row to the session. The caller commits with its own transaction."""
    session.add(
        AuditLog(
            actor_user_id=principal.user_id if principal else actor_user_id,
            actor_token_id=principal.token_id if principal else None,
            source_ip=source_ip,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            site_id=site_id,
            outcome=outcome,
            detail=_redact(detail),
        )
    )
