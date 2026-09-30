"""Single entrypoint for every backend role (ARC-001).

energy-hub api | collector | worker | migrate | sim | healthcheck | gen-key
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import urllib.request

from app.core.config import get_settings
from app.core.logging import configure_logging


def _api(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "app.api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
        access_log=False,
    )


def _collector(_args: argparse.Namespace) -> None:
    from app.collector.main import run

    run()


def _worker(_args: argparse.Namespace) -> None:
    from app.worker.main import run

    run()


def _migrate(_args: argparse.Namespace) -> None:
    """Run Alembic to head. Works from source and from the installed wheel (UPG-001)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import app.db

    config = Config()
    config.set_main_option("script_location", str(Path(app.db.__file__).parent / "migrations"))
    command.upgrade(config, "head")


def _sim(args: argparse.Namespace) -> None:
    import uvicorn

    from app.sim.server import create_sim_app

    uvicorn.run(
        create_sim_app(password=args.password),
        host="0.0.0.0",
        port=args.port,
        log_config=None,
    )


def _healthcheck(args: argparse.Namespace) -> None:
    """Container health probe without curl in the image."""
    try:
        with urllib.request.urlopen(args.url, timeout=3) as response:  # noqa: S310
            sys.exit(0 if response.status == 200 else 1)
    except Exception:
        sys.exit(1)


def _gen_key(_args: argparse.Namespace) -> None:
    print(base64.b64encode(os.urandom(32)).decode())


def main() -> None:
    parser = argparse.ArgumentParser(prog="energy-hub")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("api")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=_api)
    sub.add_parser("collector").set_defaults(fn=_collector)
    sub.add_parser("worker").set_defaults(fn=_worker)
    sub.add_parser("migrate").set_defaults(fn=_migrate)
    p = sub.add_parser("sim", help="run the EM16P device simulator")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--password", default=None)
    p.set_defaults(fn=_sim)
    p = sub.add_parser("healthcheck")
    p.add_argument("--url", default="http://127.0.0.1:8000/healthz")
    p.set_defaults(fn=_healthcheck)
    sub.add_parser("gen-key", help="print a random base64 32-byte key").set_defaults(fn=_gen_key)

    args = parser.parse_args()
    if args.cmd not in ("healthcheck", "gen-key"):
        configure_logging(get_settings().log_level)
    args.fn(args)


if __name__ == "__main__":
    main()
