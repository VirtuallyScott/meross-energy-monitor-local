"""TST-002 / TST-010: the RPC client against the device simulator."""

import time

import httpx
import pytest

from app.collector.ingest import live_rows, minute_rows
from app.devices.rpc import DeviceAuthError, DeviceClient, DeviceRpcError
from app.devices.service import channel_numbers, phase_label
from app.sim.server import DEV_ID, create_sim_app


def client_for(app, password=None):
    transport = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(transport=transport)
    return DeviceClient(base_url="http://sim", password=password, _http=http)


async def test_info_status_merges():
    async with client_for(create_sim_app()) as client:
        info = await client.device_info()
        assert info["dev_id"] == DEV_ID
        status = await client.status()
        assert channel_numbers(status) == list(range(1, 19))
        assert status["emmerge:130"] == {}
        assert [m["channels"] for m in await client.merges()] == [130, 1040, 2080]


async def test_history_follows_pagination_past_60_rows():
    now = int(time.time())
    start = now - now % 60 - 150 * 60
    async with client_for(create_sim_app()) as client:
        rows = [r async for r in client.history(1, start, start + 150 * 60, page_gap_s=0)]
    assert len(rows) == 150
    assert rows[1].ts - rows[0].ts == 60
    assert rows[0].values["energy"] > 0


async def test_history_empty_range_yields_nothing():
    async with client_for(create_sim_app()) as client:
        rows = [r async for r in client.history(1, 1000, 5000, page_gap_s=0)]
    assert rows == []


async def test_missing_result_is_error():
    async with client_for(create_sim_app()) as client:
        with pytest.raises(DeviceRpcError):
            await client.call("Em.Data.Get", {"id": 1})


async def test_digest_auth_flow():
    app = create_sim_app(password="hunter2hunter2")
    async with client_for(app, password="hunter2hunter2") as client:
        await client.device_info()
        assert "em:1" in await client.status()
    async with client_for(app, password="wrong") as client:
        await client.device_info()
        with pytest.raises(DeviceAuthError):
            await client.status()
    async with client_for(app) as client:
        await client.device_info()
        with pytest.raises(DeviceAuthError):
            await client.status()


def test_phase_labels():
    assert [phase_label(n, 18) for n in (1, 6, 7, 12, 13, 18)] == [
        "A1",
        "A6",
        "B1",
        "B6",
        "C1",
        "C6",
    ]


def test_row_mapping():
    import uuid
    from datetime import UTC, datetime

    from app.devices.rpc import HistoryRow

    ch = uuid.uuid4()
    rows = live_rows(
        {1: ch},
        {"ts": 1, "em:1": {"power": 10, "voltage": 120.5}, "em:2": {"power": 5}, "wifi": {}},
        datetime.now(UTC),
    )
    assert len(rows) == 1 and rows[0]["power_w"] == 10.0 and rows[0]["pf"] is None
    mins = minute_rows(ch, [HistoryRow(ts=120, values={"energy": 0.05, "power_avg": 3000})])
    assert mins[0]["energy_kwh"] == 0.05 and mins[0]["power_avg"] == 3000.0
    assert mins[0]["ts"] == datetime.fromtimestamp(120, UTC)
