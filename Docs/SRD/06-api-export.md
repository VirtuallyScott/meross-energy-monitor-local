# SRD 06 — API and Export

## 1. REST API conventions

| ID | Pri | Requirement |
|---|---|---|
| API-001 | M | Base path `/api/v1`. JSON only. OpenAPI 3.1 spec generated from code and served at `/api/v1/openapi.json`; interactive docs available to authenticated users only. |
| API-002 | M | Response envelope: `{"data": ..., "error": null, "meta": {...}}` on success and `{"data": null, "error": {"code": "...", "message": "...", "request_id": "..."}}` on failure. |
| API-003 | M | List endpoints use cursor pagination (`?limit=&cursor=`), default 50, max 500. `meta` carries `next_cursor`. |
| API-004 | M | Timestamps in and out are RFC 3339 with offset. Ranges are half-open `[from, to)`. Time-series responses state the resolution and time zone used. |
| API-005 | M | Status codes: 200, 201, 202 (async job accepted), 204, 400 (validation), 401, 403, 404 (includes out-of-scope, RBAC-003), 409 (conflict, for example duplicate `dev_id`), 422, 429, 500. |
| API-006 | M | Writes that change config accept `If-Match` with the resource's `version` to prevent lost updates. |
| API-007 | M | Every endpoint declares its permission (RBAC-001). |
| API-008 | S | Idempotency key header (`Idempotency-Key`) for POST endpoints that create jobs or device writes. |

## 2. Endpoint outline

| Area | Endpoints (abbreviated) | Permission |
|---|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `POST /auth/mfa/verify`, `GET /auth/me`, `POST /setup` (first run) | public / session |
| Users | `GET/POST /users`, `PATCH /users/{id}`, `GET/POST/DELETE /users/{id}/bindings` | `user:*`, `role:assign` |
| Tokens | `GET/POST /tokens`, `DELETE /tokens/{id}` | `token:self` |
| Sites | `GET/POST /sites`, `GET/PATCH /sites/{id}` | `site:*` |
| Devices | `POST /devices/probe` (preview before add), `GET/POST /devices`, `GET/PATCH/DELETE /devices/{id}`, `PUT /devices/{id}/credential`, `POST /devices/{id}/test`, `POST /devices/{id}/sync`, `POST /devices/{id}/reboot`, `GET /devices/{id}/events` | `device:*` |
| Device config | `PUT /devices/{id}/channels` (names, factors → device), `GET/POST/PATCH/DELETE /devices/{id}/merges` | `device:configure` |
| Discovery | `POST /discovery` (CIDR) → job | `device:discover` |
| Channels | `GET /channels`, `PATCH /channels/{id}` (role, local name, visibility) | `device:manage` |
| Circuits | `GET/POST /circuits`, `GET/PATCH/DELETE /circuits/{id}` | `circuit:*` |
| Live | `GET /live/stream?site=` (Server-Sent Events), `GET /live/snapshot?site=` | `data:read` |
| Readings | `GET /readings?circuits=&from=&to=&resolution=&metrics=` | `data:read` |
| Breakdown | `GET /breakdown?site=&from=&to=` (kWh and cost per circuit) | `data:read`, `bill:read` |
| Tariffs | `GET/POST /rate-plans`, `GET/POST /rate-plans/{id}/versions`, `POST /rate-plans/{id}/versions/{v}/validate`, `POST /rate-plans/import`, `GET /rate-plans/{id}/export` | `tariff:*` |
| Assignment | `GET/POST /sites/{id}/rate-assignments`, `PUT /sites/{id}/billing-cycle-rule`, `GET /sites/{id}/billing-cycles` | `tariff:assign` |
| Bills | `GET /sites/{id}/bills?cycle=`, `POST /sites/{id}/bills/estimate` → job, `GET /bills/{id}`, `POST /sites/{id}/bills/compare` → job, `GET /sites/{id}/projection` | `bill:read`, `bill:run` |
| Actual bills | `GET/POST/PATCH/DELETE /sites/{id}/actual-bills` | `bill:actual` |
| Alerts | `GET /alerts`, `POST /alerts/{id}/ack`, `GET/POST/PATCH/DELETE /alert-rules`, `/notification-channels` | `alert:*` |
| Exports | `POST /exports` → job, `GET /exports`, `GET /exports/{id}/download`, `GET/POST/PATCH/DELETE /export-schedules` | `data:export` |
| Jobs | `GET /jobs/{id}`, `POST /jobs/{id}/cancel` | owner or `system:health` |
| System | `GET /system/health`, `GET /system/version`, `GET/PATCH /system/settings`, `POST /system/backups`, `GET /system/backups` | `system:*` |
| Audit | `GET /audit` | `audit:read` |

### 2.1 Readings query

```
GET /api/v1/readings?circuits=<id>,<id>&from=2026-09-01T00:00:00-04:00&to=2026-10-01T00:00:00-04:00
                    &resolution=auto|minute|15m|hour|day|month&metrics=energy,ret_energy,power_avg,power_max
                    &tz=site
```

- `auto` picks a resolution returning at most about 2,000 points per series.
- `day` and `month` are local-time buckets in the site time zone.
- Max range per request: 7 days at `minute`, 400 days at `15m`, unlimited at `hour` and coarser.
- Each point carries `quality` (worst quality among its source rows) so the UI can mark estimated data.

### 2.2 Live stream

`GET /live/stream?site=<id>` returns Server-Sent Events. Events: `snapshot` (on connect), `sample` (per device notification, circuit totals included), `device_state` (online/offline), `alert`. Heartbeat comment every 15 s. The server closes streams when the session or token expires.

### 2.3 Integration endpoints

| ID | Pri | Requirement |
|---|---|---|
| API-020 | S | Prometheus-format endpoint `/metrics/energy` (token-protected) exposing per-circuit power, and energy counters built from minute buckets (monotonic, never reset). |
| API-021 | C | Home Assistant friendly JSON endpoint and documentation for a REST sensor setup. |

## 3. Export

### 3.1 What can be exported

| Dataset | Content | Pri |
|---|---|---|
| Readings | Per circuit or channel: timestamp, import kWh, export kWh, power avg/min/max, voltage avg/min/max, current avg, quality | M |
| Daily summary | Per circuit per local day: import kWh, export kWh, peak W, cost | M |
| Bill estimate | Header (site, cycle, plan, coverage), line items, TOU and tier breakdown | S |
| Plan comparison | Per cycle per plan totals | S |
| Rate plan | Plan JSON (BIL-015) | M |
| Device and circuit config | JSON, with no credentials | S |
| Audit log | CSV | S |
| Green Button (ESPI XML) interval data | Standard utility format | C |

### 3.2 Requirements

| ID | Pri | Requirement |
|---|---|---|
| EXP-001 | M | Formats: CSV (RFC 4180, UTF-8, header row, `.` decimal separator) and JSON (array of records, or NDJSON for large sets). |
| EXP-002 | S | XLSX with one sheet per dataset and a metadata sheet. |
| EXP-004 | M | Parameters: site, circuits or channels, range, resolution (minute, 15m, hour, day, month), time zone (site local or UTC), columns. Local-time exports include both a local timestamp with offset and a UTC timestamp column, so DST repeated hours are unambiguous. |
| EXP-005 | M | Exports run as background jobs. Files over 5 MB are gzip-compressed. Users see progress and download when done. Files expire after 7 days (configurable). |
| EXP-006 | M | Exports stream rows from the DB in batches; memory use must stay bounded for a 2-year minute-resolution export. |
| EXP-007 | M | Exports contain only resources in the requester's scope. The job re-checks permissions when it runs, not only when queued. |
| EXP-008 | M | CSV cells starting with `=`, `+`, `-`, `@`, tab or CR are prefixed with `'` to prevent formula injection when opened in spreadsheets. Numeric columns are exempt. |
| EXP-003 | S | Scheduled exports (daily, weekly, monthly, cron) written to a mounted export volume with a templated file name (for example `{site}/{yyyy}/{mm}/readings-{date}.csv`). |
| EXP-009 | S | Each export writes a small manifest JSON next to the file: parameters, row count, SHA-256, app version, generated time. |
| EXP-010 | C | Scheduled export delivery by email (SMTP) for small files. |
| EXP-011 | M | Every export is audit-logged with parameters and row count. |

### 3.3 CSV example (readings, 15 min)

```csv
ts_local,ts_utc,site,circuit,import_kwh,export_kwh,power_avg_w,power_max_w,voltage_avg_v,quality
2026-09-01T00:00:00-04:00,2026-09-01T04:00:00Z,Main house,Whole house,0.712,0.000,2848.1,2921.4,124.3,device
2026-09-01T00:15:00-04:00,2026-09-01T04:15:00Z,Main house,Whole house,0.698,0.000,2791.9,2880.0,124.2,device
```
