# SRD 01 — Functional Requirements

Priority: **M** must, **S** should, **C** could, **W** won't (v1). Protocol details: [../Reverse_API/meross-em16p-api-spec.md](../Reverse_API/meross-em16p-api-spec.md).

## 1. Sites

| ID | Pri | Requirement |
|---|---|---|
| SITE-001 | M | A user with `site:manage` can create, edit and archive sites. A site has a name, an IANA time zone, an optional address and a currency (ISO 4217). |
| SITE-002 | M | Every device belongs to exactly one site. A device can be moved between sites; history stays with the device. |
| SITE-003 | M | All calendar logic for a site (days, billing cycles, TOU windows) uses the site time zone, including DST transitions. |
| SITE-004 | S | A site can mark which channel or virtual circuit represents **grid import/export**, **solar generation** and **whole-house consumption**. These drive billing and the overview. |
| SITE-005 | C | A site can carry a default dashboard layout. |

## 2. Device management

| ID | Pri | Requirement |
|---|---|---|
| DEV-001 | M | Add a device by entering a host: IPv4 address, hostname, or URL (`http://host[:port]`). The system normalizes it to scheme, host and port. |
| DEV-002 | M | On add, the system calls `Refoss.DeviceInfo.Get` and shows the model, firmware, `dev_id` and `auth_en` before the user confirms. Adding fails with a clear message if the host is unreachable or the reply is not a recognized model. |
| DEV-003 | M | The system identifies a device by `dev_id`, not by address. If a known `dev_id` appears at a new address, the user is offered to update the address rather than create a duplicate. |
| DEV-004 | M | A device can store an optional password. The password is **write-only** through the UI and API, encrypted at rest (SEC-020) and used for digest auth when `auth_en` is true **[UNVERIFIED-API]**. |
| DEV-005 | M | "Test connection" validates reachability, identity match (`dev_id` unchanged) and auth, and reports latency. |
| DEV-006 | M | Supported models: `em16p`. |
| DEV-007 | S | Supported models: `em06p` (same firmware family, 6 channels). Channel count is taken from the status reply, not hard-coded. |
| DEV-008 | M | Device list shows: name, site, address, model, firmware, online state, last data time, Wi-Fi RSSI, uptime, collection state. |
| DEV-009 | M | A device can be **disabled** (no collection, data kept) and **deleted** (requires confirmation; user chooses keep or purge history). |
| DEV-010 | M | On connect and every 15 minutes, the system syncs device config: device name, channel names, CT factors, device merges. Drift is recorded as an event. |
| DEV-011 | S | Edit device channel names and CT factors from the UI, written back via `Em.Config.Set` with the full channel list. The UI warns that a negative factor flips direction. |
| DEV-012 | S | Create, edit and delete device merges via `Em.Chmerge.Create/Update/Del`, enforcing the device rule that a channel belongs to at most one merge. |
| DEV-013 | S | Rename a device via `Sys.Config.Set`. |
| DEV-014 | C | Reboot a device (`Refoss.Device.Reboot`) behind a confirmation dialog, restricted to Admin. |
| DEV-015 | C | Subnet discovery: scan a user-entered CIDR (maximum /24) for hosts that answer `Refoss.DeviceInfo.Get`. Rate limited, opt-in only. |
| DEV-016 | S | Show firmware version and `sys.available_updates.version`. Warn when firmware differs from the version the API spec was verified against. |
| DEV-017 | S | Show a security warning on any device where `auth_en` is false. |
| DEV-018 | W | Firmware upgrade, factory reset, on-device history delete, Wi-Fi and cloud config changes. |

## 3. Channels and circuits

| ID | Pri | Requirement |
|---|---|---|
| CIR-001 | M | Each channel has a local display name (defaults to the device name), a **role** (`grid_main`, `solar`, `battery`, `branch`, `unused`), a phase/leg label and a visibility flag. Users with `device:manage` set role and visibility on the device detail page. Hidden channels are still collected and stored, but left out of the live, overview, history and panel views. |
| CIR-002 | M | Channels with no CT connected (for example phase C at ~0.09 V and 0 W) are auto-suggested as `unused` and hidden by default. Readings of `unused` channels are not collected. Changing a channel's role out of `unused` makes it visible, and changing it to `unused` hides it, unless the same change sets visibility explicitly. |
| CIR-003 | M | Device merges are imported as circuits. Their totals are **computed by the system** because the device returns `emmerge:*` as empty objects. |
| CIR-004 | M | Users can define **virtual circuits** as a signed sum of channels from any devices in the same site, for example `whole_house = em:1 + em:7` or `unmetered = whole_house − Σ branches`. |
| CIR-005 | M | Circuit power and energy are summed. Current is summed only as an indicator and labeled as such. Voltage is not summed; the circuit shows the member channel voltages. |
| CIR-006 | S | Circuits can be grouped with tags (for example "Pool", "HVAC") for dashboards and reports. |
| CIR-007 | S | Negative results for derived circuits (for example unmetered load) are shown as-is and flagged, never clamped silently. |
| CIR-008 | M | Changing a circuit definition applies to all history (circuits are computed at query time or via rebuildable aggregates, never stored as frozen totals). |

### 3.1 Panels and breaker positions

| ID | Pri | Requirement |
|---|---|---|
| PNL-001 | M | A site has zero or more **panels** (main panel, subpanels). Each has a name, a number of breaker spaces (2 to 84, even) and a numbering scheme: `odd_even` (default, North American: odd spaces down the left, even down the right) or `sequential` (left column top to bottom, then right column). |
| PNL-002 | M | A **breaker** is placed on a panel by its starting space, pole count (1 single-pole, 2 **double-pole**, 3 triple-pole) and optional rating in amps, and gets **one sensor (channel) per pole**, for example CT A2 on space 1 and CT B2 on space 3 of a double-pole breaker. A pole may have no sensor, but a breaker needs at least one. The legs of a 240 V load often draw different current, so each pole's sensor is recorded separately. |
| PNL-003 | M | A multi-pole breaker occupies consecutive spaces on the same side: `n, n+2, n+4` for `odd_even`, `n, n+1, n+2` for `sequential`. Every occupied space must exist and stay in one column. |
| PNL-004 | M | A breaker, with all its sensors, is saved as one unit. Each pole holds at most one sensor and each sensor reads one pole. Breakers may not overlap. Sensors left out when a breaker is saved are removed from it. |
| PNL-005 | M | The device detail page shows each channel's breaker (for example `Main · 1/3 · 2P 30 A`, and for multi-pole breakers the space its sensor reads). Users with `device:manage` edit the breaker there: panel, space, single-, double- or triple-pole, rating and a sensor picker for each space. |
| PNL-006 | S | **Panel view**: a spatial drawing of each panel with breakers in their real spaces, multi-pole breakers spanning their spaces with each pole's own live reading level with its space, the breaker total, and empty spaces shown. A breaker links to its device. A list alternative serves keyboard and screen-reader users (UI-010). |
| PNL-010 | S | **Mains strip**: at the top of the panel view, where the main breaker and bus bars sit, the panel shows its mains channels (role `grid_main`, for example CT A1 and CT B1) with each channel's leg label, live voltage, live power and today's kWh, plus the combined power and today's kWh. A panel's mains are the `grid_main` channels of the devices with a sensor on that panel; a panel with no sensors placed yet shows the site's `grid_main` channels. With no mains channel the strip says so and points to the channel role setting (CIR-001). |
| PNL-011 | S | **Per-space readings**: every breaker, and every pole of a multi-pole breaker, shows its live voltage and a second reading chosen by the viewer: **power (W)** (default) or **current (A)**. The choice applies to the whole page, is kept in the URL (`?show=amps`) so it survives reload and can be shared, and is announced to screen readers. Current is the device's measured current; when the device reports none it is derived as W ÷ V and marked as estimated. A multi-pole breaker's total is summed in watts mode; in amps mode it shows the highest pole current, since leg currents of a 240 V load do not add. Missing readings show `—`, never 0. |
| PNL-007 | S | Reducing a panel's space count or changing its numbering is rejected while an assigned breaker would fall outside the panel or change column. Deleting a panel clears the position of its channels. |
| PNL-008 | C | Panel view shows load as a share of breaker rating, using live voltage, and flags breakers above 80 % of rating. |
| PNL-009 | C | Record breakers with no CT, tandem (half-size) breakers and a printable panel directory. |
| PNL-012 | C | Assign a panel's mains channels explicitly (for example a subpanel fed from a double-pole breaker in the main panel), overriding the PNL-010 default. |

Panel and breaker data is descriptive only. It never changes readings, circuits or billing.

## 4. Data collection

| ID | Pri | Requirement |
|---|---|---|
| COL-001 | M | The collector keeps **one** WebSocket per enabled device to `ws://<host>/rpc`, sends a first request so notifications start, and ingests `NotifyStatus` as live samples. |
| COL-002 | M | If the WebSocket is unavailable, the collector falls back to polling `Refoss.Status.Get` every 15 s. |
| COL-003 | M | Every 5 minutes, and on reconnect, the collector fetches `Em.Data.Get` per active channel from the last stored minute to now, following `next_ts` pagination (max 60 rows per call). Minute buckets are the **authoritative** energy record. |
| COL-004 | M | Ingest is idempotent: re-fetching the same minute for the same channel updates in place, never duplicates. |
| COL-005 | M | On startup the collector backfills each device from its last stored minute, up to what the device still holds. |
| COL-006 | M | Reconnect uses exponential backoff with jitter (5 s up to 5 min). A device is marked **offline** after 3 missed intervals (about 60 s without a sample). |
| COL-007 | M | Calls to a single device are serialized: at most one in-flight HTTP request per device, and a minimum gap between history pages (default 200 ms). |
| COL-008 | M | Handle device quirks: empty `data`, missing `result`, non-JSON bodies, `invalid namespace` text and dropped connections are errors for that call, logged, and never retried in a tight loop. |
| COL-009 | M | Unknown methods are never sent. The collector only issues methods on the allow-list in SEC-030. |
| COL-010 | M | Timestamps are stored in UTC. Device clock skew over 60 s versus the host is recorded as a data-quality event. |
| COL-011 | M | Collector exposes health (per-device state, last sample, last minute bucket, backlog) to the API and to Prometheus metrics. |
| COL-012 | S | Handle digest auth: on `401`, parse the nonce from `error.message`, compute the SHA-256 response and resend **[UNVERIFIED-API]**. |
| COL-013 | S | Record each gap (range with no minute data) with its cause (offline, device history exhausted, error). Gaps are visible on charts. |
| COL-014 | S | When minute history for a gap is no longer on the device, derive hourly energy from the difference of `*_energy` counters in live samples before and after, handling period resets. Rows derived this way are flagged `estimated`. |
| COL-015 | S | Collector instances coordinate with a per-device Postgres advisory lock so two replicas never poll the same device (safe rolling updates). |
| COL-016 | C | MQTT ingest as an alternative to WebSocket, once the topic layout is confirmed **[UNVERIFIED-API]**. |
| COL-017 | C | Capture `NotifyEvent` payloads to a raw event log for later analysis. |

## 5. Dashboards and views

| ID | Pri | Requirement |
|---|---|---|
| UI-001 | M | **Site overview**: live whole-house power, solar and grid exchange (if configured), today's kWh and estimated cost, month-to-date cost and projected bill, device health strip. |
| UI-002 | M | **Live view**: per-circuit power updating at the device notification rate (~15 to 20 s) via server push (SSE or WebSocket) from the backend, not from the browser to the device. |
| UI-003 | M | **History view**: time-series chart for one or more circuits over a chosen range, auto-selecting resolution (minute, 15 min, hour, day) by range. Shows min/avg/max bands where available. |
| UI-004 | M | **Energy breakdown**: kWh and cost per circuit for a range, as a ranked bar chart and table, including the unmetered remainder. |
| UI-005 | M | **Device detail**: all channels with V, A, W, PF, period energies, device status and config sync state. |
| UI-006 | S | Calendar heatmap of daily kWh; hour-of-day by weekday heatmap for load shape. |
| UI-007 | S | Compare two ranges (for example this month versus last month, or this July versus last July). |
| UI-008 | S | Power quality view: voltage min/avg/max per leg and power factor per circuit. |
| UI-009 | M | Responsive layout usable from 320 px width upward. Light and dark themes. |
| UI-010 | M | Meets WCAG 2.2 AA for contrast, keyboard navigation and screen-reader labels on charts (data table alternative). |
| UI-011 | C | Kiosk mode: a read-only full-screen overview reachable with a kiosk token (see RBAC). |

## 6. Alerts and notifications

| ID | Pri | Requirement |
|---|---|---|
| ALR-001 | S | Rule types: device offline for N minutes; circuit power above/below X W for N minutes; daily kWh or cost above budget; voltage outside a band; collector backlog. |
| ALR-002 | S | Channels: in-app, email (SMTP), generic webhook (JSON POST). |
| ALR-003 | S | Alerts have states (firing, acknowledged, resolved) with de-duplication and a cooldown. |
| ALR-004 | C | Channels: ntfy and Pushover. |
| ALR-005 | C | Budget alert based on projected bill exceeding a monthly target. |

## 7. Billing (summary)

Full rules in [05-billing-tariffs.md](05-billing-tariffs.md).

| ID | Pri | Requirement |
|---|---|---|
| BIL-001 | M | Flat rate per kWh plus fixed monthly charge. |
| BIL-002 | M | Time-of-use rates with seasons, weekday/weekend and holidays. |
| BIL-003 | M | Tiered (block) rates, including tiers inside TOU periods. |
| BIL-004 | M | Net metering and net billing variants for sites with solar or export. |
| BIL-005 | S | Demand charges. |
| BIL-006 | M | Bill estimate for any billing cycle, month-to-date projection, and plan comparison. |

## 8. Export (summary)

Export requirements are defined in [06-api-export.md](06-api-export.md): CSV and JSON export of readings (EXP-001), XLSX and bill export (EXP-002) and scheduled exports (EXP-003).

## 9. Administration

| ID | Pri | Requirement |
|---|---|---|
| ADM-001 | M | User management, roles and API tokens per [04-rbac-security.md](04-rbac-security.md). |
| ADM-002 | M | System settings: retention periods, collection intervals, SMTP, default currency, base URL. |
| ADM-003 | M | System health page: DB size, hypertable compression ratios, collector state, job queue, version. |
| ADM-004 | S | Trigger and download a database backup; show last successful backup time. |
| ADM-005 | M | Audit log viewer with filters (user, action, resource, time). |
