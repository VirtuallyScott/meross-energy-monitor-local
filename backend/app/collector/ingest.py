"""Write live samples, status and minute history (COL-001, COL-003, COL-004, COL-010)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import DataGap, Device, DeviceEvent
from app.db.timeseries import (
    HISTORY_KEY_MAP,
    LIVE_FIELDS,
    MINUTE_METRICS,
    QUALITY_DEVICE,
    device_status,
    energy_minute,
    live_sample,
)
from app.devices.rpc import HistoryRow

_CHANNEL_KEY = re.compile(r"^em:(\d{1,2})$")
CLOCK_SKEW_EVENT_S = 60
NOTIFY_CHANNEL = "ehub_live"


def live_rows(
    channel_ids: dict[int, uuid.UUID], params: dict[str, Any], ts: datetime
) -> list[dict[str, Any]]:
    """Map ``em:N`` objects from a status or notification to ``live_sample`` rows."""
    rows = []
    for key, value in params.items():
        match = _CHANNEL_KEY.match(key)
        if not match or not isinstance(value, dict):
            continue
        channel_id = channel_ids.get(int(match.group(1)))
        if channel_id is None:
            continue
        row: dict[str, Any] = {"channel_id": channel_id, "ts": ts}
        for src, dst in LIVE_FIELDS.items():
            raw = value.get(src)
            row[dst] = float(raw) if isinstance(raw, int | float) else None
        rows.append(row)
    return rows


def minute_rows(channel_id: uuid.UUID, rows: Sequence[HistoryRow]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        record: dict[str, Any] = {
            "channel_id": channel_id,
            "ts": datetime.fromtimestamp(row.ts, UTC),
            "quality": QUALITY_DEVICE,
        }
        for src, dst in HISTORY_KEY_MAP.items():
            raw = row.values.get(src)
            record[dst] = float(raw) if isinstance(raw, int | float) else None
        out.append(record)
    return out


async def store_live(
    session: AsyncSession, device: Device, params: dict[str, Any], *, full_status: bool
) -> int:
    """Store one snapshot. ``full_status`` means it came from ``Refoss.Status.Get``."""
    raw_ts = params.get("ts") or (params.get("sys") or {}).get("unixtime")
    ts = datetime.fromtimestamp(int(raw_ts), UTC) if raw_ts else utcnow()
    channel_ids = {c.channel_no: c.id for c in device.channels}
    rows = live_rows(channel_ids, params, ts)
    if rows:
        stmt = insert(live_sample).values(rows).on_conflict_do_nothing()
        await session.execute(stmt)
    merged = dict(device.status_json or {})
    merged.update({k: v for k, v in params.items() if k != "ts"})
    device.status_json = merged
    now = utcnow()
    # Atomic flip so concurrent loops for the same device log "online" once.
    if await _flip_online(session, device, True):
        session.add(DeviceEvent(device_id=device.id, kind="online"))
    device.last_seen_at = now
    if full_status:
        await _store_device_status(session, device, params, now)
    await session.execute(
        text("SELECT pg_notify(:ch, :payload)"), {"ch": NOTIFY_CHANNEL, "payload": str(device.id)}
    )
    return len(rows)


async def _store_device_status(
    session: AsyncSession, device: Device, status: dict[str, Any], now: datetime
) -> None:
    sys_info = status.get("sys") or {}
    wifi = status.get("wifi") or {}
    unixtime = sys_info.get("unixtime")
    skew = int(unixtime - now.timestamp()) if isinstance(unixtime, int | float) else None
    await session.execute(
        insert(device_status)
        .values(
            device_id=device.id,
            ts=now,
            online=True,
            rssi_dbm=wifi.get("rssi"),
            uptime_s=sys_info.get("uptime"),
            clock_skew_s=skew,
            cloud_connected=(status.get("cloud") or {}).get("connected"),
            mqtt_connected=(status.get("mqtt") or {}).get("connected"),
        )
        .on_conflict_do_nothing()
    )
    if skew is not None and abs(skew) > CLOCK_SKEW_EVENT_S:
        session.add(DeviceEvent(device_id=device.id, kind="clock_skew", detail={"skew_s": skew}))


async def _flip_online(session: AsyncSession, device: Device, online: bool) -> bool:
    """Set ``online`` only if it differs; True when this call made the change."""
    result = await session.execute(
        update(Device)
        .where(Device.id == device.id, Device.online.is_(not online))
        .values(online=online)
        .returning(Device.id)
        .execution_options(synchronize_session=False)
    )
    device.online = online
    return result.first() is not None


async def mark_offline(session: AsyncSession, device: Device, reason: str) -> None:
    if await _flip_online(session, device, False):
        session.add(
            DeviceEvent(device_id=device.id, kind="offline", detail={"reason": reason[:300]})
        )
        await session.execute(
            text("SELECT pg_notify(:ch, :payload)"),
            {"ch": NOTIFY_CHANNEL, "payload": str(device.id)},
        )


async def upsert_minutes(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """Idempotent upsert of minute buckets (COL-004)."""
    if not rows:
        return 0
    stmt = insert(energy_minute).values(rows)
    updates: dict[str, Any] = {name: stmt.excluded[name] for name in [*MINUTE_METRICS, "quality"]}
    updates["ingested_at"] = func.now()
    await session.execute(
        stmt.on_conflict_do_update(index_elements=["channel_id", "ts"], set_=updates)
    )
    return len(rows)


async def last_minute(session: AsyncSession, channel_id: uuid.UUID) -> datetime | None:
    value: datetime | None = await session.scalar(
        select(func.max(energy_minute.c.ts)).where(energy_minute.c.channel_id == channel_id)
    )
    return value


def record_gap(
    session: AsyncSession, channel_id: uuid.UUID, start: datetime, end: datetime, cause: str
) -> None:
    session.add(DataGap(channel_id=channel_id, start_ts=start, end_ts=end, cause=cause))
