"""Background worker: job queue plus housekeeping (SRD 02 worker, RBAC-006).

Job handlers for exports and bill runs land here in later phases. The queue uses
``FOR UPDATE SKIP LOCKED`` so several workers can run safely.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, text

from app.db.base import utcnow
from app.db.models import Job, RoleBinding, UserSession
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)
POLL_S = 2.0
HOUSEKEEPING_S = 3600.0
RETRY_DELAY = timedelta(minutes=1)

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


@handler("noop")
async def _noop(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": payload}


async def claim_one() -> Job | None:
    async with get_sessionmaker()() as session:
        job = await session.scalar(
            select(Job)
            .where(Job.status == "queued", Job.run_after <= utcnow())
            .order_by(Job.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status, job.started_at = "running", utcnow()
        job.attempts += 1
        await session.commit()
        return job


async def execute(job: Job) -> None:
    fn = HANDLERS.get(job.kind)
    async with get_sessionmaker()() as session:
        row = await session.get(Job, job.id)
        assert row is not None
        try:
            if fn is None:
                raise LookupError(f"no handler for job kind {job.kind!r}")
            row.result = await fn(dict(job.payload))
            row.status = "succeeded"
        except Exception as exc:
            log.exception("job failed", extra={"ctx": {"job": str(job.id), "kind": job.kind}})
            row.error = f"{type(exc).__name__}: {exc}"[:2000]
            retry = row.attempts < row.max_attempts and fn is not None
            row.status = "queued" if retry else "failed"
            row.run_after = utcnow() + RETRY_DELAY * row.attempts
        row.finished_at = utcnow()
        await session.commit()


async def housekeeping() -> None:
    now = utcnow()
    async with get_sessionmaker()() as session:
        await session.execute(delete(UserSession).where(UserSession.expires_at <= now))
        await session.execute(
            delete(RoleBinding).where(
                RoleBinding.expires_at.is_not(None), RoleBinding.expires_at <= now
            )
        )
        await session.execute(
            text("DELETE FROM job WHERE finished_at < now() - interval '30 days'")
        )
        await session.commit()


async def _loop(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    next_housekeeping = 0.0
    while not stop.is_set():
        try:
            if loop.time() >= next_housekeeping:
                await housekeeping()
                next_housekeeping = loop.time() + HOUSEKEEPING_S
            job = await claim_one()
            if job is not None:
                await execute(job)
                continue
        except Exception as exc:
            log.warning("worker loop error", extra={"ctx": {"error": str(exc)}})
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=POLL_S)


def run() -> None:
    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await _loop(stop)

    asyncio.run(_main())
