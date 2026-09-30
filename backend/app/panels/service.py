"""Breaker placement with one sensor per pole (PNL-002 to PNL-004, PNL-007)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import Channel, Device, Panel
from app.panels.layout import Placement, fit_error, overlap

BREAKER_FIELDS = ("panel_id", "panel_slot", "breaker_poles", "breaker_pole", "breaker_amps")


@dataclass(frozen=True)
class Leg:
    """One sensor (channel) on one pole of a breaker. Pole 1 is the top space."""

    pole: int
    channel_id: uuid.UUID


async def channels_on(session: AsyncSession, panel_id: uuid.UUID) -> Sequence[Channel]:
    rows = await session.scalars(select(Channel).where(Channel.panel_id == panel_id))
    return rows.all()


def _placement(channel: Channel) -> Placement:
    assert channel.panel_slot is not None
    return Placement(str(channel.id), channel.panel_slot, channel.breaker_poles or 1)


def _check_legs(poles: int, legs: Sequence[Leg]) -> None:
    if not legs:
        raise ApiError(422, "no_sensor", "assign a sensor to at least one pole")
    pole_nos = [leg.pole for leg in legs]
    if any(not 1 <= p <= poles for p in pole_nos):
        raise ApiError(422, "invalid_leg", f"a {poles}-pole breaker has poles 1 to {poles}")
    if len(set(pole_nos)) != len(pole_nos):
        raise ApiError(422, "invalid_leg", "each pole takes at most one sensor")
    channel_ids = [leg.channel_id for leg in legs]
    if len(set(channel_ids)) != len(channel_ids):
        raise ApiError(422, "invalid_leg", "a sensor can measure only one pole")


def plan_breaker(
    panel: Panel,
    slot: int,
    poles: int,
    legs: Sequence[Leg],
    leg_sites: Mapping[uuid.UUID, uuid.UUID],
    on_panel: Sequence[Channel],
) -> list[Channel]:
    """Validate a breaker and its legs; return channels at that breaker to clear.

    ``leg_sites`` maps each leg's channel id to its device's site. ``on_panel`` is every
    channel currently placed on ``panel``.
    """
    problem = fit_error(slot, poles, panel.spaces, panel.numbering)
    if problem:
        raise ApiError(422, "invalid_position", problem)
    _check_legs(poles, legs)
    for leg in legs:
        if leg_sites.get(leg.channel_id) != panel.site_id:
            raise ApiError(422, "invalid_member", f"sensor {leg.channel_id} is not in this site")
    leg_ids = {leg.channel_id for leg in legs}
    others = [_placement(c) for c in on_panel if c.id not in leg_ids and c.panel_slot != slot]
    clash = overlap(others, Placement("new", slot, poles), panel.numbering)
    if clash:
        raise ApiError(409, "space_taken", f"space {clash.slot} already holds a different breaker")
    return [c for c in on_panel if c.panel_slot == slot and c.id not in leg_ids]


def clear(channel: Channel) -> None:
    for field in BREAKER_FIELDS:
        setattr(channel, field, None)


async def set_breaker(
    session: AsyncSession,
    panel: Panel,
    slot: int,
    poles: int,
    amps: int | None,
    legs: Sequence[Leg],
) -> None:
    """Place a breaker and its sensors atomically (the unique pole constraint is deferred)."""
    rows = await session.execute(
        select(Channel, Device.site_id)
        .join(Device, Device.id == Channel.device_id)
        .where(Channel.id.in_([leg.channel_id for leg in legs]), Device.archived_at.is_(None))
    )
    found = {channel.id: (channel, site) for channel, site in rows.tuples()}
    leg_sites = {cid: site for cid, (_, site) in found.items()}
    for channel in plan_breaker(
        panel, slot, poles, legs, leg_sites, await channels_on(session, panel.id)
    ):
        clear(channel)
    for leg in legs:
        channel = found[leg.channel_id][0]
        channel.panel_id = panel.id
        channel.panel_slot = slot
        channel.breaker_poles = poles
        channel.breaker_pole = leg.pole
        channel.breaker_amps = amps


async def clear_breaker(session: AsyncSession, panel: Panel, slot: int) -> int:
    """Remove every sensor from the breaker starting at ``slot``; returns how many."""
    cleared = [c for c in await channels_on(session, panel.id) if c.panel_slot == slot]
    for channel in cleared:
        clear(channel)
    return len(cleared)


async def check_reshape(session: AsyncSession, panel: Panel, spaces: int, numbering: str) -> None:
    """Refuse a new size or numbering that would strand an assigned breaker (PNL-007)."""
    for channel in await channels_on(session, panel.id):
        placement = _placement(channel)
        problem = fit_error(placement.slot, placement.poles, spaces, numbering)
        if problem:
            raise ApiError(
                409, "panel_in_use", f"breaker at space {placement.slot} would not fit: {problem}"
            )
