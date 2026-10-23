# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Energy Hub: a self-hosted, cloud-free hub for Meross / Refoss EM16P (and EM06P) energy monitors.
Python backend (FastAPI + SQLAlchemy async + PostgreSQL/TimescaleDB), React + TypeScript + Vite web
UI, deployed as a Docker Swarm stack behind Traefik.

Requirements are in `Docs/SRD/` and code comments cite their IDs (e.g. `COL-015`, `SEC-040`,
`PNL-010`, `RBAC-001`). Look up the ID in the SRD before changing behaviour it governs. The device
protocol is reverse-engineered and documented in `Docs/Reverse_API/`. `TODO.md` is the working list
of open and done items, also keyed by SRD ID.

## Commands

```sh
make up-sim          # dev stack + EM16P simulator; https://localhost:8443, add device "sim:8080"
make test            # full CI checks: Dockerfile `test` stages for backend and web
make lint            # fast local lint/format/type check without Docker (needs .venv and web/node_modules)
make logs            # follow api + collector logs
make down            # stop dev stack, keep volumes
```

CI (`.github/workflows/ci.yml`) runs exactly the Dockerfile `test` targets, so `make test` is the
source of truth. Backend test stage: `ruff check`, `ruff format --check`, `mypy app` (strict),
`pytest --cov=app`. Web test stage: `eslint`, `prettier --check`, `tsc --noEmit`, `vitest run`.

Local without Docker (from `backend/`, venv at repo root `.venv`):

```sh
../.venv/bin/pytest                                   # all backend tests
../.venv/bin/pytest tests/test_panel_layout.py -k overlap   # single test
../.venv/bin/ruff check app tests && ../.venv/bin/mypy app
```

Web (from `web/`): `npm run dev` (proxies `/api` to localhost:8000), `npx vitest run src/features/panels/layout.test.ts`,
`npm run lint`, `npm run typecheck`, `npm run format`.

Backend tests need no database: `tests/conftest.py` sets dummy `EHUB_DB_PASSWORD` and
`EHUB_DEVICE_CRED_KEY`. There is no DB integration harness yet, so logic that must be tested is kept
in pure modules (e.g. `readings/plan.py`, `panels/layout.py`).

## Architecture

**One backend image, several roles.** `backend/app/cli.py` (`energy-hub <cmd>`) is the single
entrypoint: `api`, `collector`, `worker`, `migrate`, `sim`, `healthcheck`, `gen-key`. Compose and
the Swarm stack run the same image with different commands. After backend edits, rebuild the image;
running containers do not pick up source changes.

**Data flow.**
1. `collector/main.py` supervises one `DeviceRunner` per enabled device. Each runner holds a
   Postgres advisory lock (`lock_key(device_id)`), so multiple collector replicas never double-poll
   a device.
2. The runner uses `devices/rpc.py` `DeviceClient`: WebSocket live notifications with HTTP polling
   fallback, periodic minute-history backfill (48 h initial) and config sync. Gaps are recorded.
3. `collector/ingest.py` writes `live_sample`, `device_status`, `energy_minute` hypertables
   (`db/timeseries.py`, SQLAlchemy Core for bulk upserts) and fires `pg_notify('ehub_live', device_id)`.
4. The API's `api/livehub.py` holds one LISTEN connection per process and fans out to SSE clients
   (`routers/live.py`).
5. `readings/plan.py` picks resolution and source (raw minutes vs TimescaleDB continuous
   aggregates defined in migration `0001_initial`); `readings/query.py` runs it.

**Device safety.** Every RPC method is checked against `devices/allowlist.py` before sending;
destructive methods (factory reset, history delete, firmware, Wi-Fi, cloud) are blocked.
`devices/netguard.py` restricts device addresses to private ranges (SSRF guard) with
`EHUB_DEVICE_ALLOWED_CIDRS` / `EHUB_DEVICE_BLOCKED_CIDRS` overrides. Device passwords are
AES-encrypted with `device_cred_key` (`devices/credentials.py`). Do not loosen these.

**Auth / RBAC.** Every route must declare access via `app.auth.deps` (`require(P.X)`, `public`,
or `authenticated`); `tests/test_routes.py` fails on any undeclared route and pins the exact set of
public routes. New routers must be added to `ROUTERS` in `api/main.py`. Permissions and built-in
roles are in `auth/permissions.py`; site-scoped checks use `ensure_site`. Sessions use cookies with
CSRF (`ehub_csrf` cookie echoed in a header by `web/src/lib/api.ts`).

**API shape.** All responses use an envelope `{data, error, meta}` under `/api/v1`; errors go
through `core/errors.ApiError`.

**Config.** `core/config.py` `Settings` reads `EHUB_*` env vars. Secrets come from `*_FILE`
(Docker secrets) with plain-env fallback. Secrets are generated into `deploy/secrets/` by
`scripts/gen-secrets.sh`.

**Worker.** `worker/main.py` is a `FOR UPDATE SKIP LOCKED` job queue; register handlers with
`@handler("kind")`. Billing and export jobs are planned to land here.

**Simulator.** `app/sim/` is an EM16P emulator used for dev (`sim:8080`) and client tests.

**Migrations.** Alembic, in `backend/app/db/migrations/versions/` with numbered names
(`0004_show_used_channels.py`). Run via the `migrate` role, which starts before api/collector/worker.

**Web.** `web/src/features/<area>/` holds pages, CSS and pure helpers with colocated `*.test.ts`;
`lib/` has the API client, TanStack Query hooks (`queries.ts`), types and `useLive.ts` (SSE).
Design tokens are in `styles/tokens.css`. URL query params carry view state (e.g. `?show=amps`).

## Conventions

- Python: ruff line length 100, mypy strict, Python 3.13 in images (3.12 minimum).
- Commits: conventional (`feat:`, `fix:`, ...).
- Update `TODO.md` checkboxes when finishing listed items.
