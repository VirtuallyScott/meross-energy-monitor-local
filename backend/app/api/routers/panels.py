"""Electrical panels and the breakers channels sit on (PNL-001 to PNL-007)."""

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
from app.core.errors import envelope, not_found
from app.db.models import Channel, Device, Panel
from app.panels import service
from app.panels.layout import MAX_POLES, MAX_SPACES, MIN_SPACES

router = APIRouter(prefix="/panels", tags=["panels"])
Numbering = Literal["odd_even", "sequential"]


class PanelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    spaces: int = Field(ge=MIN_SPACES, le=MAX_SPACES, multiple_of=2)
    numbering: Numbering = "odd_even"


class PanelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    spaces: int | None = Field(default=None, ge=MIN_SPACES, le=MAX_SPACES, multiple_of=2)
    numbering: Numbering | None = None


class LegIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pole: int = Field(ge=1, le=MAX_POLES)
    channel_id: uuid.UUID


class BreakerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    poles: int = Field(ge=1, le=MAX_POLES)
    amps: int | None = Field(default=None, ge=1, le=400)
    legs: list[LegIn] = Field(min_length=1, max_length=MAX_POLES)


def breaker_out(channel: Channel, device: Device) -> dict[str, Any]:
    return {
        "channel_id": str(channel.id),
        "channel_name": channel.name,
        "phase_label": channel.phase_label,
        "device_id": str(device.id),
        "device_name": device.display_name or device.device_name or device.dev_id,
        "slot": channel.panel_slot,
        "poles": channel.breaker_poles or 1,
        "pole": channel.breaker_pole or 1,
        "amps": channel.breaker_amps,
    }


def panel_out(panel: Panel, breakers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": str(panel.id),
        "site_id": str(panel.site_id),
        "name": panel.name,
        "spaces": panel.spaces,
        "numbering": panel.numbering,
        "breakers": breakers or [],
    }


@router.get("")
async def list_panels(
    session: SessionDep,
    site_id: uuid.UUID | None = None,
    principal: Principal = Depends(require(P.DEVICE_READ)),
) -> dict[str, Any]:
    """Panels with the channels placed on them, ordered by creation (uuid7)."""
    stmt = select(Panel).order_by(Panel.id)
    scope = principal.sites_with(P.DEVICE_READ)
    if scope is not None:
        stmt = stmt.where(Panel.site_id.in_(scope))
    if site_id is not None:
        stmt = stmt.where(Panel.site_id == site_id)
    panels = (await session.scalars(stmt)).all()
    rows = await session.execute(
        select(Channel, Device)
        .join(Device, Device.id == Channel.device_id)
        .where(Channel.panel_id.in_([p.id for p in panels]), Device.archived_at.is_(None))
        .order_by(Channel.panel_slot, Device.id, Channel.channel_no)
    )
    by_panel: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for channel, device in rows.tuples():
        assert channel.panel_id is not None
        by_panel.setdefault(channel.panel_id, []).append(breaker_out(channel, device))
    return envelope([panel_out(p, by_panel.get(p.id)) for p in panels])


@router.post("", status_code=201)
async def create_panel(
    body: PanelIn,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    ensure_site(principal, P.DEVICE_MANAGE, body.site_id, "site")
    panel = Panel(**body.model_dump())
    session.add(panel)
    await session.flush()
    await audit.record(
        session,
        "panel.create",
        principal=principal,
        resource_type="panel",
        resource_id=panel.id,
        site_id=panel.site_id,
    )
    await session.commit()
    return envelope(panel_out(panel))


async def _load(session: SessionDep, principal: Principal, panel_id: uuid.UUID) -> Panel:
    panel = await session.get(Panel, panel_id)
    if panel is None:
        raise not_found("panel")
    ensure_site(principal, P.DEVICE_MANAGE, panel.site_id, "panel")
    return panel


@router.patch("/{panel_id}")
async def update_panel(
    panel_id: uuid.UUID,
    body: PanelPatch,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    panel = await _load(session, principal, panel_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    spaces = changes.get("spaces", panel.spaces)
    numbering = changes.get("numbering", panel.numbering)
    if (spaces, numbering) != (panel.spaces, panel.numbering):
        await service.check_reshape(session, panel, spaces, numbering)
    for key, value in changes.items():
        setattr(panel, key, value)
    await audit.record(
        session,
        "panel.update",
        principal=principal,
        resource_type="panel",
        resource_id=panel.id,
        site_id=panel.site_id,
        detail=changes,
    )
    await session.commit()
    return envelope(panel_out(panel))


@router.delete("/{panel_id}", status_code=204)
async def delete_panel(
    panel_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> None:
    """Delete the panel and clear the position of every channel on it (PNL-007)."""
    panel = await _load(session, principal, panel_id)
    for channel in await service.channels_on(session, panel.id):
        service.clear(channel)
    await session.flush()
    await session.delete(panel)
    await audit.record(
        session,
        "panel.delete",
        principal=principal,
        resource_type="panel",
        resource_id=panel.id,
        site_id=panel.site_id,
    )
    await session.commit()


@router.put("/{panel_id}/breakers/{slot}")
async def put_breaker(
    panel_id: uuid.UUID,
    slot: int,
    body: BreakerIn,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    """Place a breaker at ``slot`` with one sensor per pole (PNL-002, PNL-004).

    Sensors already on this breaker but missing from ``legs`` are removed from it.
    """
    panel = await _load(session, principal, panel_id)
    legs = [service.Leg(leg.pole, leg.channel_id) for leg in body.legs]
    await service.set_breaker(session, panel, slot, body.poles, body.amps, legs)
    await audit.record(
        session,
        "panel.breaker.set",
        principal=principal,
        resource_type="panel",
        resource_id=panel.id,
        site_id=panel.site_id,
        detail={
            "slot": slot,
            "poles": body.poles,
            "amps": body.amps,
            "legs": {str(leg.pole): str(leg.channel_id) for leg in body.legs},
        },
    )
    await session.commit()
    return envelope({"panel_id": str(panel.id), "slot": slot})


@router.delete("/{panel_id}/breakers/{slot}", status_code=204)
async def delete_breaker(
    panel_id: uuid.UUID,
    slot: int,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> None:
    panel = await _load(session, principal, panel_id)
    if not await service.clear_breaker(session, panel, slot):
        raise not_found("breaker")
    await audit.record(
        session,
        "panel.breaker.clear",
        principal=principal,
        resource_type="panel",
        resource_id=panel.id,
        site_id=panel.site_id,
        detail={"slot": slot},
    )
    await session.commit()
