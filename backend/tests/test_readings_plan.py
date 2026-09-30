"""Readings resolution rules (API spec §2.1)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.readings.plan import RangeError, Resolution, plan_query

T0 = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("span", "resolution", "source"),
    [
        (timedelta(hours=6), Resolution.MINUTE, "minute"),
        (timedelta(days=7), Resolution.M15, "minute"),
        (timedelta(days=20), Resolution.M15, "15m"),
        (timedelta(days=60), Resolution.HOUR, "hour"),
        (timedelta(days=400), Resolution.DAY, "hour"),
    ],
)
def test_auto(span, resolution, source):
    plan = plan_query(T0, T0 + span, Resolution.AUTO)
    assert (plan.resolution, plan.source) == (resolution, source)


def test_limits():
    with pytest.raises(RangeError):
        plan_query(T0, T0 + timedelta(days=8), Resolution.MINUTE)
    with pytest.raises(RangeError):
        plan_query(T0, T0 + timedelta(days=401), Resolution.M15)
    with pytest.raises(RangeError):
        plan_query(T0, T0, Resolution.HOUR)
    with pytest.raises(RangeError):
        plan_query(T0.replace(tzinfo=None), T0.replace(tzinfo=None) + timedelta(1), Resolution.DAY)


def test_calendar_buckets_have_no_fixed_width():
    assert plan_query(T0, T0 + timedelta(days=31), Resolution.DAY).bucket_seconds is None
