"""Integration tests for the /quant API endpoints."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/quant"


def override_demo_provider():
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()


def ema_def() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [
            {"id": "ema_fast", "type": "EMA", "params": {"length": 3}},
            {"id": "ema_slow", "type": "EMA", "params": {"length": 8}},
        ],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {
                    "left": {"kind": "indicator", "ref": "ema_fast"},
                    "op": "CROSS_ABOVE",
                    "right": {"kind": "indicator", "ref": "ema_slow"},
                }
            ],
        },
    }


async def test_quant_requires_auth(client):
    assert (await client.get(f"{BASE}/catalog")).status_code == 401
    assert (await client.post(f"{BASE}/validate", json={})).status_code == 401


async def test_catalog(client, auth_headers):
    resp = await client.get(f"{BASE}/catalog", headers=auth_headers)
    catalog = resp.json()
    types = {i["type"] for i in catalog["indicators"]}
    assert {"SMA", "EMA", "RSI", "MACD", "BBANDS", "SUPERTREND"} <= types
    sma = next(i for i in catalog["indicators"] if i["type"] == "SMA")
    assert sma["outputs"] == ["sma"]
    assert sma["params"]["length"]["default"] == 20


async def test_validate_ok_and_bad(client, auth_headers):
    resp = await client.post(f"{BASE}/validate", json=ema_def(), headers=auth_headers)
    body = resp.json()
    assert body == {"valid": True, "errors": [], "warnings": []}

    bad = ema_def()
    bad["timeframe"] = "13m"
    resp = await client.post(f"{BASE}/validate", json=bad, headers=auth_headers)
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"]


async def test_preview_with_demo_provider(client, auth_headers):
    override_demo_provider()
    # Sync instruments so the symbol resolves.
    await client.post("/api/v1/data/instruments/sync", headers=auth_headers)

    resp = await client.post(
        f"{BASE}/preview?bars=300", json=ema_def(), headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["is_demo"] is True
    assert body["provider"] == "demo"
    assert body["bars_evaluated"] > 0
    assert set(body["indicator_tail"]) == {"ema_fast", "ema_slow"}
    assert isinstance(body["last_bar_entry_signal"], bool)


async def test_preview_rejects_invalid_definition(client, auth_headers):
    override_demo_provider()
    bad = ema_def()
    bad["entry"]["conditions"][0]["op"] = "MAGICAL"
    resp = await client.post(f"{BASE}/preview", json=bad, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"]


async def test_preview_unknown_symbol(client, auth_headers):
    override_demo_provider()
    d = ema_def()
    d["instrument"]["symbol"] = "NOSUCH"
    resp = await client.post(f"{BASE}/preview", json=d, headers=auth_headers)
    assert resp.status_code == 404
