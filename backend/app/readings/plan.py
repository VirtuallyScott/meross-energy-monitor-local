"""Choose resolution and source table for a readings query (API spec §2.1, DAT-021).

Pure functions so the rules are unit-testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class Resolution(StrEnum):
    AUTO = "auto"
    MINUTE = "minute"
    M15 = "15m"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


BUCKET_SECONDS = {
    Resolution.MINUTE: 60,
    Resolution.M15: 900,
    Resolution.HOUR: 3600,
}

MAX_RANGE = {
    Resolution.MINUTE: timedelta(days=7),
    Resolution.M15: timedelta(days=400),
}

# Raw minute data answers any query this recent, including the not-yet-materialized tail.
RAW_SOURCE_LIMIT = timedelta(days=7)
TARGET_POINTS = 2000


class RangeError(ValueError):
    pass


@dataclass(frozen=True)
class QueryPlan:
    resolution: Resolution
    source: str  # one of SOURCES keys
    bucket_seconds: int | None  # None for calendar buckets (day, month)


# Fixed identifiers only; never built from user input (SEC-044).
SOURCES = {
    "minute": ("energy_minute", "ts"),
    "15m": ("energy_15m", "bucket"),
    "hour": ("energy_hourly", "bucket"),
}


def pick_auto(span: timedelta) -> Resolution:
    for resolution in (Resolution.MINUTE, Resolution.M15, Resolution.HOUR):
        if span.total_seconds() / BUCKET_SECONDS[resolution] <= TARGET_POINTS:
            return resolution
    return Resolution.DAY if span <= timedelta(days=TARGET_POINTS) else Resolution.MONTH


def plan_query(start: datetime, end: datetime, resolution: Resolution) -> QueryPlan:
    if start.tzinfo is None or end.tzinfo is None:
        raise RangeError("timestamps must include a UTC offset")
    if end <= start:
        raise RangeError("'to' must be after 'from'")
    span = end - start
    if resolution == Resolution.AUTO:
        resolution = pick_auto(span)
    limit = MAX_RANGE.get(resolution)
    if limit is not None and span > limit:
        raise RangeError(
            f"range too long for {resolution.value} resolution (max {limit.days} days)"
        )
    if span <= RAW_SOURCE_LIMIT:
        source = "minute"
    elif resolution == Resolution.M15:
        source = "15m"
    else:
        source = "hour"
    return QueryPlan(resolution, source, BUCKET_SECONDS.get(resolution))
