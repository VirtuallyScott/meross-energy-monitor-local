"""Fan-out of collector notifications to SSE clients (ARC-003).

One dedicated asyncpg connection per API process LISTENs on ``ehub_live``; each SSE client
gets an asyncio queue of device ids.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import asyncpg

from app.core.config import get_settings

log = logging.getLogger(__name__)
CHANNEL = "ehub_live"
QUEUE_SIZE = 100


class LiveHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._conn: asyncpg.Connection | None = None
        self._lock = asyncio.Lock()

    async def _ensure_listening(self) -> None:
        async with self._lock:
            if self._conn is not None and not self._conn.is_closed():
                return
            s = get_settings()
            self._conn = await asyncpg.connect(
                host=s.db_host,
                port=s.db_port,
                user=s.db_user,
                password=s.db_password,
                database=s.db_name,
            )
            await self._conn.add_listener(CHANNEL, self._on_notify)

    def _on_notify(self, _conn: Any, _pid: int, _channel: str, payload: str) -> None:
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    async def subscribe(self) -> asyncio.Queue[str]:
        await self._ensure_listening()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


hub = LiveHub()
