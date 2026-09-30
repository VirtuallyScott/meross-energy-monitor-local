"""Application settings.

Secrets are read from files (Docker secrets) via the ``*_FILE`` variables, falling back to the
plain variable for local development. See SWM-003.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(name: str) -> str | None:
    """Return the secret from ``<NAME>_FILE`` if set, otherwise ``<NAME>``."""
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    return os.environ.get(name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EHUB_", extra="ignore")

    env: str = "production"
    log_level: str = "INFO"
    base_url: str = "https://localhost"

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "energy"
    db_user: str = "energy"
    db_pool_size: int = 10

    # Session and cookie behaviour (AUTH-005)
    session_idle_hours: int = 12
    session_absolute_days: int = 7
    cookie_secure: bool = True

    # Collector behaviour (COL-*)
    collector_refresh_s: float = 30.0
    backfill_interval_s: float = 300.0
    config_sync_interval_s: float = 900.0
    poll_fallback_s: float = 15.0
    history_page_gap_s: float = 0.2
    initial_backfill_hours: int = 48
    device_timeout_s: float = 8.0

    # Extra CIDRs allowed for device addresses, in addition to private ranges (SEC-040)
    device_allowed_cidrs: list[str] = Field(default_factory=list)
    # CIDRs never allowed for devices, such as the stack's overlay networks (SEC-040)
    device_blocked_cidrs: list[str] = Field(default_factory=list)

    @property
    def db_password(self) -> str:
        value = _read_secret("EHUB_DB_PASSWORD")
        if not value:
            raise RuntimeError("EHUB_DB_PASSWORD or EHUB_DB_PASSWORD_FILE must be set")
        return value

    @property
    def device_cred_key(self) -> bytes:
        """32-byte AES key, stored base64-encoded (SEC-020)."""
        value = _read_secret("EHUB_DEVICE_CRED_KEY")
        if not value:
            raise RuntimeError("EHUB_DEVICE_CRED_KEY or EHUB_DEVICE_CRED_KEY_FILE must be set")
        key = base64.b64decode(value)
        if len(key) != 32:
            raise RuntimeError("EHUB_DEVICE_CRED_KEY must decode to 32 bytes")
        return key

    @property
    def setup_token(self) -> str | None:
        return _read_secret("EHUB_SETUP_TOKEN")

    def database_url(self, driver: str = "postgresql+asyncpg") -> str:
        from sqlalchemy.engine import URL

        return URL.create(
            driver,
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
