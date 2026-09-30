"""Collector supervisor: one runner task per enabled device (COL-001, SWM-005)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import uuid
from datetime import datetime

from sqlalchemy import select

from app.collector.runner import DeviceRunner
from app.core.config import get_settings
from app.db.models import Device
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

Signature = tuple[str, datetime | None, int]


async def _desired() -> dict[uuid.UUID, Signature]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Device.id, Device.base_url, Device.credential_updated_at, Device.version).where(
                Device.enabled.is_(True), Device.archived_at.is_(None)
            )
        )
        return {r.id: (r.base_url, r.credential_updated_at, r.version) for r in rows}


async def supervise(stop: asyncio.Event) -> None:
    settings = get_settings()
    tasks: dict[uuid.UUID, tuple[asyncio.Task[None], Signature]] = {}
    while not stop.is_set():
        try:
            desired = await _desired()
        except Exception as exc:
            log.warning("cannot load devices", extra={"ctx": {"error": str(exc)}})
            desired = {k: sig for k, (_t, sig) in tasks.items()}
        for device_id, (task, sig) in list(tasks.items()):
            if device_id not in desired or desired[device_id] != sig or task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                del tasks[device_id]
        for device_id, sig in desired.items():
            if device_id not in tasks:
                runner = DeviceRunner(device_id, settings)
                tasks[device_id] = (asyncio.create_task(runner.run()), sig)
                log.info("runner started", extra={"ctx": {"device": str(device_id)}})
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.collector_refresh_s)
    for task, _sig in tasks.values():
        task.cancel()
    await asyncio.gather(*(t for t, _ in tasks.values()), return_exceptions=True)


def run() -> None:
    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await supervise(stop)

    asyncio.run(_main())
