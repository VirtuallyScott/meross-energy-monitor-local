"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import bootstrap
from app.api.routers import (
    auth,
    circuits,
    devices,
    health,
    live,
    readings,
    setup,
    sites,
    tokens,
    users,
)
from app.core.errors import ApiError
from app.core.logging import request_id_var

log = logging.getLogger(__name__)
API_PREFIX = "/api/v1"
# (router, prefix). Also used by the RBAC-001 route coverage test.
ROUTERS = [
    (health.router, ""),
    *[
        (m.router, API_PREFIX)
        for m in (setup, auth, tokens, users, sites, devices, circuits, readings, live)
    ],
]


def _error(status: int, code: str, message: str, request_id: str | None) -> JSONResponse:
    body = {"data": None, "error": {"code": code, "message": message, "request_id": request_id}}
    return JSONResponse(body, status_code=status)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await bootstrap.ensure_setup_token(app)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Energy Hub API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid[:64])
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid[:64]
        response.headers.setdefault("cache-control", "no-store")
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, request_id_var.get())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid input')}" if where else "invalid input"
        return _error(422, "validation_error", message, request_id_var.get())

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "http_error", str(exc.detail), request_id_var.get())

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return _error(500, "internal_error", "internal error", request_id_var.get())

    for router, prefix in ROUTERS:
        app.include_router(router, prefix=prefix)
    return app
