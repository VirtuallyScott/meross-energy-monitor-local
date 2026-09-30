"""Async client for the EM16P local RPC API (API spec §1, §2, §4).

One client instance per device. HTTP calls are serialized per device (COL-007) and every
method is checked against the allow-list (SEC-030) before it is sent.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets

from app.devices import digest
from app.devices.allowlist import check_method

log = logging.getLogger(__name__)

MAX_REPLY_BYTES = 1_000_000  # SEC-043
HISTORY_KEYS = [
    "energy",
    "ret_energy",
    "voltage_max",
    "voltage_min",
    "voltage_avg",
    "current_max",
    "current_min",
    "current_avg",
    "power_max",
    "power_min",
    "power_avg",
    "ret_power_max",
    "ret_power_min",
    "ret_power_avg",
]


class DeviceRpcError(RuntimeError):
    """The device answered, but not with a usable ``result``."""


class DeviceAuthError(DeviceRpcError):
    """Auth is enabled and no password, or a wrong password, was supplied."""


class DeviceUnreachableError(DeviceRpcError):
    """Network-level failure talking to the device."""


@dataclass(frozen=True)
class HistoryRow:
    ts: int
    values: dict[str, float | None]


@dataclass
class DeviceClient:
    base_url: str
    password: str | None = None
    timeout: float = 8.0
    dev_id: str | None = None
    src: str = field(default_factory=lambda: f"energy-hub-{uuid.uuid4().hex[:8]}")
    _http: httpx.AsyncClient | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _ids: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    async def __aenter__(self) -> DeviceClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=False, trust_env=False
            )
        return self._http

    # ------------------------------------------------------------------ HTTP
    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        check_method(method, params)
        async with self._lock:
            frame = self._frame(method, params)
            envelope = await self._post(frame)
            error = envelope.get("error")
            if isinstance(error, dict) and error.get("code") == 401:
                envelope = await self._post(self._with_auth(frame, error))
                error = envelope.get("error")
            if isinstance(error, dict):
                if error.get("code") == 401:
                    raise DeviceAuthError("device rejected the credentials")
                raise DeviceRpcError(f"{method}: {error.get('message', error)}")
            if "result" not in envelope:
                raise DeviceRpcError(f"{method}: reply has no result (bad params?)")
            return envelope["result"]

    def _frame(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        frame: dict[str, Any] = {"id": next(self._ids), "src": self.src, "method": method}
        if params:
            frame["params"] = params
        return frame

    def _with_auth(self, frame: dict[str, Any], error: dict[str, Any]) -> dict[str, Any]:
        if not self.password:
            raise DeviceAuthError("device requires a password")
        nonce, nc, realm = digest.parse_challenge(error)
        realm = realm or self.dev_id
        if not realm:
            raise DeviceAuthError("device id unknown; cannot build digest realm")
        return {**frame, "auth": digest.build_auth(realm, self.password, nonce, nc)}

    async def _post(self, frame: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client().post(f"{self.base_url}/rpc", json=frame)
        except httpx.HTTPError as exc:
            raise DeviceUnreachableError(f"{frame['method']}: {type(exc).__name__}") from exc
        if len(response.content) > MAX_REPLY_BYTES:
            raise DeviceRpcError("reply too large")
        try:
            body = response.json()
        except ValueError as exc:
            text = response.text[:80]
            raise DeviceRpcError(f"{frame['method']}: non-JSON reply {text!r}") from exc
        if not isinstance(body, dict):
            raise DeviceRpcError(f"{frame['method']}: unexpected reply type")
        return body

    # --------------------------------------------------------------- helpers
    async def device_info(self) -> dict[str, Any]:
        info: dict[str, Any] = await self.call("Refoss.DeviceInfo.Get")
        self.dev_id = self.dev_id or info.get("dev_id")
        return info

    async def status(self) -> dict[str, Any]:
        result: dict[str, Any] = await self.call("Refoss.Status.Get")
        return result

    async def config(self) -> dict[str, Any]:
        result: dict[str, Any] = await self.call("Refoss.Config.Get")
        return result

    async def merges(self) -> list[dict[str, Any]]:
        result = await self.call("Em.Chmerge.List")
        return list(result or [])

    async def history(
        self, channel: int, start_ts: int, end_ts: int, page_gap_s: float = 0.2
    ) -> AsyncIterator[HistoryRow]:
        """Yield per-minute rows oldest first, following ``next_ts`` pagination."""
        cursor = start_ts
        while cursor < end_ts:
            result = await self.call(
                "Em.Data.Get", {"id": channel, "start_ts": cursor, "end_ts": end_ts}
            )
            data = (result.get("data") or [{}])[0] if isinstance(result, dict) else {}
            values = data.get("values") or []
            if not values:
                return
            keys = result.get("keys") or HISTORY_KEYS
            ts0, period = int(data["ts"]), int(data.get("period", 60))
            for i, row in enumerate(values):
                yield HistoryRow(ts=ts0 + i * period, values=dict(zip(keys, row, strict=False)))
            next_ts = result.get("next_ts")
            if not next_ts or next_ts <= cursor:
                return
            cursor = int(next_ts)
            await asyncio.sleep(page_gap_s)

    # ------------------------------------------------------------- WebSocket
    def ws_url(self) -> str:
        scheme = "wss" if self.base_url.startswith("https") else "ws"
        return f"{scheme}{self.base_url[self.base_url.index('://') :]}/rpc"

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        """Yield ``NotifyStatus`` params from one WebSocket session.

        Returns when the socket closes; the caller handles reconnect and backoff (COL-006).
        Notifications only start after a first request, so one is sent on connect (COL-001).
        """
        async with websockets.connect(
            self.ws_url(), open_timeout=self.timeout, ping_interval=20, max_size=MAX_REPLY_BYTES
        ) as ws:
            hello = self._frame("Refoss.DeviceInfo.Get", None)
            await ws.send(json.dumps(hello))
            auth_tried = False
            async for raw in ws:
                message = json.loads(raw)
                error = message.get("error")
                if message.get("id") == hello["id"] and isinstance(error, dict):
                    if error.get("code") != 401:
                        raise DeviceRpcError(f"WS hello failed: {error}")
                    if auth_tried:
                        raise DeviceAuthError("device rejected the credentials")
                    auth_tried = True
                    hello = self._with_auth(self._frame("Refoss.DeviceInfo.Get", None), error)
                    await ws.send(json.dumps(hello))
                    continue
                if message.get("method") == "NotifyStatus" and isinstance(
                    message.get("params"), dict
                ):
                    yield message["params"]
