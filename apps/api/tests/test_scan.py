"""Tests for POST /quant/scan (multi-symbol scanner)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/quant"


def definition(symbol: str) -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": symbol},
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
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }


async def ingest_symbol(client, headers, symbol: str):
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()
    await client.post("/api/v1/data/instruments/sync", headers=headers)
    resp = await client.post(
        "/api/v1/data/history/ingest",
        headers=headers,
        json={"symbol": symbol, "interval": "5m", "start": "2026-08-03", "end": "2026-08-14"},
    )
    assert resp.status_code == 200, resp.text


async def test_scan_ranks_and_isolates_errors(client, auth_headers):
    await ingest_symbol(client, auth_headers, "NIFTY")
    await ingest_symbol(client, auth_headers, "BANKNIFTY")

    resp = await client.post(
        f"{BASE}/scan",
        json={
            "symbols": ["nifty", "BANKNIFTY", "UNKNOWN_XYZ"],
            "definition": definition("NIFTY"),
            "start": "2026-08-03",
            "end": "2026-08-14",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    symbols = [r["symbol"] for r in data["rows"]]
    assert "NIFTY" in symbols and "BANKNIFTY" in symbols
    assert data["scanned"] == 2
    assert "UNKNOWN_XYZ" in data["errors"]
    for row in data["rows"]:
        assert row["bars_evaluated"] > 0
        assert row["entry_signals"] >= 0


async def test_scan_invalid_definition_422(client, auth_headers):
    bad = definition("NIFTY") | {"timeframe": "7m"}
    resp = await client.post(
        f"{BASE}/scan",
        json={"symbols": ["NIFTY"], "definition": bad},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_scan_requires_auth(client):
    resp = await client.post(f"{BASE}/scan", json={"symbols": ["NIFTY"], "definition": {}})
    assert resp.status_code == 401
