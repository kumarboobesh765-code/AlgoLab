"""Integration tests for /backtests/validate (In/Out-of-Sample split)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/backtests/validate"


def override_demo_provider():
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()


def crossover_definition() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [
            {"id": "f", "type": "EMA", "params": {"length": 5}},
            {"id": "s", "type": "EMA", "params": {"length": 20}},
        ],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {
                    "left": {"kind": "indicator", "ref": "f"},
                    "op": "CROSS_ABOVE",
                    "right": {"kind": "indicator", "ref": "s"},
                }
            ],
        },
        "exit": {
            "logic": "ALL",
            "conditions": [
                {
                    "left": {"kind": "indicator", "ref": "f"},
                    "op": "CROSS_BELOW",
                    "right": {"kind": "indicator", "ref": "s"},
                }
            ],
        },
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }


async def _setup(client, headers, definition=None, days=("2026-07-01", "2026-08-14")):
    override_demo_provider()
    await client.post("/api/v1/data/instruments/sync", headers=headers)
    ingest = await client.post(
        "/api/v1/data/history/ingest",
        headers=headers,
        json={"symbol": "NIFTY", "interval": "5m", "start": days[0], "end": days[1]},
    )
    assert ingest.status_code == 200, ingest.text
    created = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json={
            "name": "OOS validation strategy",
            "underlying": "NIFTY",
            "instrument": "index",
            "strategy_type": "intraday",
            "definition": definition or crossover_definition(),
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


async def test_requires_auth(client):
    resp = await client.post(BASE, json={})
    assert resp.status_code == 401


async def test_unknown_strategy_404(client, auth_headers):
    resp = await client.post(
        BASE,
        json={"strategy_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_returns_split_payload(client, auth_headers):
    strategy = await _setup(client, auth_headers)
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "start": "2026-07-01", "end": "2026-08-14"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["split_index"] > 0
    assert body["warmup_bars"] >= 0
    assert body["bars_used"] > 0
    assert set(body["windows"]) == {"in_sample", "out_of_sample"}
    for window in body["windows"].values():
        assert window["start"] < window["end"]
        assert "return_pct" in window["summary"]
    deg = body["degradation"]
    assert {"is_return_pct", "oos_return_pct", "is_sharpe", "oos_sharpe"} <= set(deg)
    assert isinstance(deg["oos_is_profitable"], bool)


async def test_warmup_derived_from_the_definition(client, auth_headers):
    """EMA20 needs 20 bars of context, so warmup must be non-zero and match."""
    strategy = await _setup(client, auth_headers)
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "start": "2026-07-01", "end": "2026-08-14"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["warmup_bars"] == 20


async def test_split_ratio_is_honoured(client, auth_headers):
    strategy = await _setup(client, auth_headers)
    body = {}
    for split in (0.5, 0.8):
        resp = await client.post(
            BASE,
            json={
                "strategy_id": strategy["id"],
                "start": "2026-07-01",
                "end": "2026-08-14",
                "split": split,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body[split] = resp.json()
    assert body[0.8]["split_index"] > body[0.5]["split_index"]


async def test_rejects_invalid_split(client, auth_headers):
    strategy = await _setup(client, auth_headers)
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "split": 1.4},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_insufficient_history_is_a_clear_400(client, auth_headers):
    """Too few bars must explain itself, not surface as a 500."""
    strategy = await _setup(client, auth_headers, days=("2026-08-10", "2026-08-10"))
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "start": "2026-08-10", "end": "2026-08-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "candles" in resp.json()["detail"].lower() or "start" in resp.json()["detail"].lower()


async def test_start_after_end_rejected(client, auth_headers):
    strategy = await _setup(client, auth_headers)
    resp = await client.post(
        BASE,
        json={
            "strategy_id": strategy["id"],
            "start": "2026-08-14",
            "end": "2026-07-01",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_does_not_persist_a_backtest_run(client, auth_headers):
    """Validation is a read-only analysis, so it must not create run rows."""
    strategy = await _setup(client, auth_headers)
    before = (await client.get("/api/v1/backtests", headers=auth_headers)).json()
    await client.post(
        BASE,
        json={"strategy_id": strategy["id"], "start": "2026-07-01", "end": "2026-08-14"},
        headers=auth_headers,
    )
    after = (await client.get("/api/v1/backtests", headers=auth_headers)).json()
    assert len(before) == len(after)


async def test_strategy_without_definition_rejected(client, auth_headers):
    override_demo_provider()
    created = await client.post(
        "/api/v1/strategies",
        headers=auth_headers,
        json={
            "name": "No definition",
            "underlying": "NIFTY",
            "instrument": "index",
            "strategy_type": "intraday",
        },
    )
    assert created.status_code == 201
    resp = await client.post(
        BASE,
        json={"strategy_id": created.json()["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "definition" in resp.json()["detail"].lower()


async def test_other_user_cannot_validate_their_strategy(client, auth_headers):
    """The strategy lookup must stay scoped to the owner."""
    strategy = await _setup(client, auth_headers)
    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "oos-other@example.com", "password": "Password123!"},
    )
    assert other.status_code in (200, 201)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "oos-other@example.com", "password": "Password123!"},
    )
    token = login.json()["access_token"]
    resp = await client.post(
        BASE,
        json={"strategy_id": strategy["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
