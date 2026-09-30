# SRD 03 — Data Model

PostgreSQL 16+ with TimescaleDB 2.x. Types below are indicative; the Alembic migrations are the source of truth once written. All timestamps are `timestamptz` stored in UTC. Energy is kWh as `double precision` in raw tables and `numeric(14,6)` in billing results.

## 1. Principles

| ID | Pri | Requirement |
|---|---|---|
| DAT-001 | M | Config data lives in ordinary tables. Time-series data lives in hypertables. |
| DAT-002 | M | **Minute buckets are the source of truth for energy.** Live samples are for real-time display and gap estimation only. |
| DAT-003 | M | Raw data is stored per **channel**. Circuits (device merges and virtual circuits) are computed from channels at query time or in rebuildable aggregates. |
| DAT-004 | M | Every row carries enough keys to be re-derived: `channel_id`, `ts`, and a `source` / `quality` flag. |
| DAT-005 | M | Primary keys are UUIDv7 for config entities (time-ordered, safe to expose). Hypertables use natural composite keys. |
| DAT-006 | M | Soft delete (`archived_at`) for sites, devices, circuits and rate plans, so historic bills stay reproducible. |

## 2. Configuration schema

```sql
site (
  id uuid pk, name text not null, time_zone text not null,      -- IANA name
  currency char(3) not null default 'USD', address text,
  grid_circuit_id uuid null, solar_circuit_id uuid null, load_circuit_id uuid null,
  created_at, updated_at, archived_at
)

device (
  id uuid pk, site_id uuid fk site,
  dev_id text unique not null,           -- e.g. meross-em16p-c4e7ae2545ab
  display_name text, device_name text,   -- local name vs name on device
  base_url text not null,                -- normalized http://host:port
  model text not null, fw_ver text, hw_ver text, mac text,
  auth_enabled bool not null default false,
  credential_ciphertext bytea null,      -- AES-256-GCM, see SEC-020
  credential_key_version int null,
  enabled bool not null default true,
  last_seen_at timestamptz, last_minute_ts timestamptz,
  created_at, updated_at, archived_at
)

channel (
  id uuid pk, device_id uuid fk device, channel_no smallint,   -- 1..18
  device_label text,                     -- name reported by device
  display_name text, role text check (role in ('grid_main','solar','battery','branch','unused')),
  phase_label text, ct_factor double precision, visible bool default true,
  panel_id uuid null fk panel,           -- PNL-002: where the CT's breaker sits
  panel_slot smallint null,              -- starting space, 1-based
  breaker_poles smallint null check (breaker_poles in (1,2,3)),
  breaker_pole smallint null check (breaker_pole between 1 and breaker_poles),  -- leg this CT reads
  breaker_amps smallint null check (breaker_amps between 1 and 400),
  check ((panel_id is null) = (panel_slot is null)),
  unique (panel_id, panel_slot, breaker_pole) deferrable initially deferred,  -- one sensor per pole
  unique (device_id, channel_no)
)

panel (                                  -- PNL-001
  id uuid pk, site_id uuid fk site, name text not null,
  spaces smallint not null check (spaces between 2 and 84 and spaces % 2 = 0),
  numbering text not null default 'odd_even' check (numbering in ('odd_even','sequential')),
  created_at, updated_at
)

circuit (
  id uuid pk, site_id uuid fk site, name text, kind text check (kind in ('device_merge','virtual')),
  device_merge_mask int null,            -- for kind = device_merge
  device_id uuid null,                   -- for kind = device_merge
  tags text[] default '{}', created_at, updated_at, archived_at
)

circuit_member (
  circuit_id uuid fk circuit, channel_id uuid fk channel,
  sign smallint check (sign in (1,-1)),
  primary key (circuit_id, channel_id)
)

device_event (                           -- config drift, online/offline, errors, clock skew
  id bigserial, device_id uuid, ts timestamptz, kind text, detail jsonb
)

data_gap (
  id bigserial, channel_id uuid, start_ts timestamptz, end_ts timestamptz,
  cause text, resolved bool default false
)
```

Rules:

- A virtual circuit may reference channels from several devices, all in the same site.
- A virtual circuit may reference another circuit only by expanding it into channel members at save time (no nested references, no cycles).
- A channel's panel must be in the same site as its device. Space occupancy and overlap rules (PNL-003, PNL-004) are checked by the API. Pole `k` of a breaker sits on its `k`-th occupied space.

## 3. Time-series schema

### 3.1 `energy_minute` (hypertable, authoritative)

```sql
energy_minute (
  channel_id uuid not null,
  ts timestamptz not null,               -- bucket start
  energy_kwh double precision,           -- import in bucket
  ret_energy_kwh double precision,       -- export in bucket
  voltage_min, voltage_avg, voltage_max double precision,
  current_min, current_avg, current_max double precision,
  power_min, power_avg, power_max double precision,
  ret_power_min, ret_power_avg, ret_power_max double precision,
  quality smallint not null default 0,   -- 0 device, 1 estimated from counters, 2 interpolated
  ingested_at timestamptz not null default now(),
  primary key (channel_id, ts)
)
-- chunk_time_interval 7 days; segmentby channel_id; orderby ts desc
```

Ingest uses `INSERT ... ON CONFLICT (channel_id, ts) DO UPDATE` (COL-004).

### 3.2 `live_sample` (hypertable, short-lived)

```sql
live_sample (
  channel_id uuid, ts timestamptz,
  power_w, current_a, voltage_v, pf double precision,
  day_kwh, week_kwh, month_kwh, year_kwh double precision,
  day_ret_kwh, week_ret_kwh, month_ret_kwh, year_ret_kwh double precision,
  primary key (channel_id, ts)
)
-- chunk_time_interval 1 day
```

### 3.3 `device_status` (hypertable)

`device_id, ts, online, rssi_dbm, uptime_s, unixtime_skew_s, cloud_connected, mqtt_connected`.

## 4. Continuous aggregates

| View | Bucket | From | Contents | Refresh |
|---|---|---|---|---|
| `energy_15m` | 15 min | `energy_minute` | sum import/export kWh, avg/max power, min/max voltage | every 5 min, lag 30 min |
| `energy_hourly` | 1 h | `energy_15m` (hierarchical) | same | every 15 min |
| `energy_daily_utc` | 1 day UTC | `energy_hourly` | same | hourly |

| ID | Pri | Requirement |
|---|---|---|
| DAT-020 | M | Aggregates are per **channel**. Circuit totals join `circuit_member` and apply `sign` at query time. |
| DAT-021 | M | Local-day and billing-cycle totals are computed from `energy_hourly` using the site time zone, never from UTC-day buckets. This avoids DST and offset errors. Sites in time zones with non-hour offsets (for example UTC+5:30) must compute from `energy_15m`. |
| DAT-022 | M | Late or corrected minute data (backfill) triggers a refresh of the affected aggregate window. |
| DAT-023 | M | The 15-minute aggregate is the input for demand charges. |

## 5. Retention and compression (defaults, admin configurable)

| Data | Compress after | Keep |
|---|---|---|
| `live_sample` | 1 day | 7 days |
| `device_status` | 7 days | 90 days |
| `energy_minute` | 7 days | 2 years |
| `energy_15m` | 30 days | 5 years |
| `energy_hourly`, `energy_daily_utc` | 90 days | forever |
| `audit_log` | 30 days | 1 year minimum |

**Sizing estimate** (per device, 12 active channels): about 17,000 minute rows per day, 6.3 million per year, roughly 1 GB per year uncompressed and on the order of 100 MB after compression. Twenty devices for two years stay well under 10 GB.

## 6. Billing and tariff tables

Defined in [05-billing-tariffs.md §8](05-billing-tariffs.md#8-data-model). Summary: `rate_plan`, `rate_plan_version`, `rate_component`, `tou_period`, `tou_schedule_rule`, `holiday_calendar`, `holiday`, `site_rate_assignment`, `billing_cycle`, `bill_estimate`, `bill_line_item`, `actual_bill`.

## 7. Security and ops tables

Defined in [04-rbac-security.md](04-rbac-security.md). Summary: `app_user`, `role`, `permission`, `role_permission`, `user_role_binding`, `api_token`, `session`, `audit_log`.

## 8. Jobs

```sql
job (
  id uuid pk, kind text, payload jsonb, status text,   -- queued, running, succeeded, failed, cancelled
  run_after timestamptz, attempts int, max_attempts int,
  created_by uuid null, created_at, started_at, finished_at, error text, result jsonb
)
job_schedule (id uuid pk, kind text, cron text, payload jsonb, enabled bool, last_run_at, next_run_at)
```

Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED`.
