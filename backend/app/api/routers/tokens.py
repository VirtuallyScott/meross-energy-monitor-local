"""Personal API tokens (RBAC-007, RBAC-008, AUTH-010)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import audit
from app.auth import tokens as token_util
from app.auth.deps import SessionDep, require
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import ApiError, envelope, not_found
from app.db.base import utcnow
from app.db.models import ApiToken

router = APIRouter(prefix="/tokens", tags=["tokens"])
DEFAULT_DAYS = 90
MAX_DAYS = 365


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    permissions: list[P] = Field(min_length=1)
    site_id: uuid.UUID | None = None
    expires_in_days: int = Field(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS)


def _out(token: ApiToken) -> dict[str, Any]:
    return {
        "id": str(token.id),
        "name": token.name,
        "prefix": token.prefix,
        "permissions": token.permissions,
        "site_id": str(token.site_id) if token.site_id else None,
        "kind": token.kind,
        "expires_at": token.expires_at.isoformat(),
        "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
        "revoked_at": token.revoked_at.isoformat() if token.revoked_at else None,
    }


@router.get("")
async def list_tokens(
    session: SessionDep, principal: Principal = Depends(require(P.TOKEN_SELF))
) -> dict[str, Any]:
    rows = await session.scalars(
        select(ApiToken).where(ApiToken.user_id == principal.user_id).order_by(ApiToken.id)
    )
    return envelope([_out(t) for t in rows])


@router.post("", status_code=201)
async def create_token(
    body: TokenIn, session: SessionDep, principal: Principal = Depends(require(P.TOKEN_SELF))
) -> dict[str, Any]:
    if principal.token_id is not None:
        raise ApiError(403, "forbidden", "tokens cannot create tokens")
    for perm in body.permissions:
        if not principal.has(perm, body.site_id):
            raise ApiError(403, "forbidden", f"you do not hold {perm.value} in that scope")
    raw, prefix, digest = token_util.new_api_token()
    expires: datetime = utcnow() + timedelta(days=body.expires_in_days)
    token = ApiToken(
        user_id=principal.user_id,
        name=body.name,
        prefix=prefix,
        token_hash=digest,
        permissions=[p.value for p in body.permissions],
        site_id=body.site_id,
        expires_at=expires,
    )
    session.add(token)
    await session.flush()
    await audit.record(
        session,
        "token.create",
        principal=principal,
        resource_type="api_token",
        resource_id=token.id,
        detail={"permissions": token.permissions},
    )
    await session.commit()
    return envelope({**_out(token), "token": raw})


@router.delete("/{token_id}", status_code=204)
async def revoke_token(
    token_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.TOKEN_SELF)),
) -> None:
    token = await session.get(ApiToken, token_id)
    if token is None or token.user_id != principal.user_id:
        raise not_found("token")
    if token.revoked_at is None:
        token.revoked_at = utcnow()
        await audit.record(
            session,
            "token.revoke",
            principal=principal,
            resource_type="api_token",
            resource_id=token.id,
        )
        await session.commit()
