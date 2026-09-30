# Energy Hub

Self-hosted web app for monitoring Meross / Refoss EM16P smart energy monitors on your local
network. It collects live and per-minute data from each device, stores it in PostgreSQL with
TimescaleDB, and runs as a Docker Swarm stack. No cloud account is involved.

Requirements live in [Docs/SRD](Docs/SRD/README.md). The device protocol is documented in
[Docs/Reverse_API](Docs/Reverse_API/).

## Hardware

Built and tested against this monitor:
[Refoss / Meross EM16P energy monitor on Amazon](https://www.amazon.com/gp/product/B0FSZYR7V4).
This is **not** an affiliate link. Meross and Refoss are the same company, so the device may
be sold under either brand.

## What works today

| Area | Status |
|---|---|
| Device registry: add by IP or URL, probe, optional encrypted password, test, sync | Done |
| Collector: WebSocket live feed, polling fallback, 48 h minute-history backfill, gap records | Done |
| Channels and circuits: roles, device merges mirrored, virtual circuits with +/- members | Done |
| Readings API: minute, 15 min, hour, local day and month buckets | Done |
| Live overview (Server-Sent Events), history chart, device pages | Done |
| Auth: first-run setup, sessions, CSRF, API tokens, RBAC with site scoping, audit log | Done |
| Deployment: multi-stage images, dev compose with simulator, Swarm stack, Traefik TLS, backups | Done |
| Bill estimation (flat, TOU, tiers, net metering) | Next phase |
| Export (CSV, JSON, XLSX) and alerts | Next phase |

## Quick start (development)

Needs Docker with Compose.

```sh
make up-sim          # generates secrets, builds images, starts the stack and the simulator
cat deploy/secrets/setup_token
open https://localhost:8443
```

The certificate is self-signed. Complete setup with the token, then add a device. Use
`sim:8080` for the built-in simulator or your monitor's IP address, for example `192.168.2.75`.

### Signing in

There are **no default credentials**. On a new database, the web UI opens a first-run setup
page. That page creates the first administrator account, with a username and password you
choose, and the first site.

1. Get the one-time setup token. It is the `setup_token` secret, which is in
   `deploy/secrets/setup_token` for the dev stack. If no token secret is configured, the API
   generates one and prints it once in its log. Look for `setup_token_value` in
   `docker compose logs api`.
2. Open the web UI and enter the token, an admin username and a password. The password needs
   at least 12 characters, and common passwords are rejected.
3. Sign in with the account you just created. The setup page and its token stop working once
   the first user exists.

Administrators can create more users and assign roles from the API (`/api/v1/users`). There
is no password-reset command yet. If the only admin password is lost on a dev stack, the
fix is to start over with an empty database, which deletes all data:

```sh
docker compose --profile sim down -v   # removes the database volume
make up-sim
```

Useful commands:

```sh
make test            # backend and web lint, type checks and tests, in containers
make logs            # follow api and collector logs
make backup          # take a database backup now
make down            # stop (data volume kept)
```

### Working on the code without Docker

```sh
python3 -m venv .venv && .venv/bin/pip install uv
cd backend && ../.venv/bin/uv pip install --python ../.venv/bin/python -e '.[dev]'
../.venv/bin/pytest

cd ../web && npm install && npm run dev   # proxies /api to localhost:8000
```

## Production on Docker Swarm

```sh
docker swarm init
docker node update --label-add energy.db=true  <node>   # where the database volume lives
docker node update --label-add energy.lan=true <node>   # a node that can reach the devices
make images                                             # or: make images-push REGISTRY=...
make stack-deploy
```

Traefik publishes ports 80 and 443. To use your own certificate, copy
`deploy/traefik/tls.example.yml` to `deploy/traefik/dynamic/tls.yml` and add `tls_cert` and
`tls_key` secrets.

**Back up `deploy/secrets/device_cred_key` separately.** Database backups contain device
passwords encrypted with that key, and they cannot be decrypted without it.

## Layout

```
backend/   Python 3.13: FastAPI API, collector, worker, simulator (one image, several commands)
web/       React + TypeScript + Vite single-page app, served by nginx
deploy/    Swarm stack, Traefik config
scripts/   Secret generation, Swarm secrets, backup
Docs/      Requirements (SRD) and device API notes
```

## Device safety

The app only sends read methods and a small set of configuration writes to devices. Factory
reset, history delete, firmware, Wi-Fi and cloud methods are blocked in code (see
`backend/app/devices/allowlist.py`). Device addresses must be on a private network.
