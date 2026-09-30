"""Cursor pagination over time-ordered UUIDv7 ids (API-003)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import Query
from sqlalchemy import Select

from app.core.errors import ApiError

MAX_LIMIT = 500

LimitQ = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorQ = Annotated[str | None, Query(max_length=64)]


def apply_cursor(stmt: Select[Any], id_column: Any, cursor: str | None, limit: int) -> Select[Any]:
    if cursor:
        try:
            after = uuid.UUID(cursor)
        except ValueError as exc:
            raise ApiError(400, "bad_cursor", "invalid cursor") from exc
        stmt = stmt.where(id_column > after)
    return stmt.order_by(id_column).limit(limit + 1)


def page_meta(items: list[Any], limit: int) -> tuple[list[Any], dict[str, Any]]:
    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None
    return items, {"next_cursor": next_cursor}
