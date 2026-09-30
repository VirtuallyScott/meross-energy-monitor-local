"""Historical readings (UI-003, API spec §2.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.auth.deps import SessionDep, require
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.errors import ApiError, envelope
from app.db.models import Site
from app.readings import query, series
from app.readings.plan import RangeError, Resolution, plan_query

router = APIRouter(prefix="/readings", tags=["readings"])
MAX_SERIES = 20


def _ids(raw: str | None) -> list[uuid.UUID]:
    if not raw:
        return []
    try:
        return [uuid.UUID(part) for part in raw.split(",") if part]
    except ValueError as exc:
        raise ApiError(422, "validation_error", "ids must be UUIDs") from exc


@router.get("")
async def readings(
    session: SessionDep,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
    circuits: str | None = None,
    channels: str | None = None,
    resolution: Resolution = Resolution.AUTO,
    principal: Principal = Depends(require(P.DATA_READ)),
) -> dict[str, Any]:
    circuit_ids, channel_ids = _ids(circuits), _ids(channels)
    if not circuit_ids and not channel_ids:
        raise ApiError(422, "validation_error", "give circuits or channels")
    if len(circuit_ids) + len(channel_ids) > MAX_SERIES:
        raise ApiError(422, "validation_error", f"at most {MAX_SERIES} series per request")
    try:
        plan = plan_query(start, end, resolution)
    except RangeError as exc:
        raise ApiError(422, "invalid_range", str(exc)) from exc
    members, meta, site_id = await series.resolve(session, principal, circuit_ids, channel_ids)
    site = await session.get(Site, site_id) if site_id else None
    tz = site.time_zone if site else "UTC"
    data = await query.run(session, plan, members, start, end, tz)
    return envelope(
        [{"series": key, **meta[key], "points": points} for key, points in data.items()],
        {"resolution": plan.resolution.value, "time_zone": tz, "source": plan.source},
    )
