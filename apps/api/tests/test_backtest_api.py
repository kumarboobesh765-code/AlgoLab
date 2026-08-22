"""Integration tests for /backtests endpoints."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/backtests"


def override_demo_provider():
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()


def valid_definition() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 5}},
            {"id": "s", "type": "SMA", "params": {"length": 20}},
        ],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "s"}}
            ],
        },
        "exit": {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "s"}}
            ],
        },
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }


async def create_strategy(client, headers, definition=None) -> dict:
    payload = {
        "name": "SMA Cross Backtest",
        "underlying": "NIFTY",
        "instrument": "index",
        "strategy_type": "intraday",
    }
    if definition is not None:
        payload["definition"] = definition
    resp = await client.post("/api/v1/strategies", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def ingest_demo_history(client, headers):
    override_demo_provider()
    await client.post("/api/v1/data/instruments/sync", headers=headers)
    resp = await client.post(
        "/api/v1/data/history/ingest",
        headers=headers,
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-08-10", "end": "2026-08-14"},
    )
    assert resp.status_code == 200, resp.text


async def test_requires_auth(client):
    assert (await client.post(BASE, json={})).status_code == 401
    assert (await client.get(BASE)).status_code == 401


async def test_unknown_strategy_404(client, auth_headers):
    resp = await client.post(
        BASE,
        json={"strategy_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_strategy_without_definition_rejected(client, auth_headers):
    strategy = await create_strategy(client, auth_headers)
    resp = await client.post(
        BASE, json={"strategy_id": strategy["id"]}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert "no definition" in resp.json()["detail"]


async def test_no_stored_candles_rejected(client, auth_headers):
    strategy = await create_strategy(client, auth_headers, valid_definition())
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "start": "2026-08-10", "end": "2026-08-14"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "ingest" in resp.json()["detail"].lower()


async def test_happy_path_run(client, auth_headers):
    await ingest_demo_history(client, auth_headers)
    strategy = await create_strategy(client, auth_headers, valid_definition())

    resp = await client.post(
        BASE,
        json={
            "strategy_id": strategy["id"],
            "start": "2026-08-10",
            "end": "2026-08-14",
            "initial_capital": 200_000,
            "costs_pct": 0.01,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["version_number"] == 1
    cfg = body["config"]
    assert cfg["symbol"] == "NIFTY"
    assert cfg["timeframe"] == "5m"
    assert cfg["bars"] > 0
    assert cfg["initial_capital"] == 200_000

    results = body["result_summary"]
    s = results["summary"]
    for key in (
        "net_pnl", "return_pct", "total_trades", "win_rate", "profit_factor",
        "max_drawdown_pct", "sharpe_ratio", "final_equity", "total_costs",
    ):
        assert key in s
    assert s["initial_capital"] == 200_000
    assert isinstance(results["trades"], list)
    assert len(results["equity_curve"]) == cfg["bars"]

    # List shows the run; detail returns full results.
    listed = (await client.get(f"{BASE}?strategy_id={strategy['id']}", headers=auth_headers)).json()
    assert len(listed) == 1
    detail = (await client.get(f"{BASE}/{body['id']}", headers=auth_headers)).json()
    assert detail["id"] == body["id"]
    assert "trades" in detail["result_summary"]


async def test_run_user_isolation(client, auth_headers):
    await ingest_demo_history(client, auth_headers)
    strategy = await create_strategy(client, auth_headers, valid_definition())
    created = (
        await client.post(
            BASE,
            json={"strategy_id": strategy["id"], "start": "2026-08-10", "end": "2026-08-14"},
            headers=auth_headers,
        )
    ).json()

    # Second user cannot see or fetch the run.
    await client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "secret123"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "other@example.com", "password": "secret123"}
    )
    other_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    assert (await client.get(BASE, headers=other_headers)).json() == []
    assert (await client.get(f"{BASE}/{created['id']}", headers=other_headers)).status_code == 404


async def test_invalid_range_rejected(client, auth_headers):
    strategy = await create_strategy(client, auth_headers, valid_definition())
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "start": "2026-08-14", "end": "2026-08-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
