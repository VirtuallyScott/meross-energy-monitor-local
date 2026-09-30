# Meross EM16P Local API Specification

Reverse engineered from the device's built-in web UI and checked against a live unit. This is not a vendor document. Anything marked **Unverified** came from reading the UI code but was not tested live.

| Item | Value |
|---|---|
| Device | Meross EM16P, a 16/18 channel CT energy monitor |
| Model string | `em16p` |
| Firmware | `fw_ver` 13.1.4, `hw_ver` 13.0.0 |
| API version | `api_ver` 1.0 |
| Device ID | `meross-em16p-c4e7ae2545ab` (the format is `meross-<model>-<mac without colons>`) |
| Host tested | `192.168.2.75` |
| Firmware lineage | Refoss firmware. The RPC namespaces are `Refoss.*` and the UI assets use `refoss-*` class names |
| Protocol family | Shelly Gen2 style JSON-RPC 2.0 over HTTP and WebSocket |
| Date verified | 2026-09-28 |

---

## 1. Transport

The same RPC endpoint is available three ways. They all share one method set.

### 1.1 HTTP GET

```
GET http://<host>/rpc/<Method>
GET http://<host>/rpc/<Method>?<param>=<value>&<param>=<value>
```

- The response body is the **bare `result` object**, with no envelope.
- Query parameters are passed as-is. String values are JSON-quoted in the UI code, for example `action="toggle"`. Numeric values are unquoted.
- Verified: `GET /rpc/Em.Data.Get?id=2&start_ts=...&end_ts=...` works.

### 1.2 HTTP POST

```
POST http://<host>/rpc
Content-Type: application/json   (not required; the device accepted a body with no content type)

{"id": 1, "method": "Em.Data.Get", "params": {"id": 1, "start_ts": 1790634000, "end_ts": 1790637600}}
```

Response envelope:

```json
{"id": 1, "src": "meross-em16p-c4e7ae2545ab", "result": { ... }}
```

### 1.3 WebSocket

```
ws://<host>/rpc
```

Request frame:

```json
{"id": 7, "src": "my-client-id", "method": "Refoss.Status.Get", "params": {}}
```

- `id` is a caller-chosen integer used to match replies to requests.
- `src` is a caller-chosen string that identifies your client. The device echoes it back as `dst` and uses it to address notifications to you. The web UI generates a random UUID string for this.
- `params` is optional.
- `auth` is added when authentication is enabled (see section 2).

Reply frame:

```json
{"id": 7, "src": "meross-em16p-c4e7ae2545ab", "dst": "my-client-id", "result": { ... }}
```

Notification frames have no `id`:

```json
{"src": "meross-em16p-c4e7ae2545ab", "dst": "my-client-id", "method": "NotifyStatus", "params": {"ts": 1790637650, "em:1": { ... }, ... }}
```

**Notifications only start after your first request on the socket.** A socket that sends nothing receives nothing. Send any cheap call, such as `Refoss.DeviceInfo.Get`, right after connecting. See section 5.

---

## 2. Authentication

`Refoss.DeviceInfo.Get` reports `auth_en`. On the tested unit it is `false`, so every method, including reboot and factory reset, can be called with no credentials.

When auth is enabled the scheme is HTTP digest style, carried inside the RPC frame, the same as Shelly Gen2.

| Field | Value |
|---|---|
| `username` | always `admin` |
| `realm` | the device's `dev_id` |
| `algorithm` | `SHA-256` |
| `nonce` | issued by the device in a 401 error |
| `cnonce` | random client value (the UI uses a 16 character random string) |
| `nc` | nonce count issued by the device |

Computation, copied from the UI login code:

```
ha1      = sha256_hex("admin:" + dev_id + ":" + password)
ha2      = sha256_hex("dummy_method:dummy_uri")
response = sha256_hex(ha1 + ":" + nonce + ":" + nc + ":" + cnonce + ":auth:" + ha2)
```

Auth object added to each request frame:

```json
"auth": {
  "username": "admin",
  "realm": "meross-em16p-c4e7ae2545ab",
  "nonce": 1234567890,
  "cnonce": "a1b2c3d4e5f6a7b8",
  "response": "<hex>",
  "algorithm": "SHA-256",
  "nc": 1
}
```

Challenge flow:

1. Send the request without `auth`.
2. The device replies with `error.code == 401`. `error.message` is a **JSON string** that contains at least `nonce` and `nc`.
3. Parse it, compute `response` and resend with `auth`.

**Unverified:** auth was disabled on the test unit, so this flow comes from the UI code only. Whether the plain HTTP GET form accepts digest headers when auth is on was not tested.

The password is set with `Refoss.Auth.Set`. The UI limits it to 32 characters.

---

## 3. Components and IDs

| Key | Meaning |
|---|---|
| `em:1` ... `em:18` | Individual CT channels |
| `emmerge:<mask>` | A merged ("Total") circuit. `<mask>` is a bitmask of the member channels |
| `wifi`, `mqtt`, `cloud`, `sys` | Device subsystems |

### 3.1 Channel map (this installation)

The web UI labels channels by phase group and position. The `em` IDs map in order:

| `em:` id | UI position | Current name | Notes |
|---|---|---|---|
| 1 | A1 | Primary Phase A | Main feed, leg A |
| 2 | A2 | Phase A Waterfall Pool Pump | |
| 3 | A3 | A3 | |
| 4 | A4 | A4 | Nonzero daily energy, unnamed |
| 5 | A5 | Phase A Main Pool Pump | |
| 6 | A6 | Phase A AC Condenser | |
| 7 | B1 | Primary Phase B | Main feed, leg B |
| 8 | B2 | Phase B Waterfall Pool Pump | |
| 9 | B3 | B3 | |
| 10 | B4 | B4 | Nonzero daily energy, unnamed |
| 11 | B5 | Phase B Main Pool Pump | |
| 12 | B6 | Phase B AC Condenser | |
| 13 to 18 | C1 to C6 | C1 to C6 | Voltage reads ~0.09 V. No phase C reference is connected (normal for US split phase) |

### 3.2 Merged circuit bitmask

```
mask = sum over member channels c of 2^(c - 1)
```

The UI builds it exactly this way (`channels += Math.pow(2, ch - 1)`).

| Mask | Binary | Channels | Name |
|---|---|---|---|
| 130 | `100000010` | 2, 8 | Waterfall Pool Pump |
| 1040 | `10000010000` | 5, 11 | Main Pool Pump |
| 2080 | `100000100000` | 6, 12 | AC Condenser |
| 260 | `100000100` | 3, 9 | ? |
| 520 | `1000001000` | 4, 10 | ?? |

**Important:** `emmerge:*` entries in `Refoss.Status.Get` are **empty objects** (`{}`). The device does not compute merged totals. The web UI adds up the member channels on the client side. Your interface has to do the same.

---

## 4. Method reference

Legend: **V** = verified live (read-only calls only). **U** = found in the UI code, not called. **X** = called, returned `invalid namespace` on this firmware.

### 4.1 Device (`Refoss.*`)

#### `Refoss.DeviceInfo.Get` (V)

Params: `{"ident": true}` optional (the UI sends it; the result is the same without it).

```json
{
  "name": "Primary Energy Monitor",
  "model": "em16p",
  "dev_id": "meross-em16p-c4e7ae2545ab",
  "mac": "c4:e7:ae:xx:xx:xx",
  "uuid": "25112180348072740703c4e7ae2545ab",
  "api_ver": "1.0",
  "fw_ver": "13.1.4",
  "hw_ver": "13.0.0",
  "auth_en": false
}
```

#### `Refoss.Status.Get` (V)

No params. Returns a live snapshot of everything.

```json
{
  "em:1": {
    "id": 1,
    "current": 25.628,
    "voltage": 124.169,
    "power": 2857.436,
    "pf": 0.9,
    "day_energy": 28.259,   "day_ret_energy": 0,
    "week_energy": 28.259,  "week_ret_energy": 0,
    "month_energy": 28.259, "month_ret_energy": 0,
    "year_energy": 28.259,  "year_ret_energy": 0
  },
  "em:2": { ... },
  "...": "...",
  "em:18": { ... },
  "emmerge:130": {},
  "emmerge:1040": {},
  "emmerge:2080": {},
  "emmerge:260": {},
  "emmerge:520": {},
  "wifi":  {"sta_ip": "192.168.2.75", "status": "connected", "ssid": "<ssid>", "rssi": -49},
  "mqtt":  {"connected": false},
  "cloud": {"connected": true},
  "sys": {
    "mac": "...",
    "restart_required": false,
    "unixtime": 1790637447,
    "uptime": 28063,
    "cfg_rev": 16,
    "schedule_rev": 1,
    "webhook_rev": 0,
    "available_updates": {"version": null}
  }
}
```

EM channel fields:

| Field | Unit | Notes |
|---|---|---|
| `current` | A | RMS |
| `voltage` | V | RMS, from the phase reference the channel is tied to |
| `power` | W | Active power. Imported power is positive |
| `pf` | none | Power factor, 0 to 1 |
| `*_energy` | kWh | Imported energy for the calendar day, week, month and year |
| `*_ret_energy` | kWh | Exported (returned) energy for the same periods |

Calendar boundaries follow the device time zone (`Sys.Config.Get` → `time.time_zone`).

#### `Refoss.Config.Get` (V)

```json
{
  "em:1": {"id": 1, "name": "Primary Phase A", "factor": 1},
  "...": "...",
  "emmerge:130": {"name": "Waterfall Pool Pump"},
  "wifi": {
    "roam":  {"enable": false, "rssi_thr": -60},
    "ap":    {"ssid": "...", "is_open": true, "enable": false},
    "sta_1": {"ssid": "...", "is_open": false, "enable": true, "ipv4mode": "dhcp", "ip": "...", "netmask": null, "gw": null, "nameserver": "..."},
    "sta_2": {"ssid": "...", "is_open": true, "enable": false, "ipv4mode": "dhcp", "ip": "...", "netmask": null, "gw": null, "nameserver": "..."}
  },
  "mqtt": {
    "enable": true,
    "rpc_ntf": true,
    "server": "...",
    "client_id": "",
    "user": "...",
    "topic_prefix": "meross-em16p-c4e7ae2545ab",
    "ssl_ca": null,
    "enable_ctrl": false
  },
  "cloud": {"server": "...", "enable": true}
}
```

`factor` is a per-channel CT multiplier. The UI describes a negative factor as "equivalent to flipping the direction of the current transformer."

#### `Refoss.Device.Reboot` (U)

No params. Reboots the device.

#### `Refoss.Factory.Reset` (U)

No params. **Destructive.** Wipes configuration.

#### `Refoss.Auth.Set` (U)

Sets or clears the device password. Param shape not captured. It is expected to be similar to Shelly's `SetAuth` (`user`, `realm`, `ha1`), but that is **unverified**.

#### `Refoss.Upgrade.Check` (U), `Refoss.Upgrade` (U)

Checks for and applies firmware updates. The result appears in `sys.available_updates.version`.

### 4.2 Energy (`Em.*`)

#### `Em.Data.Get` (V)

Per-minute history for one channel.

Params:

| Name | Type | Required | Notes |
|---|---|---|---|
| `id` | int | yes | `em` channel id, 1 to 18. Merged masks do **not** work (the reply has no `result`) |
| `start_ts` | int | yes | Unix seconds |
| `end_ts` | int | yes | Unix seconds |

Response:

```json
{
  "next_ts": 1790637780,
  "keys": ["energy", "ret_energy",
           "voltage_max", "voltage_min", "voltage_avg",
           "current_max", "current_min", "current_avg",
           "power_max", "power_min", "power_avg",
           "ret_power_max", "ret_power_min", "ret_power_avg"],
  "data": [
    {
      "id": 1,
      "ts": 1790637480,
      "period": 60,
      "values": [
        [0.049, 0, 124.493, 124.207, 124.325, 25.658, 25.384, 25.565, 2863.437, 2828.769, 2848.9, 0, 0, 0],
        [0.045, 0, 124.370, 124.056, 124.244, 25.580, 25.350, 25.476, 2852.357, 2813.150, 2834.843, 0, 0, 0]
      ]
    }
  ]
}
```

Semantics (verified):

- `period` is 60 seconds. Each row in `values` is one minute bucket.
- `ts` is the start of the first bucket. Row `i` covers `ts + 60*i` to `ts + 60*(i+1)`. Rows are oldest first.
- `energy` and `ret_energy` are **kWh within that bucket**. A 2,850 W load for one minute gives 0.0475 kWh, which matches the observed 0.049.
- **At most 60 rows (1 hour) per call.** A 6 hour request came back with 60 rows starting at `start_ts`. `next_ts` is where to start the next page.
- Asking for a range with no stored data returns `data` with no values (or no `data[0]`). Handle both.
- Retention is **unknown**. This unit had data only for the current install window (a few hours). Requests for 1, 7 and 30 days ago returned nothing.
- Calling it with no params returns `There is an error. Try it again.` over GET or an envelope with no `result` over POST.

#### `Em.Config.Set` (U)

Sets channel names and CT factors. Params from the UI:

```json
{"config": [
  {"id": 1, "name": "Primary Phase A", "factor": 1},
  {"id": 2, "name": "Phase A Waterfall Pool Pump", "factor": 1}
]}
```

The UI sends the full list of channels at once. Sending one channel is **unverified**.

#### `Em.Chmerge.List` (V)

```json
[
  {"id": 0, "name": "Waterfall Pool Pump", "channels": 130},
  {"id": 1, "name": "Main Pool Pump",      "channels": 1040},
  {"id": 2, "name": "AC Condenser",        "channels": 2080},
  {"id": 3, "name": "?",                   "channels": 260},
  {"id": 4, "name": "??",                  "channels": 520}
]
```

Note that `id` here is a list index (0 to 4). It is different from the `emmerge:<mask>` status key.

#### `Em.Chmerge.Create` (U), `Em.Chmerge.Update` (U)

Params: `{"id": <int>, "name": "<string>", "channels": <mask>}`. The UI refuses to put a channel in more than one merge.

#### `Em.Chmerge.Del` (U)

Deletes a merged circuit. Param shape not captured (probably `{"id": <int>}`).

#### `Em.Data.Del` (U)

**Destructive.** Clears stored energy history. Params not captured.

### 4.3 System (`Sys.*`)

#### `Sys.Config.Get` (V)

```json
{
  "device": {"name": "Primary Energy Monitor", "mac": "...", "fw_ver": "13.1.4"},
  "position": {"lat": 00000000, "lon": -00000000},
  "time": {
    "timestamp": 1790637618,
    "time_zone": "America/New_York",
    "time_rule": [[1772953200, -14400, 1], [1793512800, -18000, 0], "..."]
  },
  "DNDMod": {"led": false},
  "restart_required": false,
  "cfg_rev": 16
}
```

- `position.lat` and `position.lon` are integers equal to degrees × 10^6.
- `time_rule` is a DST table of `[transition_unix_ts, utc_offset_seconds, is_dst]`.
- `DNDMod.led` turns off the status LED ("do not disturb").

#### `Sys.Config.Set` (U)

Params: `{"config": { <partial Sys config> }}`. The UI renames the device with `{"config": {"device": {"name": "..."}}}`.

#### `Sys.Time.Update` (U)

Syncs device time. Params not captured.

### 4.4 Network

| Method | Status | Notes |
|---|---|---|
| `WiFi.Config.Set` | U | Station, AP and roaming settings. **Can knock the device off the network** |
| `WiFi.Scan.List` | U | Blocking scan. A test call did not return within the timeout, so treat it as slow |
| `Mqtt.Config.Set` | U | Fields as in `Refoss.Config.Get` → `mqtt`. `ssl_ca` choices in the UI: none, `ca.pem` (default TLS), `user_ca.pem` (user TLS) and a client certificate option |
| `Cloud.Config.Get` | V | `{"server": "...", "enable": true}` |
| `Cloud.Config.Set` | U | Turning off `enable` disconnects the device from the Meross cloud |

### 4.5 Automation

| Method | Status | Notes |
|---|---|---|
| `Webhook.Supported.List` | V | Map of event names (see below) |
| `Webhook.List` | V | `{"num": 0, "rev": 0, "hooks": []}` |
| `Webhook.Get`, `Webhook.Create`, `Webhook.Update`, `Webhook.Delete` | U | Hook objects carry `cid`, `event` and `urls[]`, similar to Shelly |
| `Timer.List`, `Schedule.List` | X | Shared UI code for switch and cover products. Not present on EM16P |
| `OverTemp.Config.Get`, `OverTemp.Config.Set` | X / U | `Get` returned `invalid namespace` on this unit |

Supported webhook events (from `Webhook.Supported.List`):

```
em.voltage_change          emmerge.current_change
em.current_change          emmerge.power_change
em.power_change            emmerge.day_energy_change
em.power_factor_change     ...
em.day_energy_change
em.day_ret_energy_change
em.week_energy_change
em.week_ret_energy_change
em.month_energy_change
em.month_ret_energy_change
...
```

The list was cut off in the capture. Call the method to get the full set. The threshold and condition fields for these events were not captured.

---

## 5. Notifications (WebSocket)

After the first request on a socket, the device pushes:

| Method | Observed cadence | Params |
|---|---|---|
| `NotifyStatus` | about every 15 to 20 s | `ts` plus every `em:N` object, same shape as `Refoss.Status.Get`. Does **not** include `sys`, `wifi` or `emmerge` |
| `NotifyEvent` | on events | Two top-level keys, including `ts`. Shape not fully captured |

Notifications are addressed to the `src` you used (`dst` on the frame).

---

## 6. MQTT

Configured under `mqtt` in the config.

| Field | Meaning |
|---|---|
| `enable` | Master switch. On for this unit |
| `server` | `host:port` of the broker |
| `topic_prefix` | Defaults to the device id |
| `rpc_ntf` | Publish RPC notifications (the same `NotifyStatus` / `NotifyEvent` frames) |
| `enable_ctrl` | Accept control commands over MQTT. Off |
| `ssl_ca` | TLS mode (see 4.4) |

Status shows `mqtt.connected: false`, so the configured broker is not reachable or not correct. Topic layout was not observed. If it follows Shelly Gen2, expect `<prefix>/events/rpc` for notifications and `<prefix>/rpc` for requests. That is **unverified**.

---

## 7. Errors

| Situation | HTTP GET | HTTP POST / WS |
|---|---|---|
| Unknown namespace | `200` with body `invalid namespace` (plain text) | POST: **connection dropped** (fetch failed) |
| Missing required params | `200` with `There is an error. Try it again.` | Envelope with `id` and `src` but no `result` or `error` |
| Auth required | not tested | `{"error": {"code": 401, "message": "<JSON string with nonce, nc>"}}` |

Clients should treat a non-JSON body, or an envelope with no `result`, as a failure.

---

## 8. Quick reference

```bash
H=192.168.2.75

# Identity
curl -s http://$H/rpc/Refoss.DeviceInfo.Get

# Live snapshot
curl -s http://$H/rpc/Refoss.Status.Get

# Channel names and factors
curl -s http://$H/rpc/Refoss.Config.Get

# Merged circuits
curl -s http://$H/rpc/Em.Chmerge.List

# Last hour of per-minute history for channel 1
NOW=$(date +%s)
curl -s "http://$H/rpc/Em.Data.Get?id=1&start_ts=$((NOW-3600))&end_ts=$NOW"

# Same, via POST
curl -s http://$H/rpc -d "{\"id\":1,\"method\":\"Em.Data.Get\",\"params\":{\"id\":1,\"start_ts\":$((NOW-3600)),\"end_ts\":$NOW}}"
```
