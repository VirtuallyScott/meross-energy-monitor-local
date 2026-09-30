"""Breaker planning with one sensor per pole (PNL-002 to PNL-004, PNL-007), no database."""

import uuid
from typing import Any

import pytest

from app.core.errors import ApiError
from app.db.models import Channel, Panel
from app.panels.service import Leg, check_reshape, clear_breaker, plan_breaker, set_breaker

SITE = uuid.uuid4()


def _panel(spaces: int = 40, numbering: str = "odd_even") -> Panel:
    return Panel(id=uuid.uuid4(), site_id=SITE, name="Main", spaces=spaces, numbering=numbering)


def _channel(
    panel: Panel | None = None, slot: int | None = None, poles: int = 1, pole: int = 1
) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        channel_no=1,
        panel_id=panel.id if panel else None,
        panel_slot=slot,
        breaker_poles=poles if panel else None,
        breaker_pole=pole if panel else None,
    )


def _sites(*channels: Channel, site: uuid.UUID = SITE) -> dict[uuid.UUID, uuid.UUID]:
    return {c.id: site for c in channels}


def test_pnl_002_double_pole_with_a_sensor_on_each_leg():
    panel, a2, b2 = _panel(), _channel(), _channel()
    legs = [Leg(1, a2.id), Leg(2, b2.id)]
    assert plan_breaker(panel, 1, 2, legs, _sites(a2, b2), []) == []


def test_pnl_002_double_pole_with_one_sensor_is_allowed():
    panel, a2 = _panel(), _channel()
    assert plan_breaker(panel, 1, 2, [Leg(2, a2.id)], _sites(a2), []) == []


def test_pnl_002_needs_at_least_one_sensor():
    with pytest.raises(ApiError) as err:
        plan_breaker(_panel(), 1, 2, [], {}, [])
    assert err.value.code == "no_sensor"


def test_pnl_002_pole_beyond_breaker_is_rejected():
    panel, a2 = _panel(), _channel()
    with pytest.raises(ApiError) as err:
        plan_breaker(panel, 1, 1, [Leg(2, a2.id)], _sites(a2), [])
    assert err.value.code == "invalid_leg"


def test_pnl_004_two_sensors_on_one_pole_are_rejected():
    panel, a2, b2 = _panel(), _channel(), _channel()
    with pytest.raises(ApiError) as err:
        plan_breaker(panel, 1, 2, [Leg(1, a2.id), Leg(1, b2.id)], _sites(a2, b2), [])
    assert err.value.code == "invalid_leg"


def test_pnl_004_one_sensor_on_two_poles_is_rejected():
    panel, a2 = _panel(), _channel()
    with pytest.raises(ApiError) as err:
        plan_breaker(panel, 1, 2, [Leg(1, a2.id), Leg(2, a2.id)], _sites(a2), [])
    assert err.value.code == "invalid_leg"


def test_pnl_002_sensor_from_other_site_is_rejected():
    panel, a2 = _panel(), _channel()
    with pytest.raises(ApiError) as err:
        plan_breaker(panel, 1, 1, [Leg(1, a2.id)], _sites(a2, site=uuid.uuid4()), [])
    assert err.value.code == "invalid_member"


def test_pnl_002_unknown_sensor_is_rejected():
    with pytest.raises(ApiError) as err:
        plan_breaker(_panel(), 1, 1, [Leg(1, uuid.uuid4())], {}, [])
    assert err.value.code == "invalid_member"


def test_pnl_003_breaker_past_end_is_rejected():
    panel, a2 = _panel(spaces=20), _channel()
    with pytest.raises(ApiError) as err:
        plan_breaker(panel, 19, 2, [Leg(1, a2.id)], _sites(a2), [])
    assert err.value.code == "invalid_position"


def test_pnl_004_overlapping_another_breaker_is_rejected():
    panel, a2 = _panel(), _channel()
    dryer = _channel(panel, 5, 2)
    with pytest.raises(ApiError) as err:
        plan_breaker(panel, 7, 1, [Leg(1, a2.id)], _sites(a2), [dryer])
    assert err.value.status == 409


def test_pnl_004_replaced_sensor_at_same_breaker_is_cleared():
    panel, a2, c3 = _panel(), _channel(), _channel()
    old_leg = _channel(panel, 1, 2, pole=2)
    to_clear = plan_breaker(panel, 1, 2, [Leg(1, a2.id), Leg(2, c3.id)], _sites(a2, c3), [old_leg])
    assert to_clear == [old_leg]


def test_pnl_004_growing_to_three_poles_keeps_existing_legs():
    panel = _panel()
    a2, b2 = _channel(panel, 1, 2, pole=1), _channel(panel, 1, 2, pole=2)
    legs = [Leg(1, a2.id), Leg(2, b2.id)]
    assert plan_breaker(panel, 1, 3, legs, _sites(a2, b2), [a2, b2]) == []


def test_pnl_004_swapping_legs_is_allowed():
    panel = _panel()
    a2, b2 = _channel(panel, 1, 2, pole=1), _channel(panel, 1, 2, pole=2)
    legs = [Leg(1, b2.id), Leg(2, a2.id)]
    assert plan_breaker(panel, 1, 2, legs, _sites(a2, b2), [a2, b2]) == []


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Pairs:
    def __init__(self, pairs: list[tuple[Channel, uuid.UUID]]) -> None:
        self._pairs = pairs

    def tuples(self) -> list[tuple[Channel, uuid.UUID]]:
        return self._pairs


class FakeSession:
    """Just enough of AsyncSession: scalars() lists the panel, execute() finds sensors."""

    def __init__(self, on_panel: list[Channel], sensors: list[Channel] | None = None) -> None:
        self.on_panel = on_panel
        self.sensors = sensors or []

    async def execute(self, _stmt: Any) -> _Pairs:
        return _Pairs([(c, SITE) for c in self.sensors])

    async def scalars(self, _stmt: Any) -> _Rows:
        return _Rows(self.on_panel)


async def test_pnl_007_shrinking_under_a_breaker_is_rejected():
    panel = _panel(spaces=40)
    session = FakeSession([_channel(panel, 37, 2)])
    with pytest.raises(ApiError) as err:
        await check_reshape(session, panel, 30, "odd_even")  # type: ignore[arg-type]
    assert err.value.code == "panel_in_use"


async def test_pnl_007_reshape_that_still_fits_is_allowed():
    panel = _panel(spaces=40)
    session = FakeSession([_channel(panel, 3, 2)])
    await check_reshape(session, panel, 24, "sequential")  # type: ignore[arg-type]


async def test_pnl_002_set_breaker_writes_each_leg():
    panel, a2, b2 = _panel(), _channel(), _channel()
    session = FakeSession([], [a2, b2])
    legs = [Leg(1, a2.id), Leg(2, b2.id)]
    await set_breaker(session, panel, 1, 2, 30, legs)  # type: ignore[arg-type]
    assert (a2.panel_slot, a2.breaker_poles, a2.breaker_pole, a2.breaker_amps) == (1, 2, 1, 30)
    assert (b2.panel_id, b2.breaker_pole) == (panel.id, 2)


async def test_pnl_004_set_breaker_clears_replaced_leg():
    panel, a2 = _panel(), _channel()
    old = _channel(panel, 1, 2, pole=2)
    session = FakeSession([old], [a2])
    await set_breaker(session, panel, 1, 1, None, [Leg(1, a2.id)])  # type: ignore[arg-type]
    assert old.panel_id is None and old.breaker_pole is None


async def test_pnl_002_clear_breaker_removes_all_legs():
    panel = _panel()
    legs = [_channel(panel, 1, 2, pole=1), _channel(panel, 1, 2, pole=2)]
    other = _channel(panel, 2)
    session = FakeSession([*legs, other])
    assert await clear_breaker(session, panel, 1) == 2  # type: ignore[arg-type]
    assert other.panel_slot == 2 and all(c.panel_id is None for c in legs)
