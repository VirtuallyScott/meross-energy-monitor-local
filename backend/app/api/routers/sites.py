"""Sites (SITE-001 to SITE-004)."""

from __future__ import annotations

import uuid
from typing import Any
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.auth import audit
from app.auth.deps import SessionDep, ensure_site, require
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import ApiError, envelope, not_found
from app.db.base import utcnow
from app.db.models import Circuit, Site

router = APIRouter(prefix="/sites", tags=["sites"])


def _tz(value: str | None) -> str | None:
    if value is not None and value not in available_timezones():
        raise ValueError("unknown time zone")
    return value


class SiteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    time_zone: str = Field(max_length=64)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    address: str | None = Field(default=None, max_length=500)

    @field_validator("time_zone")
    @classmethod
    def _check_tz(cls, value: str | None) -> str | None:
        return _tz(value)


class SitePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    time_zone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    address: str | None = Field(default=None, max_length=500)
    grid_circuit_id: uuid.UUID | None = None
    solar_circuit_id: uuid.UUID | None = None
    load_circuit_id: uuid.UUID | None = None
    archived: bool | None = None

    @field_validator("time_zone")
    @classmethod
    def _check_tz(cls, value: str | None) -> str | None:
        return _tz(value)


def site_out(site: Site) -> dict[str, Any]:
    def s(v: Any) -> str | None:
        return str(v) if v else None

    return {
        "id": str(site.id),
        "name": site.name,
        "time_zone": site.time_zone,
        "currency": site.currency,
        "address": site.address,
        "grid_circuit_id": s(site.grid_circuit_id),
        "solar_circuit_id": s(site.solar_circuit_id),
        "load_circuit_id": s(site.load_circuit_id),
        "version": site.version,
        "archived": site.archived_at is not None,
    }


@router.get("")
async def list_sites(
    session: SessionDep, principal: Principal = Depends(require(P.SITE_READ))
) -> dict[str, Any]:
    stmt = select(Site).where(Site.archived_at.is_(None)).order_by(Site.name)
    scope = principal.sites_with(P.SITE_READ)
    if scope is not None:
        stmt = stmt.where(Site.id.in_(scope))
    return envelope([site_out(s) for s in await session.scalars(stmt)])


@router.post("", status_code=201)
async def create_site(
    body: SiteIn, session: SessionDep, principal: Principal = Depends(require(P.SITE_MANAGE))
) -> dict[str, Any]:
    if not principal.has(P.SITE_MANAGE):
        raise ApiError(403, "forbidden", "creating a site requires global site:manage")
    site = Site(**body.model_dump())
    session.add(site)
    await session.flush()
    await audit.record(
        session,
        "site.create",
        principal=principal,
        resource_type="site",
        resource_id=site.id,
        site_id=site.id,
    )
    await session.commit()
    return envelope(site_out(site))


async def load_site(session: SessionDep, principal: Principal, perm: P, site_id: uuid.UUID) -> Site:
    site = await session.get(Site, site_id)
    if site is None:
        raise not_found("site")
    ensure_site(principal, perm, site.id, "site")
    return site


@router.get("/{site_id}")
async def get_site(
    site_id: uuid.UUID, session: SessionDep, principal: Principal = Depends(require(P.SITE_READ))
) -> dict[str, Any]:
    return envelope(site_out(await load_site(session, principal, P.SITE_READ, site_id)))


@router.patch("/{site_id}")
async def update_site(
    site_id: uuid.UUID,
    body: SitePatch,
    session: SessionDep,
    if_match: str | None = Header(default=None),
    principal: Principal = Depends(require(P.SITE_MANAGE)),
) -> dict[str, Any]:
    site = await load_site(session, principal, P.SITE_MANAGE, site_id)
    if if_match is not None and if_match.strip('"') != str(site.version):
        raise ApiError(409, "version_conflict", "site was changed by someone else")  # API-006
    changes = body.model_dump(exclude_unset=True)
    for key in ("grid_circuit_id", "solar_circuit_id", "load_circuit_id"):
        circuit_id = changes.get(key)
        if circuit_id is not None:
            circuit = await session.get(Circuit, circuit_id)
            if circuit is None or circuit.site_id != site.id:
                raise ApiError(422, "invalid_circuit", f"{key} must be a circuit in this site")
    archived = changes.pop("archived", None)
    for key, value in changes.items():
        setattr(site, key, value)
    if archived is not None:
        site.archived_at = utcnow() if archived else None
    site.version += 1
    await audit.record(
        session,
        "site.update",
        principal=principal,
        resource_type="site",
        resource_id=site.id,
        site_id=site.id,
        detail={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return envelope(site_out(site))
