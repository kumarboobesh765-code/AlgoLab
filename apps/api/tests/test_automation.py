"""Tests for the automation loop (/automation): signals -> orders."""

import pytest

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/automation"


def _definition() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 3}},
            {"id": "s", "type": "SMA", "params": {"length": 10}},
        ],
        "entry": {"logic": "ALL", "conditions": [
            {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "s"}}]},
        "exit": {"logic": "ALL", "conditions": [
            {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "s"}}]},
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }


async def _setup(client, headers):
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()
    await client.post("/api/v1/data/instruments/sync", headers=headers)
    r = await client.post(
        "/api/v1/data/history/ingest",
        headers=headers,
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-08-03", "end": "2026-08-14"},
    )
    assert r.status_code == 200
    s = await client.post(
        "/api/v1/strategies",
        json={"name": "AutoStrat", "underlying": "NIFTY", "instrument": "index",
              "strategy_type": "intraday", "definition": _definition()},
        headers=headers,
    )
    assert s.status_code == 201
    return s.json()["id"]


@pytest.mark.asyncio
async def test_run_once_requires_started(client, auth_headers):
    sid = await _setup(client, auth_headers)
    resp = await client.post(f"{BASE}/{sid}/run-once", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_stop_and_run_cycle(client, auth_headers):

    sid = await _setup(client, auth_headers)

    start = await client.post(
        BASE + "/start",
        json={"strategy_id": sid, "broker": "mock", "mode": "paper"},
        headers=auth_headers,
    )
    assert start.status_code == 200, start.text
    assert start.json()["started"] is True

    run1 = (await client.post(f"{BASE}/{sid}/run-once", headers=auth_headers)).json()
    assert run1["bars_evaluated"] >= 5
    # Demo data zigzags — either an action fired or no signal on the last bar
    if run1["actions"]:
        assert any(a.startswith(("BUY", "SELL", "EXIT")) for a in run1["actions"])

    listing = (await client.get(BASE, headers=auth_headers)).json()
    assert any(a["strategy_id"] == sid for a in listing)
    entry_state = next(a for a in listing if a["strategy_id"] == sid)
    assert entry_state["runs"] == 1

    stop = await client.post(f"{BASE}/{sid}/stop", headers=auth_headers)
    assert stop.status_code == 200


@pytest.mark.asyncio
async def test_confirm_mode_stages_orders(client, auth_headers):
    sid = await _setup(client, auth_headers)
    await client.post(
        BASE + "/start",
        json={"strategy_id": sid, "broker": "mock", "mode": "confirm"},
        headers=auth_headers,
    )
    run = (await client.post(f"{BASE}/{sid}/run-once", headers=auth_headers)).json()
    # Any routed action must be staged PENDING, not executed
    for a in run["actions"]:
        kind, st, _ = a.split(":", 2)
        assert st == "PENDING"
