"""Integration tests for /optimizations endpoints (grid + walk-forward)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/optimizations"


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


async def make_strategy(client, headers) -> dict:
    resp = await client.post(
        "/api/v1/strategies",
        json={
            "name": "Opt Target",
            "underlying": "NIFTY",
            "instrument": "index",
            "strategy_type": "intraday",
            "definition": valid_definition(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def ingest(client, headers):
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()
    await client.post("/api/v1/data/instruments/sync", headers=headers)
    resp = await client.post(
        "/api/v1/data/history/ingest",
        headers=headers,
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-08-03", "end": "2026-08-14"},
    )
    assert resp.status_code == 200, resp.text


async def test_requires_auth(client):
    assert (await client.post(BASE, json={})).status_code == 401
    assert (await client.get(BASE)).status_code == 401


async def test_grid_search_happy_path(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)

    resp = await client.post(
        BASE,
        json={
            "strategy_id": strategy["id"],
            "method": "grid",
            "param_ranges": {
                "indicators.f.params.length": [3, 5, 8],
                "indicators.s.params.length": [15, 20],
            },
            "start": "2026-08-03",
            "end": "2026-08-14",
            "target_metric": "sharpe_ratio",
            "initial_capital": 100_000,
            "costs_pct": 0.01,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["status"] == "completed"
    assert run["total_combinations"] == 6
    assert run["completed_combinations"] == 6
    assert run["best_params"] is not None
    assert "sharpe_ratio" in run["best_metrics"]

    results = (
        await client.get(f"{BASE}/{run['id']}/results", headers=auth_headers)
    ).json()
    assert len(results) == 6
    ranks = [r["rank"] for r in results]
    assert ranks == list(range(1, 7))
    assert all(r["status"] == "completed" for r in results)


async def test_walk_forward_persists_train_pct(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)

    resp = await client.post(
        BASE,
        json={
            "strategy_id": strategy["id"],
            "method": "walk_forward",
            "param_ranges": {"indicators.f.params.length": [3, 5]},
            "start": "2026-08-03",
            "end": "2026-08-14",
            "target_metric": "sharpe_ratio",
            "train_pct": 0.7,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["train_pct"] == 0.7
    assert run["status"] == "completed"
    results = (
        await client.get(f"{BASE}/{run['id']}/results", headers=auth_headers)
    ).json()
    assert all("train_sharpe" in r and "test_sharpe" in r for r in results)


async def test_too_many_combinations_400(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)
    resp = await client.post(
        BASE,
        json={
            "strategy_id": strategy["id"],
            "method": "grid",
            # 11 x 51 = 561 > 500
            "param_ranges": {
                "indicators.f.params.length": list(range(2, 13)),
                "indicators.s.params.length": list(range(10, 61)),
            },
            "start": "2026-08-03",
            "end": "2026-08-14",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "500" in resp.json()["detail"]


async def test_not_enough_candles_400(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)
    resp = await client.post(
        BASE,
        json={
            "strategy_id": strategy["id"],
            "method": "grid",
            "param_ranges": {"indicators.f.params.length": [3]},
            "start": "2026-07-01",
            "end": "2026-07-02",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "candles" in resp.json()["detail"].lower()


async def test_user_isolation(client, auth_headers):
    resp = await client.get(f"{BASE}/00000000-0000-0000-0000-000000000009", headers=auth_headers)
    assert resp.status_code == 404


# ---- background execution mode ----


async def test_background_run_executes(client, auth_headers, db_engine, db_session, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.db.session as db_session_module

    # Route the executor's session factory at the isolated test database
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_session_module, "get_session_factory", lambda: factory)

    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)

    resp = await client.post(
        f"{BASE}?background=true",
        json={
            "strategy_id": strategy["id"],
            "method": "grid",
            "param_ranges": {"indicators.f.params.length": [3, 5]},
            "start": "2026-08-03",
            "end": "2026-08-14",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 202, resp.text
    run = resp.json()
    assert run["status"] == "queued"

    # TestClient runs BackgroundTasks inline before returning — the run is done.
    detail = (await client.get(f"{BASE}/{run['id']}", headers=auth_headers)).json()
    assert detail["status"] == "completed"
    assert detail["completed_combinations"] == 2
    assert detail["best_params"] is not None


# ---- parameter sensitivity heatmap ----


async def test_heatmap_happy_path(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)

    resp = await client.post(
        f"{BASE}/heatmap",
        json={
            "strategy_id": strategy["id"],
            "x_key": "indicators.f.params.length",
            "x_values": [3, 5, 8],
            "y_key": "indicators.s.params.length",
            "y_values": [15, 20],
            "metric": "sharpe_ratio",
            "start": "2026-08-03",
            "end": "2026-08-14",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["x_key"] == "indicators.f.params.length"
    assert data["metric"] == "sharpe_ratio"
    assert len(data["cells"]) == 6
    assert all(c["value"] is not None for c in data["cells"])
    assert data["best"] is not None and data["worst"] is not None


async def test_heatmap_too_large_422(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/heatmap",
        json={
            "strategy_id": strategy["id"],
            "x_key": "indicators.f.params.length",
            "x_values": list(range(2, 28)),  # 26 values > schema cap of 25
            "y_key": "indicators.s.params.length",
            "y_values": list(range(10, 35)),
            "start": "2026-08-03",
            "end": "2026-08-14",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_heatmap_not_enough_candles_400(client, auth_headers):
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/heatmap",
        json={
            "strategy_id": strategy["id"],
            "x_key": "indicators.f.params.length",
            "x_values": [3, 5],
            "y_key": "indicators.s.params.length",
            "y_values": [15, 20],
            "start": "2026-07-01",
            "end": "2026-07-02",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_heatmap_bad_params_grey_cells(client, auth_headers):
    """A param key that doesn't exist yields failed combos → null values, not a 500."""
    await ingest(client, auth_headers)
    strategy = await make_strategy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/heatmap",
        json={
            "strategy_id": strategy["id"],
            "x_key": "risk.stop_loss_pct",
            "x_values": [0.5, 1.0],
            "y_key": "indicators.f.params.length",
            "y_values": [3, 5],
            "start": "2026-08-03",
            "end": "2026-08-14",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["cells"]) == 4
