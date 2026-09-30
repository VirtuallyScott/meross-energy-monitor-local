# SRD 00 — Overview

**Product:** Local Energy Monitor Hub (working name)
**Status:** Draft v0.1 for review, 2026-09-29
**Audience:** Developers and reviewers who will build and accept the system.

## 1. Purpose

A self-hosted web application, deployed as a Docker Swarm stack on the home or small-site LAN, that:

1. Registers and manages **multiple** Meross / Refoss EM16P (and sibling EM06P) smart energy monitors by IP or URL, with an optional device password.
2. Collects live and per-minute energy data from each device over the local RPC API, with no cloud dependency.
3. Stores configuration and time-series data in **PostgreSQL with the TimescaleDB extension**.
4. Shows live and historical dashboards per device, per channel and per user-defined circuit.
5. **Estimates the electricity bill** from measured kWh using rate plans ranging from a simple flat rate to time-of-use, tiered, demand and net-metering tariffs.
6. **Exports** raw and aggregated data plus bill estimates.
7. Controls access with a role-based access control (RBAC) model.

## 2. Document set

| Doc | Title | Contents |
|---|---|---|
| [00](00-overview.md) | Overview | Scope, glossary, assumptions, decisions, open questions |
| [01](01-functional-requirements.md) | Functional requirements | Devices, collection, circuits, dashboards, alerts |
| [02](02-architecture-deployment.md) | Architecture and deployment | Services, Swarm stack, networking, secrets, backups |
| [03](03-data-model.md) | Data model | Config schema, hypertables, aggregates, retention |
| [04](04-rbac-security.md) | RBAC and security | Roles, permission matrix, auth, secrets handling, audit |
| [05](05-billing-tariffs.md) | Billing and tariffs | Rate plan model and calculation rules |
| [06](06-api-export.md) | API and export | REST API conventions, export formats and jobs |
| [07](07-nfr-testing-acceptance.md) | Non-functional, testing, acceptance | Performance, reliability, test strategy, release criteria |

Device protocol reference: [../Reverse_API/](../Reverse_API/). The SRDs cite it rather than repeat it.

## 3. Requirement conventions

- IDs are `<AREA>-<NNN>`, for example `DEV-001`. IDs are never reused.
- Priority uses MoSCoW: **M** must, **S** should, **C** could, **W** won't (this release).
- "The system" means the whole stack. "The collector" means the device-polling service.
- Anything that depends on unverified device behavior is marked **[UNVERIFIED-API]** and must be confirmed against a real device before implementation is considered done.

## 4. Scope

### In scope (v1)

- Multiple EM16P devices on one LAN, single installation, one or more **sites** (a site is a billing location, for example "Main house" and "Guest cottage").
- Live data over WebSocket, authoritative per-minute history via `Em.Data.Get`, gap backfill.
- Device config read, and a narrow allow-list of writes (channel names, CT factor, merged circuits).
- User-defined virtual circuits, including across devices and with subtraction.
- Rate plans: flat, tiered, time-of-use, seasonal, demand charges, fixed charges, taxes, net metering and net billing.
- Bill estimate, month-to-date projection, plan comparison, reconciliation against actual bills.
- CSV, JSON and XLSX export. Scheduled exports.
- Local user accounts, RBAC, API tokens, audit log.
- Swarm deployment on one or more nodes, with TLS at the edge.

### Out of scope (v1)

- Meross or Refoss cloud integration.
- Controlling loads (these devices do not switch loads).
- Firmware upgrades, factory reset and on-device history deletion. The system must never issue `Refoss.Factory.Reset` or `Em.Data.Del` (see SEC-030).
- Access from the public internet. The design assumes LAN or VPN only.
- Multi-tenant hosting for unrelated customers.
- Mobile native apps. The web UI must be responsive instead.

## 5. Glossary

| Term | Meaning |
|---|---|
| Device | One physical energy monitor, identified by its `dev_id` (for example `meross-em16p-c4e7ae2545ab`) |
| Channel | One CT input on a device, `em:1` to `em:18` |
| Device merge | A merged circuit stored on the device (`Em.Chmerge.*`), identified by a channel bitmask |
| Virtual circuit | A circuit defined in this system as a signed sum of channels, possibly across devices |
| Channel role | What a channel measures: `grid_main`, `solar`, `battery`, `branch`, `unused` |
| Panel | An electrical panel (load center) at a site: the main panel or a subpanel, with a fixed number of breaker spaces |
| Panel space | One numbered breaker position in a panel. A breaker occupies one space per pole |
| Double-pole breaker | A breaker taking two spaces on the same side of the panel, feeding a 240 V branch circuit |
| Site | A billing location with a time zone, a set of devices and an assigned rate plan |
| Minute bucket | One row from `Em.Data.Get`: 60 s of energy, min/avg/max V, A and W |
| Live sample | One `NotifyStatus` channel snapshot, every ~15 to 20 s |
| Import / export | Energy drawn from the grid / sent to the grid (`energy` / `ret_energy`) |
| Rate plan | A versioned tariff definition used to price energy |
| Billing cycle | The utility's period between meter reads; not always a calendar month |
| TOU | Time of use: price varies by time of day, weekday and season |
| NEM | Net energy metering: exports offset imports |

## 6. Key assumptions

| # | Assumption | Impact if wrong |
|---|---|---|
| A1 | Devices and the Swarm nodes share a routed LAN; nodes can open TCP 80 to each device | Collector cannot reach devices; needs VLAN or firewall change |
| A2 | Device minute history retention is at least 24 h. Verified 2026-09-29: about 35 h of history available (everything since install) and it survived a device reboot. Upper limit still unknown | Longer outages lose minute data; system falls back to counter deltas (COL-014) |
| A3 | Mains CTs measure grid import and export, with `ret_energy` populated when exporting | Net metering needs a different data source |
| A4 | Users are household members or a small team, under 25 accounts | RBAC and session design sized for this |
| A5 | Under 20 devices per installation | Collector and storage sizing |
| A6 | Utility rate plans are entered by a user, not downloaded | An import from OpenEI URDB is a Could (BIL-060) |

## 7. Proposed technical decisions

These are recommendations. They become fixed once this SRD is approved.

| Area | Proposal | Reason |
|---|---|---|
| Database | PostgreSQL 16+ with TimescaleDB 2.x, one instance | User direction. Hypertables, compression and continuous aggregates cover the time-series needs |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic | Integration guide client is Python; async WebSocket support is mature |
| Collector | Separate Python asyncio service, same code base and image | Isolates device I/O from web traffic |
| Jobs | Worker service using a Postgres-backed queue (`SELECT ... FOR UPDATE SKIP LOCKED`) | Avoids adding Redis; one fewer stateful service |
| Frontend | React + TypeScript + Vite, served by nginx | Mainstream; good charting options |
| Edge | Traefik v3 as reverse proxy with TLS | Native Swarm service discovery |
| Charts | Apache ECharts | Handles large time series and heatmaps |

## 8. Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Confirm backend language/framework in section 7 | Product owner | Before sprint 1 |
| Q2 | Actual utility tariff(s) to use as first test fixtures | Product owner | Billing sprint |
| Q3 | Is any site on net metering today, and which variant (1:1 NEM, net billing, true-up)? | Product owner | Billing sprint |
| Q4 | Device minute-history upper limit. Partly answered 2026-09-29: history reaches back to install (~35 h) and survives reboot. Re-test after one week and one month | Dev | Collector sprint |
| Q5 | `Refoss.Auth.Set` params and digest flow with auth on | Dev with device | Device auth story |
| Q6 | Single-node Swarm or multi-node? Affects volume placement | Product owner | Deployment sprint |
| Q7 | Need for SSO (OIDC) in v1, or local accounts only | Product owner | Auth sprint |
