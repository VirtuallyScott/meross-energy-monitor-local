"""Device merges and virtual circuits (CIR-003 to CIR-008)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import audit
from app.auth.deps import SessionDep, ensure_site, require
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import ApiError, envelope, not_found
from app.db.base import utcnow
from app.db.models import Channel, Circuit, CircuitMember, Device

router = APIRouter(prefix="/circuits", tags=["circuits"])
MAX_MEMBERS = 64


class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_id: uuid.UUID
    sign: Literal[1, -1] = 1


class CircuitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    members: list[MemberIn] = Field(min_length=1, max_length=MAX_MEMBERS)
    tags: list[str] = Field(default_factory=list, max_length=20)


class CircuitPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    members: list[MemberIn] | None = Field(default=None, min_length=1, max_length=MAX_MEMBERS)
    tags: list[str] | None = Field(default=None, max_length=20)


def circuit_out(c: Circuit) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "site_id": str(c.site_id),
        "name": c.name,
        "kind": c.kind,
        "device_id": str(c.device_id) if c.device_id else None,
        "device_merge_mask": c.device_merge_mask,
        "tags": c.tags or [],
        "members": [{"channel_id": str(m.channel_id), "sign": m.sign} for m in c.members],
        "version": c.version,
    }


async def _validate_members(
    session: SessionDep, site_id: uuid.UUID, members: list[MemberIn]
) -> list[CircuitMember]:
    """Members must be distinct channels on devices in the same site (CIR-004)."""
    ids = [m.channel_id for m in members]
    if len(set(ids)) != len(ids):
        raise ApiError(422, "duplicate_member", "a channel may appear only once")
    rows = await session.execute(
        select(Channel.id, Device.site_id)
        .join(Device, Device.id == Channel.device_id)
        .where(Channel.id.in_(ids))
    )
    found = {row.id: row.site_id for row in rows}
    for channel_id in ids:
        if found.get(channel_id) != site_id:
            raise ApiError(422, "invalid_member", f"channel {channel_id} is not in this site")
    return [CircuitMember(channel_id=m.channel_id, sign=m.sign) for m in members]


@router.get("")
async def list_circuits(
    session: SessionDep,
    site_id: uuid.UUID | None = None,
    principal: Principal = Depends(require(P.CIRCUIT_READ)),
) -> dict[str, Any]:
    stmt = select(Circuit).where(Circuit.archived_at.is_(None)).order_by(Circuit.name)
    scope = principal.sites_with(P.CIRCUIT_READ)
    if scope is not None:
        stmt = stmt.where(Circuit.site_id.in_(scope))
    if site_id is not None:
        stmt = stmt.where(Circuit.site_id == site_id)
    return envelope([circuit_out(c) for c in await session.scalars(stmt)])


@router.post("", status_code=201)
async def create_circuit(
    body: CircuitIn,
    session: SessionDep,
    principal: Principal = Depends(require(P.CIRCUIT_MANAGE)),
) -> dict[str, Any]:
    ensure_site(principal, P.CIRCUIT_MANAGE, body.site_id, "site")
    members = await _validate_members(session, body.site_id, body.members)
    circuit = Circuit(
        site_id=body.site_id, name=body.name, kind="virtual", tags=body.tags, members=members
    )
    session.add(circuit)
    await session.flush()
    await audit.record(
        session,
        "circuit.create",
        principal=principal,
        resource_type="circuit",
        resource_id=circuit.id,
        site_id=circuit.site_id,
    )
    await session.commit()
    return envelope(circuit_out(circuit))


async def _load(
    session: SessionDep, principal: Principal, perm: P, circuit_id: uuid.UUID
) -> Circuit:
    circuit = await session.get(Circuit, circuit_id)
    if circuit is None or circuit.archived_at is not None:
        raise not_found("circuit")
    ensure_site(principal, perm, circuit.site_id, "circuit")
    return circuit


@router.patch("/{circuit_id}")
async def update_circuit(
    circuit_id: uuid.UUID,
    body: CircuitPatch,
    session: SessionDep,
    principal: Principal = Depends(require(P.CIRCUIT_MANAGE)),
) -> dict[str, Any]:
    circuit = await _load(session, principal, P.CIRCUIT_MANAGE, circuit_id)
    if body.members is not None:
        if circuit.kind == "device_merge":
            raise ApiError(409, "device_merge", "edit device merges on the device")
        circuit.members = await _validate_members(session, circuit.site_id, body.members)
    if body.name is not None:
        circuit.name = body.name
    if body.tags is not None:
        circuit.tags = body.tags
    circuit.version += 1
    await audit.record(
        session,
        "circuit.update",
        principal=principal,
        resource_type="circuit",
        resource_id=circuit.id,
        site_id=circuit.site_id,
    )
    await session.commit()
    return envelope(circuit_out(circuit))


@router.delete("/{circuit_id}", status_code=204)
async def delete_circuit(
    circuit_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.CIRCUIT_MANAGE)),
) -> None:
    circuit = await _load(session, principal, P.CIRCUIT_MANAGE, circuit_id)
    if circuit.kind == "device_merge":
        raise ApiError(409, "device_merge", "delete device merges on the device")
    circuit.archived_at = utcnow()
    await audit.record(
        session,
        "circuit.delete",
        principal=principal,
        resource_type="circuit",
        resource_id=circuit.id,
        site_id=circuit.site_id,
    )
    await session.commit()
