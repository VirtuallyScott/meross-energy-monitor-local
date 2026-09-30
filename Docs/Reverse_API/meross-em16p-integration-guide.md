# Meross EM16P Integration Guide

How to build your own interface on the local API. Read this alongside `meross-em16p-api-spec.md`.

---

## 1. Recommended architecture

```
                 ┌──────────────────────────────┐
                 │  EM16P  192.168.2.75         │
                 │  ws://…/rpc   http://…/rpc   │
                 └──────┬───────────────┬───────┘
          NotifyStatus  │               │  Em.Data.Get (hourly backfill)
          (~15 to 20 s) │               │  Refoss.Config.Get (names)
                        ▼               ▼
                 ┌──────────────────────────────┐
                 │  Collector (one process)      │
                 │  - one WS connection          │
                 │  - computes merged totals     │
                 │  - backfills gaps             │
                 └──────┬───────────────────────┘
                        ▼
                 Time series store  (InfluxDB, Prometheus, TimescaleDB, SQLite)
                        ▼
                 Your UI / Grafana / Home Assistant
```

Why this shape:

- **One collector owns the device.** It's a small embedded box. Many dashboards polling it directly add load and each would need to repeat the merge math.
- **WebSocket for live data.** You get pushes every 15 to 20 s without polling.
- **`Em.Data.Get` for accuracy.** Per-minute buckets with min, max and average come from the device itself. Use them to fill gaps after the collector restarts and to get real kWh instead of summing samples.
- **Merged circuits are computed by you.** The device returns `emmerge:*` as empty objects.

---

## 2. Python client

Needs Python 3.10+ and `pip install requests websockets`.

```python
"""em16p.py - minimal client for the Meross EM16P local RPC API."""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

import requests
import websockets

HISTORY_KEYS = [
    "energy", "ret_energy",
    "voltage_max", "voltage_min", "voltage_avg",
    "current_max", "current_min", "current_avg",
    "power_max", "power_min", "power_avg",
    "ret_power_max", "ret_power_min", "ret_power_avg",
]


def mask_to_channels(mask: int) -> list[int]:
    """emmerge bitmask -> list of em channel ids (1 based)."""
    return [bit + 1 for bit in range(mask.bit_length()) if mask >> bit & 1]


def channels_to_mask(channels: list[int]) -> int:
    return sum(1 << (c - 1) for c in channels)


class RpcError(RuntimeError):
    pass


@dataclass
class EM16P:
    host: str
    timeout: float = 5.0

    # ---------- HTTP ----------
    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        body = {"id": 1, "method": method}
        if params:
            body["params"] = params
        r = requests.post(f"http://{self.host}/rpc", json=body, timeout=self.timeout)
        r.raise_for_status()
        env = r.json()
        if "error" in env:
            raise RpcError(env["error"])
        if "result" not in env:
            raise RpcError(f"{method}: no result (bad params?)")
        return env["result"]

    def device_info(self) -> dict:
        return self.call("Refoss.DeviceInfo.Get")

    def status(self) -> dict:
        return self.call("Refoss.Status.Get")

    def config(self) -> dict:
        return self.call("Refoss.Config.Get")

    def merges(self) -> list[dict]:
        return self.call("Em.Chmerge.List")

    def history(self, channel: int, start_ts: int, end_ts: int) -> list[dict]:
        """Per-minute rows for one channel, following next_ts pagination (60 rows max per call)."""
        rows: list[dict] = []
        cursor = start_ts
        while cursor < end_ts:
            res = self.call("Em.Data.Get", {"id": channel, "start_ts": cursor, "end_ts": end_ts})
            data = (res.get("data") or [{}])[0]
            values = data.get("values") or []
            if not values:
                break
            keys = res.get("keys", HISTORY_KEYS)
            ts0, period = data["ts"], data.get("period", 60)
            for i, v in enumerate(values):
                rows.append({"ts": ts0 + i * period, **dict(zip(keys, v))})
            nxt = res.get("next_ts")
            if not nxt or nxt <= cursor:
                break
            cursor = nxt
        return rows

    # ---------- WebSocket ----------
    async def stream(self, password: str | None = None) -> AsyncIterator[dict]:
        """Yield NotifyStatus params forever. Reconnects on failure."""
        src = f"em16p-client-{uuid.uuid4().hex[:8]}"
        ids = itertools.count(1)
        while True:
            try:
                async with websockets.connect(f"ws://{self.host}/rpc", ping_interval=20) as ws:
                    # Notifications only flow after a first request.
                    await ws.send(json.dumps({"id": next(ids), "src": src,
                                              "method": "Refoss.DeviceInfo.Get"}))
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("method") == "NotifyStatus":
                            yield msg["params"]
            except (OSError, websockets.ConnectionClosed):
                await asyncio.sleep(5)


# ---------- digest auth helper (for when auth_en is true) ----------
def digest_auth(dev_id: str, password: str, nonce: int, nc: int) -> dict:
    sha = lambda s: hashlib.sha256(s.encode()).hexdigest()
    cnonce = secrets.token_hex(8)
    ha1 = sha(f"admin:{dev_id}:{password}")
    ha2 = sha("dummy_method:dummy_uri")
    return {
        "username": "admin", "realm": dev_id, "nonce": nonce, "cnonce": cnonce,
        "nc": nc, "algorithm": "SHA-256",
        "response": sha(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}"),
    }


# ---------- merged circuit totals ----------
SUM_FIELDS = ["power", "current",
              "day_energy", "week_energy", "month_energy", "year_energy",
              "day_ret_energy", "week_ret_energy", "month_ret_energy", "year_ret_energy"]


def merged_totals(status: dict, merges: list[dict]) -> dict[str, dict]:
    out = {}
    for m in merges:
        chans = mask_to_channels(m["channels"])
        tot = {f: 0.0 for f in SUM_FIELDS}
        for c in chans:
            ch = status.get(f"em:{c}", {})
            for f in SUM_FIELDS:
                tot[f] += ch.get(f, 0) or 0
        out[m["name"]] = {"channels": chans, **{k: round(v, 3) for k, v in tot.items()}}
    return out


if __name__ == "__main__":
    dev = EM16P("192.168.2.75")
    info = dev.device_info()
    print(info["name"], info["model"], info["fw_ver"])

    st, cfg, merges = dev.status(), dev.config(), dev.merges()
    for n in range(1, 19):
        ch, name = st[f"em:{n}"], cfg[f"em:{n}"]["name"]
        if ch["power"] or ch["day_energy"]:
            print(f"em:{n:<2} {name:<30} {ch['power']:>9.1f} W  {ch['day_energy']:>7.3f} kWh today")

    for name, t in merged_totals(st, merges).items():
        print(f"TOTAL {name:<25} {t['power']:>9.1f} W  {t['day_energy']:>7.3f} kWh  ch={t['channels']}")

    now = int(time.time())
    hist = dev.history(1, now - 3 * 3600, now)
    print(f"history rows for em:1 over 3 h: {len(hist)}")
```

Notes on the client:

- `current` is added up for merged circuits the same way the UI does it. For a 240 V load split across two legs, the per-leg current is what matters, so the sum is only a rough indicator. Power and energy sum correctly.
- `history()` follows `next_ts` because the device caps each call at 60 one-minute rows.
- `stream()` sends one request after connecting because the device only pushes notifications to clients that have spoken first.

---

## 3. Recipes

### 3.1 Poll with plain curl and jq

```bash
H=192.168.2.75
curl -s http://$H/rpc/Refoss.Status.Get \
  | jq -r 'to_entries[] | select(.key|startswith("em:")) | select(.value.power>0)
           | "\(.key)\t\(.value.power) W\t\(.value.day_energy) kWh"'
```

### 3.2 Whole-house numbers

In this installation the mains CTs are on `em:1` (Primary Phase A) and `em:7` (Primary Phase B).

```
house_power_w   = em:1.power + em:7.power
house_today_kwh = em:1.day_energy + em:7.day_energy
unmetered_w     = house_power_w - sum(power of every branch channel)
```

The web UI's overview tiles ("Consumption", "Grid Exchange") show a figure close to `em:1 + em:7`. The exact formula the UI uses was not confirmed. See the open questions in the discovery notes.

### 3.3 Prometheus exporter shape

Suggested metrics:

```
em16p_power_watts{channel="1",name="Primary Phase A",phase="A"}
em16p_current_amps{...}
em16p_voltage_volts{...}
em16p_power_factor{...}
em16p_energy_kwh_total{channel="1",direction="import",period="year"}
em16p_merged_power_watts{circuit="AC Condenser"}
em16p_wifi_rssi_dbm
em16p_uptime_seconds
```

Use `year_energy` as the counter source, since it only resets once a year. Or better, add up `Em.Data.Get` bucket `energy` values into your own monotonic counter so resets never matter.

### 3.4 InfluxDB line protocol from history

```python
for r in dev.history(ch, start, end):
    print(f"em16p,channel={ch} "
          f"energy_kwh={r['energy']},power_avg={r['power_avg']},"
          f"power_max={r['power_max']},voltage_avg={r['voltage_avg']},"
          f"current_avg={r['current_avg']} {r['ts']}000000000")
```

### 3.5 MQTT instead of a WebSocket collector

The device already has MQTT turned on with `rpc_ntf: true`, but it is not connected. To use it:

1. Stand up a broker (Mosquitto, EMQX or similar) reachable from the device.
2. Call `Mqtt.Config.Set` (or use the web UI under Settings → MQTT) with your broker's `server`, `user` and password.
3. Subscribe to `meross-em16p-c4e7ae2545ab/#` and record the actual topic names. The layout is unverified.

The benefit is that the device pushes and any number of consumers can subscribe, with no single collector process to keep alive.

---

## 4. Hardening before you rely on it

| Item | Current | Recommendation |
|---|---|---|
| Device auth | `auth_en: false` | Set a password with `Refoss.Auth.Set` or the web UI. Right now anything on the LAN can call `Refoss.Factory.Reset` or `Em.Data.Del` |
| Network placement | Main LAN (192.168.2.0/24) | Put it on an IoT VLAN. Allow only the collector host to reach TCP 80 |
| Cloud | `cloud.enable: true`, connected | Keep it if you want the Meross app. Turn it off with `Cloud.Config.Set` if local only is the goal. Test that the web UI and API keep working first |
| Firmware | 13.1.4 | Watch `sys.available_updates.version`. Recheck this spec after any update since method names could change |
| Encryption | Plain HTTP and WS | Nothing to do on the device side. Keep the collector on the same segment, or front it with a reverse proxy that serves your UI over TLS |
| Static address | DHCP | Add a DHCP reservation for the MAC so `192.168.2.75` stays put |

Once auth is on, re-test that the HTTP GET form still works with your client. The digest flow is only confirmed for the WebSocket and POST frame format.

---

## 5. Things the client must handle

- **Empty `emmerge` status.** Compute totals yourself.
- **No history beyond install.** `Em.Data.Get` returns empty data for older ranges. Treat that as "no data", not as an error.
- **Missing `result`.** Bad params give an envelope with no `result` and no `error`.
- **Dropped connection on an unknown method over POST.** Don't retry in a tight loop.
- **Calendar resets.** `day_energy` drops to 0 at local midnight in `America/New_York`. `week`, `month` and `year` reset on their own boundaries.
- **Phase C channels.** `em:13` to `em:18` read about 0.09 V and 0 W. Hide them unless you add CTs there.
