"""Liveness, readiness and version (ARC-005, UPG-003)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.auth.deps import SessionDep, public
from app.core.errors import envelope

router = APIRouter(dependencies=[Depends(public)], tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
async def readyz(session: SessionDep) -> dict[str, Any] | JSONResponse:
    try:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        return JSONResponse({"status": "not_ready", "reason": "database"}, status_code=503)
    return {"status": "ready", "schema": revision}


@router.get("/api/v1/system/version")
async def version(session: SessionDep) -> dict[str, Any]:
    try:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        revision = None
    return envelope({"app": __version__, "schema": revision})
