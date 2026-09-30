"""Hypertables, defined with SQLAlchemy Core for bulk upserts (SRD 03 §3)."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, SmallInteger, Table
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

_M = Base.metadata

MINUTE_METRICS = [
    "energy_kwh",
    "ret_energy_kwh",
    "voltage_min",
    "voltage_avg",
    "voltage_max",
    "current_min",
    "current_avg",
    "current_max",
    "power_min",
    "power_avg",
    "power_max",
    "ret_power_min",
    "ret_power_avg",
    "ret_power_max",
]

# Device history key -> column name
HISTORY_KEY_MAP = {
    "energy": "energy_kwh",
    "ret_energy": "ret_energy_kwh",
    "voltage_min": "voltage_min",
    "voltage_avg": "voltage_avg",
    "voltage_max": "voltage_max",
    "current_min": "current_min",
    "current_avg": "current_avg",
    "current_max": "current_max",
    "power_min": "power_min",
    "power_avg": "power_avg",
    "power_max": "power_max",
    "ret_power_min": "ret_power_min",
    "ret_power_avg": "ret_power_avg",
    "ret_power_max": "ret_power_max",
}

QUALITY_DEVICE = 0
QUALITY_ESTIMATED = 1

energy_minute = Table(
    "energy_minute",
    _M,
    Column("channel_id", UUID(as_uuid=True), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    *[Column(name, Float) for name in MINUTE_METRICS],
    Column("quality", SmallInteger, nullable=False, default=QUALITY_DEVICE),
    Column("ingested_at", DateTime(timezone=True)),
)

LIVE_FIELDS = {
    "power": "power_w",
    "current": "current_a",
    "voltage": "voltage_v",
    "pf": "pf",
    "day_energy": "day_kwh",
    "week_energy": "week_kwh",
    "month_energy": "month_kwh",
    "year_energy": "year_kwh",
    "day_ret_energy": "day_ret_kwh",
    "week_ret_energy": "week_ret_kwh",
    "month_ret_energy": "month_ret_kwh",
    "year_ret_energy": "year_ret_kwh",
}

live_sample = Table(
    "live_sample",
    _M,
    Column("channel_id", UUID(as_uuid=True), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    *[Column(name, Float) for name in LIVE_FIELDS.values()],
)

device_status = Table(
    "device_status",
    _M,
    Column("device_id", UUID(as_uuid=True), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("online", Boolean),
    Column("rssi_dbm", Integer),
    Column("uptime_s", Integer),
    Column("clock_skew_s", Integer),
    Column("cloud_connected", Boolean),
    Column("mqtt_connected", Boolean),
)
