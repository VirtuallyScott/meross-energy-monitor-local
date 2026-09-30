"""Live snapshot and Server-Sent Events stream (UI-002, API spec §2.2)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.livehub import hub
from app.auth.deps import SessionDep, ensure_site, require
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import envelope, not_found
from app.db.models import Circuit, Device, Site
from app.db.session import get_sessionmaker

router = APIRouter(prefix="/live", tags=["live"])
HEARTBEAT_S = 15.0


async def build_snapshot(session: AsyncSession, site_id: uuid.UUID) -> dict[str, Any]:
    """Latest per-channel values from each device's last status, plus circuit sums."""
    devices = list(
        await session.scalars(
            select(Device).where(Device.site_id == site_id, Device.archived_at.is_(None))
        )
    )
    power: dict[uuid.UUID, float] = {}
    channels: list[dict[str, Any]] = []
    for device in devices:
        status = device.status_json or {}
        for ch in device.channels:
            live = status.get(f"em:{ch.channel_no}") or {}
            watts = float(live.get("power") or 0.0)
            power[ch.id] = watts
            if ch.visible and ch.role != "unused":
                channels.append(
                    {
                        "id": str(ch.id),
                        "device_id": str(device.id),
                        "name": ch.name,
                        "role": ch.role,
                        "power_w": watts,
                        "voltage_v": live.get("voltage"),
                        "current_a": live.get("current"),
                        "pf": live.get("pf"),
                        "day_kwh": live.get("day_energy"),
                        "day_ret_kwh": live.get("day_ret_energy"),
                    }
                )
    circuits = await session.scalars(
        select(Circuit).where(Circuit.site_id == site_id, Circuit.archived_at.is_(None))
    )
    return {
        "site_id": str(site_id),
        "ts": max((d.last_seen_at for d in devices if d.last_seen_at), default=None),
        "devices": [
            {
                "id": str(d.id),
                "name": d.display_name or d.device_name or d.dev_id,
                "online": d.online,
            }
            for d in devices
        ],
        "channels": channels,
        "circuits": [
            {
                "id": str(c.id),
                "name": c.name,
                "kind": c.kind,
                "power_w": round(sum(m.sign * power.get(m.channel_id, 0.0) for m in c.members), 1),
                "channel_ids": [str(m.channel_id) for m in c.members],
            }
            for c in circuits
        ],
    }


async def _site_in_scope(session: SessionDep, principal: Principal, site_id: uuid.UUID) -> None:
    if await session.get(Site, site_id) is None:
        raise not_found("site")
    ensure_site(principal, P.DATA_READ, site_id, "site")


@router.get("/snapshot")
async def snapshot(
    site_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.DATA_READ)),
) -> dict[str, Any]:
    await _site_in_scope(session, principal, site_id)
    return envelope(await build_snapshot(session, site_id))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/stream")
async def stream(
    site_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: Principal = Depends(require(P.DATA_READ)),
) -> StreamingResponse:
    await _site_in_scope(session, principal, site_id)
    device_ids = {
        str(d) for d in await session.scalars(select(Device.id).where(Device.site_id == site_id))
    }
    await session.close()  # do not hold a pool connection for the life of the stream

    async def events() -> AsyncIterator[str]:
        queue = await hub.subscribe()
        try:
            async with get_sessionmaker()() as s:
                yield _sse("snapshot", await build_snapshot(s, site_id))
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if payload not in device_ids:
                    continue
                async with get_sessionmaker()() as s:
                    yield _sse("sample", await build_snapshot(s, site_id))
        finally:
            hub.unsubscribe(queue)

    headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
