"""Integration tests for /market endpoints (demo provider)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/market"


def override_demo_provider():
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()


async def test_instruments(client, auth_headers):
    override_demo_provider()
    resp = await client.get(f"{BASE}/instruments", headers=auth_headers)
    assert resp.status_code == 200
    instruments = resp.json()
    assert len(instruments) > 0
    for key in ("symbol", "exchange", "segment"):
        assert key in instruments[0]


async def test_candles_fixed_range(client, auth_headers):
    override_demo_provider()
    resp = await client.get(
        f"{BASE}/candles",
        params={
            "symbol": "NIFTY",
            "interval": "5m",
            "start": "2026-08-10T00:00:00+00:00",
            "end": "2026-08-12T00:00:00+00:00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    candles = resp.json()
    assert len(candles) > 0
    first = candles[0]
    for key in ("timestamp", "open", "high", "low", "close", "volume"):
        assert key in first


async def test_candles_invalid_interval_400(client, auth_headers):
    override_demo_provider()
    resp = await client.get(
        f"{BASE}/candles", params={"interval": "7m"}, headers=auth_headers
    )
    assert resp.status_code == 400


async def test_option_chain_shape_and_cache(client, auth_headers):
    override_demo_provider()
    resp = await client.get(
        f"{BASE}/option-chain", params={"underlying": "NIFTY"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    chain = resp.json()
    assert chain["is_demo"] is True
    assert chain["underlying"] == "NIFTY"
    assert chain["spot"] > 0
    assert len(chain["strikes"]) > 0
    row = chain["strikes"][0]
    for key in ("strike", "call_ltp", "put_ltp", "call_iv", "put_iv", "call_delta", "put_delta"):
        assert key in row

    # Second hit must come from the cache (same payload).
    cached = await client.get(
        f"{BASE}/option-chain", params={"underlying": "NIFTY"}, headers=auth_headers
    )
    assert cached.status_code == 200
    assert cached.json() == chain


async def test_option_chain_unknown_underlying_400(client, auth_headers):
    override_demo_provider()
    resp = await client.get(
        f"{BASE}/option-chain", params={"underlying": "NOPE"}, headers=auth_headers
    )
    assert resp.status_code == 400
