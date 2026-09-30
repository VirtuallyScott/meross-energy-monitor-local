"""One device: live stream, periodic backfill and config sync (COL-001 to COL-015)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector import ingest
from app.core.config import Settings
from app.db.base import utcnow
from app.db.models import Device
from app.db.session import get_engine, get_sessionmaker
from app.devices import service as device_service
from app.devices.rpc import DeviceClient, DeviceRpcError, HistoryRow

log = logging.getLogger(__name__)
BACKOFF_MIN_S = 5.0
BACKOFF_MAX_S = 300.0
OFFLINE_AFTER_S = 60.0
POLL_MODE_S = 300.0
UPSERT_BATCH = 500
MINUTE = timedelta(minutes=1)


def lock_key(device_id: uuid.UUID) -> int:
    """Signed 64-bit advisory lock key derived from the device id (COL-015)."""
    return int.from_bytes(device_id.bytes[:8], "big", signed=True)


def next_backoff(current: float) -> float:
    return min(BACKOFF_MAX_S, current * 2) * random.uniform(0.8, 1.2)  # noqa: S311


@contextlib.asynccontextmanager
async def device_session(device_id: uuid.UUID) -> AsyncIterator[tuple[AsyncSession, Device]]:
    async with get_sessionmaker()() as session:
        device = await session.get(Device, device_id)
        if device is None:
            raise LookupError(f"device {device_id} disappeared")
        yield session, device
        await session.commit()


class DeviceRunner:
    def __init__(self, device_id: uuid.UUID, settings: Settings) -> None:
        self.device_id = device_id
        self.settings = settings
        self._last_ok = 0.0
        self._shared: DeviceClient | None = None

    async def run(self) -> None:
        """Hold the advisory lock for the life of the runner, then run all loops."""
        async with get_engine().connect() as lock_conn:
            got = await lock_conn.scalar(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key(self.device_id)}
            )
            await lock_conn.commit()
            if not got:
                log.info(
                    "device locked by another collector",
                    extra={"ctx": {"device": str(self.device_id)}},
                )
                await asyncio.sleep(self.settings.collector_refresh_s)
                return
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._live_loop())
                    tg.create_task(
                        self._periodic(self._backfill, self.settings.backfill_interval_s)
                    )
                    tg.create_task(self._periodic(self._sync, self.settings.config_sync_interval_s))
            finally:
                if self._shared is not None:
                    await self._shared.aclose()
                with contextlib.suppress(Exception):
                    await lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key(self.device_id)}
                    )

    async def _client(self) -> DeviceClient:
        """One client per runner, so its lock serializes all HTTP calls (COL-007).

        The supervisor restarts the runner when the address or credential changes.
        """
        if self._shared is None:
            async with get_sessionmaker()() as session:
                device = await session.get(Device, self.device_id)
                if device is None:
                    raise LookupError("device removed")
                self._shared = await device_service.client_for(device)
        return self._shared

    # ----------------------------------------------------------------- live
    async def _live_loop(self) -> None:
        backoff = BACKOFF_MIN_S
        loop = asyncio.get_running_loop()
        while True:
            try:
                client = await self._client()
                async for params in client.notifications():
                    await self._store(params, full_status=False)
                    backoff = BACKOFF_MIN_S
                raise DeviceRpcError("websocket closed")
            except Exception as exc:
                log.warning(
                    "live stream failed",
                    extra={
                        "ctx": {
                            "device": str(self.device_id),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    },
                )
            if await self._poll_mode():  # COL-002
                backoff = BACKOFF_MIN_S
                continue
            if loop.time() - self._last_ok > OFFLINE_AFTER_S:
                async with device_session(self.device_id) as (session, device):
                    await ingest.mark_offline(session, device, "no data")
            await asyncio.sleep(backoff)
            backoff = next_backoff(backoff)

    async def _poll_mode(self) -> bool:
        """Poll ``Refoss.Status.Get`` for a while; True if any poll succeeded."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + POLL_MODE_S
        succeeded = False
        while loop.time() < deadline:
            try:
                client = await self._client()
                await self._store(await client.status(), full_status=True)
                succeeded = True
            except (DeviceRpcError, ValueError, OSError):
                return succeeded
            await asyncio.sleep(self.settings.poll_fallback_s)
        return succeeded

    async def _store(self, params: dict[str, object], *, full_status: bool) -> None:
        async with device_session(self.device_id) as (session, device):
            await ingest.store_live(session, device, dict(params), full_status=full_status)
        self._last_ok = asyncio.get_running_loop().time()

    # ------------------------------------------------------------- periodic
    async def _periodic(self, job: Callable[[], Awaitable[None]], interval: float) -> None:
        while True:
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "periodic job failed",
                    extra={
                        "ctx": {
                            "device": str(self.device_id),
                            "job": getattr(job, "__name__", "?"),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    },
                )
            await asyncio.sleep(interval)

    async def _sync(self) -> None:
        client = await self._client()
        async with device_session(self.device_id) as (session, device):
            await device_service.sync_device(session, device, client)

    async def _backfill(self) -> None:
        """Fetch minute history since the last stored minute for each active channel."""
        client = await self._client()
        await self._store(await client.status(), full_status=True)
        async with get_sessionmaker()() as session:
            device = await session.get(Device, self.device_id)
            if device is None:
                raise LookupError("device removed")
            channels = [(c.id, c.channel_no) for c in device.channels if c.role != "unused"]
        newest: datetime | None = None
        for channel_id, channel_no in channels:
            last = await self._backfill_channel(client, channel_id, channel_no)
            if last is not None and (newest is None or last > newest):
                newest = last
        if newest is not None:
            async with device_session(self.device_id) as (_session, device):
                device.last_minute_ts = newest

    async def _backfill_channel(
        self, client: DeviceClient, channel_id: uuid.UUID, channel_no: int
    ) -> datetime | None:
        now = utcnow()
        async with get_sessionmaker()() as session:
            last = await ingest.last_minute(session, channel_id)
        start = (
            last + MINUTE if last else now - timedelta(hours=self.settings.initial_backfill_hours)
        )
        end = now.replace(second=0, microsecond=0)  # only complete minutes
        if end - start < MINUTE:
            return last
        batch: list[HistoryRow] = []
        first_ts: datetime | None = None
        newest = last
        async for row in client.history(
            channel_no,
            int(start.timestamp()),
            int(end.timestamp()),
            self.settings.history_page_gap_s,
        ):
            row_ts = datetime.fromtimestamp(row.ts, UTC)
            first_ts = first_ts or row_ts
            newest = row_ts
            batch.append(row)
            if len(batch) >= UPSERT_BATCH:
                await self._flush(channel_id, batch)
                batch = []
        await self._flush(channel_id, batch)
        if last is not None and first_ts is not None and first_ts - last > 2 * MINUTE:
            async with get_sessionmaker()() as session:  # COL-013
                ingest.record_gap(session, channel_id, last + MINUTE, first_ts, "missing_on_device")
                await session.commit()
        return newest

    async def _flush(self, channel_id: uuid.UUID, rows: list[HistoryRow]) -> None:
        if not rows:
            return
        async with get_sessionmaker()() as session:
            await ingest.upsert_minutes(session, ingest.minute_rows(channel_id, rows))
            await session.commit()
