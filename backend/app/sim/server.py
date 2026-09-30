"""EM16P device simulator (TST-010).

Mimics the quirks in the API spec: bare GET results, POST envelopes, ``invalid namespace``
text, a 60-row cap on ``Em.Data.Get``, empty ``emmerge`` status objects, notifications only
after the first WebSocket request, and optional digest auth.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.devices import digest
from app.sim import model

DEV_ID = os.environ.get("SIM_DEV_ID", "meross-em16p-51a100000001")
RETENTION_S = int(os.environ.get("SIM_RETENTION_H", "48")) * 3600
NOTIFY_S = float(os.environ.get("SIM_NOTIFY_S", "16"))
BOOT = int(time.time())
MERGES = [
    {"id": 0, "name": "Waterfall Pool Pump", "channels": 130},
    {"id": 1, "name": "Main Pool Pump", "channels": 1040},
    {"id": 2, "name": "AC Condenser", "channels": 2080},
]
NAMES = {
    1: "Primary Phase A",
    2: "Phase A Waterfall Pool Pump",
    5: "Phase A Main Pool Pump",
    6: "Phase A AC Condenser",
    7: "Primary Phase B",
    8: "Phase B Waterfall Pool Pump",
    11: "Phase B Main Pool Pump",
    12: "Phase B AC Condenser",
}
LABELS = [f"{p}{i}" for p in "ABC" for i in range(1, 7)]


class SimState:
    def __init__(self, password: str | None) -> None:
        self.password = password
        self.nonce = secrets.randbelow(2**31)
        self.nc = 1

    def challenge(self) -> dict[str, Any]:
        return {
            "code": 401,
            "message": json.dumps({"nonce": self.nonce, "nc": self.nc, "realm": DEV_ID}),
        }

    def check_auth(self, auth: dict[str, Any] | None) -> bool:
        if not self.password:
            return True
        if not auth:
            return False
        expected = digest.build_auth(
            DEV_ID, self.password, auth.get("nonce", ""), int(auth.get("nc", 0)), auth.get("cnonce")
        )
        return auth.get("nonce") == self.nonce and auth.get("response") == expected["response"]


def _midnight(now: int) -> int:
    return now - now % 86400


def channel_status(channel: int, now: int) -> dict[str, Any]:
    p = model.power(channel, now)
    v = model.voltage(channel)
    day = model.energy_since(channel, max(_midnight(now), BOOT - RETENTION_S), now)
    return {
        "id": channel,
        "current": round(p / v if v > 1 else 0.0, 3),
        "voltage": v,
        "power": round(p, 3),
        "pf": 0.9 if p else 0,
        "day_energy": round(day, 3),
        "day_ret_energy": 0,
        "week_energy": round(day, 3),
        "week_ret_energy": 0,
        "month_energy": round(day, 3),
        "month_ret_energy": 0,
        "year_energy": round(day, 3),
        "year_ret_energy": 0,
    }


def status(now: int, full: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {f"em:{c}": channel_status(c, now) for c in range(1, model.CHANNELS + 1)}
    if full:
        out.update({f"emmerge:{m['channels']}": {} for m in MERGES})
        out["wifi"] = {"sta_ip": "sim", "status": "connected", "ssid": "sim", "rssi": -52}
        out["mqtt"] = {"connected": False}
        out["cloud"] = {"connected": False}
        out["sys"] = {
            "mac": "51:a1:00:00:00:01",
            "restart_required": False,
            "unixtime": now,
            "uptime": now - BOOT,
            "cfg_rev": 1,
            "available_updates": {"version": None},
        }
    return out


def history(params: dict[str, Any], now: int) -> dict[str, Any] | None:
    try:
        channel, start, end = int(params["id"]), int(params["start_ts"]), int(params["end_ts"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 1 <= channel <= model.CHANNELS:
        return None
    oldest = now - RETENTION_S
    first = max(start, oldest)
    first -= first % 60
    last = min(end, now - now % 60)
    rows: list[list[float]] = []
    ts = first
    while ts < last and len(rows) < 60:
        rows.append(model.minute_row(channel, ts))
        ts += 60
    result: dict[str, Any] = {
        "next_ts": ts if ts < last else None,
        "keys": [
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
        ],
    }
    result["data"] = [{"id": channel, "ts": first, "period": 60, "values": rows}] if rows else []
    return result


def dispatch(method: str, params: dict[str, Any]) -> Any:
    now = int(time.time())
    if method == "Refoss.DeviceInfo.Get":
        return {
            "name": "Simulated Energy Monitor",
            "model": "em16p",
            "dev_id": DEV_ID,
            "mac": "51:a1:00:00:00:01",
            "api_ver": "1.0",
            "fw_ver": "13.1.4",
            "hw_ver": "13.0.0",
            "auth_en": False,
        }
    if method == "Refoss.Status.Get":
        return status(now)
    if method == "Refoss.Config.Get":
        cfg: dict[str, Any] = {
            f"em:{c}": {"id": c, "name": NAMES.get(c, LABELS[c - 1]), "factor": 1}
            for c in range(1, model.CHANNELS + 1)
        }
        cfg.update({f"emmerge:{m['channels']}": {"name": m["name"]} for m in MERGES})
        return cfg
    if method == "Em.Chmerge.List":
        return MERGES
    if method == "Em.Data.Get":
        return history(params, now)
    if method in ("Sys.Config.Get", "Cloud.Config.Get"):
        return {"device": {"name": "Simulated Energy Monitor"}, "time": {"time_zone": "UTC"}}
    raise KeyError(method)


def create_sim_app(password: str | None = None) -> Starlette:
    state = SimState(password or os.environ.get("SIM_PASSWORD") or None)

    def info_with_auth(result: Any, method: str) -> Any:
        if method == "Refoss.DeviceInfo.Get" and state.password:
            return {**result, "auth_en": True}
        return result

    async def get_rpc(request: Request) -> Response:
        method = request.path_params["method"]
        if state.password and method != "Refoss.DeviceInfo.Get":
            return JSONResponse({"error": state.challenge()}, status_code=401)
        params = {
            k: json.loads(v) if v.lstrip("-").isdigit() else v.strip('"')
            for k, v in request.query_params.items()
        }
        try:
            result = dispatch(method, params)
        except KeyError:
            return PlainTextResponse("invalid namespace")
        if result is None:
            return PlainTextResponse("There is an error. Try it again.")
        return JSONResponse(info_with_auth(result, method))

    async def post_rpc(request: Request) -> Response:
        frame = await request.json()
        method, params = frame.get("method", ""), frame.get("params") or {}
        base = {"id": frame.get("id"), "src": DEV_ID}
        if method != "Refoss.DeviceInfo.Get" and not state.check_auth(frame.get("auth")):
            return JSONResponse({**base, "error": state.challenge()})
        try:
            result = dispatch(method, params)
        except KeyError:
            return Response(status_code=500)  # the real device drops the connection
        if result is None:
            return JSONResponse(base)
        return JSONResponse({**base, "result": info_with_auth(result, method)})

    async def ws_rpc(ws: WebSocket) -> None:
        await ws.accept()
        client_src: str | None = None
        pusher: asyncio.Task[None] | None = None

        async def push() -> None:
            while True:
                now = int(time.time())
                await ws.send_json(
                    {
                        "src": DEV_ID,
                        "dst": client_src,
                        "method": "NotifyStatus",
                        "params": {"ts": now, **status(now, full=False)},
                    }
                )
                await asyncio.sleep(NOTIFY_S)

        try:
            while True:
                frame = await ws.receive_json()
                client_src = frame.get("src") or client_src
                method = frame.get("method", "")
                base = {"id": frame.get("id"), "src": DEV_ID, "dst": client_src}
                if state.password and not state.check_auth(frame.get("auth")):
                    await ws.send_json({**base, "error": state.challenge()})
                    continue
                try:
                    result = dispatch(method, frame.get("params") or {})
                    await ws.send_json({**base, "result": info_with_auth(result, method)})
                except KeyError:
                    await ws.send_json(
                        {**base, "error": {"code": 404, "message": "invalid namespace"}}
                    )
                if pusher is None:  # notifications start after the first request
                    pusher = asyncio.create_task(push())
        except WebSocketDisconnect:
            pass
        finally:
            if pusher is not None:
                pusher.cancel()

    return Starlette(
        routes=[
            Route("/rpc/{method}", get_rpc, methods=["GET"]),
            Route("/rpc", post_rpc, methods=["POST"]),
            WebSocketRoute("/rpc", ws_rpc),
        ]
    )
