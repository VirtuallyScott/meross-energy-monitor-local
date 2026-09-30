"""API error type and the response envelope (API-002)."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """An error that maps to a JSON error envelope with a stable ``code``."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str = "resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta or {}}
