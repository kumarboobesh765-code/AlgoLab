"""Integration tests for the /data API endpoints (with the demo provider)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/data"


def override_demo_provider():
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()


async def test_data_endpoints_require_auth(client):
    assert (await client.get(f"{BASE}/instruments")).status_code == 401
    assert (await client.get(f"{BASE}/status")).status_code == 401
    assert (await client.post(f"{BASE}/instruments/sync")).status_code == 401


async def test_full_data_flow(client, auth_headers):
    override_demo_provider()

    # 1. sync instruments
    resp = await client.post(f"{BASE}/instruments/sync", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "demo"
    assert body["received"] == 5

    # 2. list instruments
    resp = await client.get(f"{BASE}/instruments", headers=auth_headers)
    instruments = resp.json()
    assert any(i["symbol"] == "NIFTY" for i in instruments)

    # 3. ingest one day of 5m candles
    resp = await client.post(
        f"{BASE}/history/ingest",
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-08-10", "end": "2026-08-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["fetched"] == 75
    assert stats["inserted_or_updated"] == 75
    assert stats["issues"] == []
    assert stats["coverage"]["status"] == "healthy"

    # 4. quality report on stored candles
    resp = await client.get(
        f"{BASE}/quality/NIFTY?interval=5m&days=7", headers=auth_headers
    )
    assert resp.status_code == 200
    quality = resp.json()
    assert quality["candles_checked"] == 75
    assert quality["issues"] == []

    # 5. status overview
    resp = await client.get(f"{BASE}/status", headers=auth_headers)
    status_body = resp.json()
    assert status_body["candle_counts"]["index"] == 75
    assert status_body["instruments"] == 5


async def test_ingest_rejects_oversized_range(client, auth_headers):
    override_demo_provider()
    resp = await client.post(
        f"{BASE}/history/ingest",
        json={"symbol": "NIFTY", "interval": "5m", "start": "2026-01-01", "end": "2026-12-31"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Range too large" in resp.json()["detail"]


async def test_ingest_unknown_instrument(client, auth_headers):
    override_demo_provider()
    resp = await client.post(
        f"{BASE}/history/ingest",
        json={"symbol": "FAKE", "interval": "5m", "start": "2026-08-10", "end": "2026-08-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 502
    assert "Sync the instrument master" in resp.json()["detail"]
