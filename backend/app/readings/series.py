"""Resolve requested circuits and channels into signed channel members, with scope checks."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import ensure_site
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import not_found
from app.db.models import Channel, Circuit, Device
from app.readings.query import SeriesMember


async def resolve(
    session: AsyncSession,
    principal: Principal,
    circuit_ids: list[uuid.UUID],
    channel_ids: list[uuid.UUID],
) -> tuple[list[SeriesMember], dict[str, dict[str, str]], uuid.UUID | None]:
    """Return members, series metadata and the (single) site id the series belong to."""
    members: list[SeriesMember] = []
    meta: dict[str, dict[str, str]] = {}
    site_id: uuid.UUID | None = None
    for circuit_id in circuit_ids:
        circuit = await session.get(Circuit, circuit_id)
        if circuit is None or circuit.archived_at is not None:
            raise not_found("circuit")
        ensure_site(principal, P.DATA_READ, circuit.site_id, "circuit")
        site_id = site_id or circuit.site_id
        key = f"circuit:{circuit.id}"
        meta[key] = {"name": circuit.name, "kind": "circuit"}
        members += [SeriesMember(key, m.channel_id, m.sign) for m in circuit.members]
    if channel_ids:
        rows = await session.execute(
            select(Channel, Device.site_id)
            .join(Device, Device.id == Channel.device_id)
            .where(Channel.id.in_(channel_ids))
        )
        found = {ch.id: (ch, sid) for ch, sid in rows}
        for channel_id in channel_ids:
            if channel_id not in found:
                raise not_found("channel")
            channel, sid = found[channel_id]
            ensure_site(principal, P.DATA_READ, sid, "channel")
            site_id = site_id or sid
            key = f"channel:{channel.id}"
            meta[key] = {"name": channel.name, "kind": "channel"}
            members.append(SeriesMember(key, channel.id, 1))
    return members, meta, site_id
