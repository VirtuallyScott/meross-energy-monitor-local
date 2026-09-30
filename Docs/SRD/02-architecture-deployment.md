# SRD 02 — Architecture and Deployment

## 1. Context

```
   Browser (LAN / VPN)
         │ HTTPS 443
         ▼
 ┌───────────────────────────── Docker Swarm stack: energy ─────────────────────────────┐
 │                                                                                       │
 │  traefik ──► web (nginx, static SPA)                                                  │
 │     │                                                                                 │
 │     └──────► api (FastAPI) ──────────────┐                                            │
 │                 ▲  SSE live feed          │ SQL                                        │
 │                 │ LISTEN/NOTIFY           ▼                                            │
 │  collector ─────┴──────────────────► db (PostgreSQL + TimescaleDB)  ◄── backup (cron) │
 │     │                                     ▲                                            │
 │  worker (jobs: billing, exports, alerts, aggregates) ─┘                               │
 └─────┼─────────────────────────────────────────────────────────────────────────────────┘
       │ HTTP + WS, TCP 80
       ▼
  EM16P #1   EM16P #2   EM06P #3 ...   (IoT VLAN)
```

## 2. Services

| Service | Image | Replicas | Role | Stateful |
|---|---|---|---|---|
| `traefik` | `traefik:v3` | 1 | TLS termination, routing, security headers, rate limits | cert volume |
| `web` | app `web` image (nginx) | 1–2 | Serves the built SPA | no |
| `api` | app `backend` image, cmd `api` | 1–2 | REST API, auth, SSE live feed | no |
| `collector` | app `backend` image, cmd `collector` | 1 | Device connections, ingest, backfill, config sync | no (state in DB) |
| `worker` | app `backend` image, cmd `worker` | 1 | Job queue: exports, bill runs, alert evaluation, maintenance | no |
| `db` | `timescale/timescaledb:2.x-pg16` (pin exact tag) | 1 | Config and time-series storage | **yes** |
| `backup` | app `backend` image or `postgres` client image, cmd `backup` | 1 | Scheduled `pg_dump`, retention pruning | backup volume |
| `migrate` | app `backend` image, cmd `migrate` | 0 (one-shot) | Alembic migrations run before rollout | no |

| ID | Pri | Requirement |
|---|---|---|
| ARC-001 | M | Backend services share one image with different entrypoint commands. |
| ARC-002 | M | All inter-service traffic stays on an internal overlay network. Only Traefik publishes ports (80 redirect, 443). |
| ARC-003 | M | The collector pushes live samples to the API through Postgres `LISTEN/NOTIFY` (payload is a device id and timestamp; data read from the DB). No extra broker. |
| ARC-004 | M | The API is stateless. Sessions are stored in Postgres so any API replica can serve any request. |
| ARC-005 | M | Every service has a health check. The API exposes `/healthz` (liveness) and `/readyz` (DB reachable, migrations current). |
| ARC-006 | S | Every backend service exposes Prometheus metrics on an internal port, not routed through Traefik. |
| ARC-007 | M | Structured JSON logs to stdout, with request id, user id and device id where relevant. No secrets or device passwords in logs. |

## 3. Swarm specifics

| ID | Pri | Requirement |
|---|---|---|
| SWM-001 | M | Deployable with `docker stack deploy -c stack.yml energy` on a single-node Swarm. |
| SWM-002 | M | `db` is pinned to one node with a placement constraint (`node.labels.energy.db == true`) and a local named volume. Swarm does not move stateful data between nodes. |
| SWM-003 | M | Secrets are Docker secrets, mounted as files and read via `*_FILE` env vars: `db_password`, `app_secret_key`, `device_cred_key`, `smtp_password`. None in the stack file, image or env. |
| SWM-004 | M | Non-secret config is Docker configs or env vars: time zone default, log level, base URL, retention settings. |
| SWM-005 | M | `collector` runs with `replicas: 1` and `update_config.order: stop-first`. Advisory locks (COL-015) are the safety net. |
| SWM-006 | M | `api` and `web` use `update_config.order: start-first` with health checks, for zero-downtime updates. `failure_action: rollback`. |
| SWM-007 | M | Resource limits set on every service. Starting point: db 2 GB, api 512 MB, collector 256 MB, worker 512 MB. |
| SWM-008 | S | Multi-node support: stateless services may run on any node. The collector must run on a node with a route to the device VLAN (`node.labels.energy.lan == true`). |
| SWM-009 | M | The collector reaches devices through normal egress from the overlay network. No host networking. mDNS discovery is therefore out of scope; devices are added by address. |
| SWM-010 | S | A `docker-compose.dev.yml` runs the same services for local development without Swarm, with a device simulator (TST-010). |
| SWM-011 | M | Images are multi-arch (amd64, arm64) so the stack runs on a Raspberry Pi 5 or small x86 server. |
| SWM-012 | M | Images run as non-root, read-only root filesystem where possible, with no unnecessary Linux capabilities. |

## 4. Networking and TLS

| ID | Pri | Requirement |
|---|---|---|
| NET-001 | M | HTTPS only for the UI and API. HTTP on port 80 redirects to 443. |
| NET-002 | M | TLS certificate options: (a) user-provided cert and key as Docker secrets, (b) self-signed generated on first start, (c) ACME DNS-01 for users with a domain. (a) and (b) are Must, (c) is Should. |
| NET-003 | M | Traefik adds HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY` and a Content Security Policy (see SEC-050). |
| NET-004 | S | Recommended deployment puts devices on an IoT VLAN with firewall rules allowing only the collector node to reach device TCP 80. Documented in the install guide. |
| NET-005 | M | The application makes no outbound internet calls by default. Any that are added (ACME, rate import, SMTP) are opt-in settings. |

## 5. Backup and restore

| ID | Pri | Requirement |
|---|---|---|
| BAK-001 | M | Nightly `pg_dump` in custom format to a backup volume, keeping 7 daily and 4 weekly copies by default. |
| BAK-002 | M | A documented, tested restore procedure into a fresh stack. Restore is part of release testing (TST-030). |
| BAK-003 | S | Backup target volume can be an NFS or SMB mount so copies leave the host. |
| BAK-004 | S | The backup includes the encrypted device credentials. The `device_cred_key` secret is **not** in the backup and must be backed up separately; the install guide says so plainly. |
| BAK-005 | C | Continuous WAL archiving for point-in-time recovery. |

## 6. Upgrades and migrations

| ID | Pri | Requirement |
|---|---|---|
| UPG-001 | M | Schema changes via Alembic only. The `migrate` one-shot task runs before new API/collector versions start. |
| UPG-002 | M | Migrations are forward-only in production and must be tested against a copy of a populated database. |
| UPG-003 | M | Semantic versioning. The UI footer and `/api/v1/system/version` show app and schema version. |
| UPG-004 | S | TimescaleDB extension upgrades are documented separately (`ALTER EXTENSION timescaledb UPDATE`). |

## 7. Repository layout (proposed)

```
backend/
  app/
    api/          # FastAPI routers by feature
    auth/         # sessions, tokens, RBAC
    devices/      # device registry, config sync
    collector/    # WS client, backfill, ingest
    circuits/
    billing/      # tariff engine (pure functions)
    export/
    alerts/
    jobs/         # queue and worker
    db/           # models, migrations
  tests/
web/
  src/
    features/     # overview, live, history, devices, billing, admin
    components/
deploy/
  stack.yml
  docker-compose.dev.yml
  traefik/
tools/
  device-sim/     # EM16P simulator for tests
Docs/
```
