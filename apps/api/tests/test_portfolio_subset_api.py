"""API tests for POST /portfolio/optimise-subset (G6)."""

import uuid

import pytest

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/portfolio"


def _definition(length: int) -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 5}},
            {"id": "s", "type": "SMA", "params": {"length": length}},
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


async def _seed(client, headers, count: int = 3) -> list[str]:
    """Create `count` strategies, backtest each, return their run IDs."""
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()
    await client.post("/api/v1/data/instruments/sync", headers=headers)
    ingest = await client.post(
        "/api/v1/data/history/ingest",
        headers=headers,
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-07-01", "end": "2026-08-14"},
    )
    assert ingest.status_code == 200, ingest.text

    run_ids: list[str] = []
    for i in range(count):
        created = await client.post(
            "/api/v1/strategies",
            headers=headers,
            json={
                "name": f"Subset strat {i}",
                "underlying": "NIFTY",
                "instrument": "index",
                "strategy_type": "intraday",
                "definition": _definition(10 + i * 5),
            },
        )
        assert created.status_code == 201, created.text
        run = await client.post(
            "/api/v1/backtests",
            headers=headers,
            json={
                "strategy_id": created.json()["id"],
                "start": "2026-07-01",
                "end": "2026-08-14",
            },
        )
        assert run.status_code == 201, run.text
        run_ids.append(run.json()["id"])
    return run_ids


@pytest.mark.asyncio
async def test_requires_auth(client):
    resp = await client.post(f"{BASE}/optimise-subset", json={"run_ids": []})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_returns_ranked_subsets(client, auth_headers):
    run_ids = await _seed(client, auth_headers, 3)
    resp = await client.post(
        f"{BASE}/optimise-subset",
        headers=auth_headers,
        json={"run_ids": run_ids, "size": 2, "objective": "sharpe_ratio"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["best"] is not None
    assert len(body["best"]["run_ids"]) == 2
    assert body["best"]["rank"] == 1
    assert "sharpe_ratio" in body["best"]["metrics"]


@pytest.mark.asyncio
async def test_reports_baseline_and_exhaustiveness(client, auth_headers):
    run_ids = await _seed(client, auth_headers, 3)
    body = (
        await client.post(
            f"{BASE}/optimise-subset",
            headers=auth_headers,
            json={"run_ids": run_ids, "size": 2},
        )
    ).json()
    # The whole point of the baseline: a subset must be judged against its best
    # component, not just reported as a winner.
    assert body["single_best"] is not None
    assert len(body["single_best"]["run_ids"]) == 1
    assert body["exhaustive"] is True
    assert body["combinations_possible"] == 3


@pytest.mark.asyncio
async def test_runners_up_returned(client, auth_headers):
    run_ids = await _seed(client, auth_headers, 3)
    body = (
        await client.post(
            f"{BASE}/optimise-subset",
            headers=auth_headers,
            json={"run_ids": run_ids, "size": 2, "top_n": 3},
        )
    ).json()
    assert len(body["runners_up"]) >= 1
    assert [r["rank"] for r in body["runners_up"]] == sorted(r["rank"] for r in body["runners_up"])


@pytest.mark.asyncio
async def test_rejects_invalid_run_id(client, auth_headers):
    resp = await client.post(
        f"{BASE}/optimise-subset",
        headers=auth_headers,
        json={"run_ids": ["not-a-uuid"]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unknown_runs_404(client, auth_headers):
    resp = await client.post(
        f"{BASE}/optimise-subset",
        headers=auth_headers,
        json={"run_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_run_ids_rejected(client, auth_headers):
    resp = await client.post(
        f"{BASE}/optimise-subset", headers=auth_headers, json={"run_ids": []}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_objective_rejected(client, auth_headers):
    run_ids = await _seed(client, auth_headers, 2)
    resp = await client.post(
        f"{BASE}/optimise-subset",
        headers=auth_headers,
        json={"run_ids": run_ids, "objective": "vibes"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_other_users_runs_are_not_visible(client, auth_headers):
    run_ids = await _seed(client, auth_headers, 2)
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "subset-other@example.com", "password": "Password123!"},
    )
    assert register.status_code in (200, 201)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "subset-other@example.com", "password": "Password123!"},
    )
    token = login.json()["access_token"]
    resp = await client.post(
        f"{BASE}/optimise-subset",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_ids": run_ids, "size": 2},
    )
    assert resp.status_code == 404
