"""First-run setup token (AUTH-003)."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.auth import service, tokens
from app.core.config import get_settings
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)


async def ensure_setup_token(app: FastAPI) -> None:
    """Use the configured setup token, or generate one and log it once if no users exist."""
    app.state.setup_token = get_settings().setup_token
    if app.state.setup_token:
        return
    try:
        async with get_sessionmaker()() as session:
            users = await service.count_users(session)
    except Exception:  # database not ready yet; readiness probe will report it
        log.warning("could not check for first-run setup; database unavailable")
        return
    if users == 0:
        app.state.setup_token = tokens.new_secret(18)
        log.warning(
            "No users exist. Complete first-run setup in the web UI with this one-time token.",
            extra={"ctx": {"setup_token_value": app.state.setup_token}},
        )
