"""Readings SQL: per-channel buckets, then signed sums per series (DAT-003, DAT-020, CIR-005)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.readings.plan import SOURCES, QueryPlan, Resolution


@dataclass(frozen=True)
class SeriesMember:
    series: str
    channel_id: uuid.UUID
    sign: int


def _bucket_expr(plan: QueryPlan, ts_col: str) -> str:
    if plan.resolution == Resolution.DAY:
        return f"date_trunc('day', {ts_col}, :tz)"
    if plan.resolution == Resolution.MONTH:
        return f"date_trunc('month', {ts_col}, :tz)"
    return f"time_bucket(make_interval(secs => :bucket_s), {ts_col})"


def build_sql(plan: QueryPlan) -> str:
    table, ts_col = SOURCES[plan.source]
    bucket = _bucket_expr(plan, ts_col)
    return f"""
WITH members AS (
  SELECT * FROM unnest(CAST(:series AS text[]), CAST(:channels AS uuid[]),
                       CAST(:signs AS int[])) AS m(series, channel_id, sign)
),
per_channel AS (
  SELECT src.channel_id, {bucket} AS bucket,
         sum(src.energy_kwh) AS energy_kwh,
         sum(src.ret_energy_kwh) AS ret_energy_kwh,
         avg(src.power_avg) AS power_avg,
         max(src.quality) AS quality
  FROM {table} src
  WHERE src.channel_id = ANY(CAST(:channels AS uuid[]))
    AND src.{ts_col} >= :start AND src.{ts_col} < :end
  GROUP BY src.channel_id, 2
)
SELECT m.series, pc.bucket,
       sum(m.sign * pc.energy_kwh) AS energy_kwh,
       sum(m.sign * pc.ret_energy_kwh) AS ret_energy_kwh,
       sum(m.sign * pc.power_avg) AS power_avg_w,
       max(pc.quality) AS quality
FROM per_channel pc JOIN members m ON m.channel_id = pc.channel_id
GROUP BY m.series, pc.bucket
ORDER BY m.series, pc.bucket
"""  # noqa: S608 - identifiers come from the fixed SOURCES map


async def run(
    session: AsyncSession,
    plan: QueryPlan,
    members: list[SeriesMember],
    start: datetime,
    end: datetime,
    tz: str,
) -> dict[str, list[dict[str, Any]]]:
    params: dict[str, Any] = {
        "series": [m.series for m in members],
        "channels": [m.channel_id for m in members],
        "signs": [m.sign for m in members],
        "start": start,
        "end": end,
    }
    if plan.bucket_seconds is not None:
        params["bucket_s"] = plan.bucket_seconds
    else:
        params["tz"] = tz
    rows = await session.execute(text(build_sql(plan)), params)
    out: dict[str, list[dict[str, Any]]] = {m.series: [] for m in members}
    for row in rows:
        out[row.series].append(
            {
                "ts": row.bucket.isoformat(),
                "energy_kwh": _r(row.energy_kwh, 6),
                "ret_energy_kwh": _r(row.ret_energy_kwh, 6),
                "power_avg_w": _r(row.power_avg_w, 1),
                "quality": "device" if (row.quality or 0) == 0 else "estimated",
            }
        )
    return out


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)
