"""Integration tests for /forward-tests endpoints.

Covers the full HTTP tick path — the code path where a NameError hid until
lint flagged it (bars_processed referenced an undefined variable), because no
test exercised a tick that actually processed new bars.
"""

from datetime import datetime, timedelta

from app.services.candles import resolve_instrument
from app.services.validation import ensure_utc

BASE = "/api/v1/forward-tests"


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


async def setup_strategy_and_account(client, auth_headers) -> tuple[dict, dict]:
    await client.post("/api/v1/data/instruments/sync", headers=auth_headers)
    ingest = await client.post(
        "/api/v1/data/history/ingest",
        headers=auth_headers,
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-08-10", "end": "2026-08-14"},
    )
    assert ingest.status_code == 200, ingest.text

    strategy = (
        await client.post(
            "/api/v1/strategies",
            json={
                "name": "FT SMA Cross",
                "underlying": "NIFTY",
                "instrument": "index",
                "strategy_type": "intraday",
                "definition": valid_definition(),
            },
            headers=auth_headers,
        )
    ).json()

    account = (
        await client.post(
            "/api/v1/paper/accounts",
            json={"name": "ft-account", "initial_capital": 1_000_000},
            headers=auth_headers,
        )
    ).json()
    return strategy, account


async def create_run(client, auth_headers, strategy: dict, account: dict) -> str:
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "account_id": account["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_requires_auth(client):
    assert (await client.get(BASE)).status_code == 401


async def test_first_tick_anchors_without_action(client, auth_headers):
    strategy, account = await setup_strategy_and_account(client, auth_headers)
    run_id = await create_run(client, auth_headers, strategy, account)

    resp = await client.post(f"{BASE}/{run_id}/tick", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["bars_processed"] == 0
    assert body["fills"] == []
    assert body["open_position"] is None

    detail = (await client.get(f"{BASE}/{run_id}", headers=auth_headers)).json()
    assert detail["last_bar_time"] is not None


async def test_duplicate_running_run_rejected(client, auth_headers):
    strategy, account = await setup_strategy_and_account(client, auth_headers)
    await create_run(client, auth_headers, strategy, account)
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "account_id": account["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "running" in resp.json()["detail"].lower()


async def test_tick_processes_new_bars_and_reports_fills(client, auth_headers, db_session):
    from app.models import CANDLE_MODELS_BY_SEGMENT

    strategy, account = await setup_strategy_and_account(client, auth_headers)
    run_id = await create_run(client, auth_headers, strategy, account)

    first = await client.post(f"{BASE}/{run_id}/tick", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["bars_processed"] == 0

    detail = (await client.get(f"{BASE}/{run_id}", headers=auth_headers)).json()
    anchor = ensure_utc(datetime.fromisoformat(detail["last_bar_time"]))

    instrument = await resolve_instrument(db_session, "NIFTY")
    assert instrument is not None
    model = CANDLE_MODELS_BY_SEGMENT["index"]

    # Engineered series: decline then a sharp rally -> SMA(5) must cross above SMA(20).
    start_close = 22_000.0
    prices = [start_close - 25 * i for i in range(1, 13)]
    prices += [prices[-1] + 60 * i for i in range(1, 15)]

    t = anchor
    prev_close = start_close
    for close in prices:
        t = t + timedelta(minutes=5)
        db_session.add(
            model(
                # Candle rows are keyed by symbol (see services/candles.load_candles).
                instrument_id=instrument.symbol,
                interval="5m",
                time=t,
                open=prev_close,
                high=max(prev_close, close) + 15,
                low=min(prev_close, close) - 15,
                close=close,
                volume=1000,
                oi=None,
            )
        )
        prev_close = close
    await db_session.commit()

    resp = await client.post(f"{BASE}/{run_id}/tick", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bars_processed"] == len(prices)

    detail = (await client.get(f"{BASE}/{run_id}", headers=auth_headers)).json()
    # With fills the message lists them ("entry BUY ..."); without, it reports bar counts.
    msg = detail["last_message"].lower()
    assert "processed" in msg or "entry" in msg or "exit" in msg

    for fill in body["fills"]:
        assert set(fill.keys()) >= {"side", "quantity", "price", "reason"}


async def test_ticking_paused_run_rejected(client, auth_headers):
    strategy, account = await setup_strategy_and_account(client, auth_headers)
    run_id = await create_run(client, auth_headers, strategy, account)

    paused = await client.post(f"{BASE}/{run_id}/pause", headers=auth_headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resp = await client.post(f"{BASE}/{run_id}/tick", headers=auth_headers)
    assert resp.status_code == 400
    assert "not running" in resp.json()["detail"]

    resumed = await client.post(f"{BASE}/{run_id}/resume", headers=auth_headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"

    stopped = await client.post(f"{BASE}/{run_id}/stop", headers=auth_headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"


async def test_other_user_cannot_tick(client, auth_headers):
    strategy, account = await setup_strategy_and_account(client, auth_headers)
    run_id = await create_run(client, auth_headers, strategy, account)

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "intruder@example.com", "password": "secret1234"},
    )
    assert reg.status_code in (200, 201)
    login = await client.post(
        "/api/v1/auth/login", json={"email": "intruder@example.com", "password": "secret1234"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(f"{BASE}/{run_id}/tick", headers=other_headers)
    assert resp.status_code == 404
