"""Integration tests for strategy polish endpoints (report, import/export, templates, compare)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1"


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


async def test_templates(client, auth_headers):
    resp = await client.get(f"{BASE}/templates", headers=auth_headers)
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 5
    names = {t["name"] for t in templates}
    assert "EMA Crossover" in names
    assert "RSI Mean Reversion" in names
    for t in templates:
        assert "definition" in t
        assert "name" in t
        assert "description" in t


async def test_export_import_roundtrip(client, auth_headers):
    # Create a strategy
    resp = await client.post(
        f"{BASE}/strategies",
        json={"name": "Export Test", "underlying": "NIFTY", "definition": valid_definition()},
        headers=auth_headers,
    )
    strategy_id = resp.json()["id"]

    # Export it
    export_resp = await client.get(f"{BASE}/strategies/{strategy_id}/export", headers=auth_headers)
    assert export_resp.status_code == 200
    exported = export_resp.json()
    assert exported["name"] == "Export Test"
    assert exported["definition"] is not None

    # Import it as a new strategy
    import_resp = await client.post(
        f"{BASE}/strategies/import",
        json={
            "name": "Imported Copy",
            "definition": exported["definition"],
            "exchange": exported["exchange"],
            "underlying": exported["underlying"],
        },
        headers=auth_headers,
    )
    assert import_resp.status_code == 201
    imported = import_resp.json()
    assert imported["name"] == "Imported Copy"
    assert imported["definition"]["timeframe"] == "5m"


async def test_import_rejects_invalid_definition(client, auth_headers):
    resp = await client.post(
        f"{BASE}/strategies/import",
        json={"name": "Bad", "definition": {"version": 1, "timeframe": "X"}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_report(client, auth_headers):
    resp = await client.post(
        f"{BASE}/strategies",
        json={"name": "Report Test", "underlying": "NIFTY", "definition": valid_definition()},
        headers=auth_headers,
    )
    strategy_id = resp.json()["id"]

    report_resp = await client.get(f"{BASE}/strategies/{strategy_id}/report", headers=auth_headers)
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["strategy"]["name"] == "Report Test"
    assert report["strategy"]["has_definition"] is True
    assert isinstance(report["versions"], list)
    assert report["total_backtests"] == 0
    assert report["latest_backtest"] is None
    assert isinstance(report["optimizations"], list)


async def test_compare_versions(client, auth_headers):
    # Create strategy with definition
    resp = await client.post(
        f"{BASE}/strategies",
        json={"name": "Compare Test", "underlying": "NIFTY", "definition": valid_definition()},
        headers=auth_headers,
    )
    strategy_id = resp.json()["id"]

    # Update definition to create v2
    new_def = valid_definition()
    new_def["indicators"][0]["params"]["length"] = 10
    await client.patch(
        f"{BASE}/strategies/{strategy_id}",
        json={"definition": new_def},
        headers=auth_headers,
    )

    # Compare v1 vs v2
    compare_resp = await client.get(
        f"{BASE}/strategies/{strategy_id}/compare?v1=1&v2=2", headers=auth_headers
    )
    assert compare_resp.status_code == 200
    result = compare_resp.json()
    assert result["v1_version"] == 1
    assert result["v2_version"] == 2
    assert result["v1_definition"] is not None
    assert result["v2_definition"] is not None
    assert result["v1_definition"]["indicators"][0]["params"]["length"] == 5
    assert result["v2_definition"]["indicators"][0]["params"]["length"] == 10


async def test_compare_unknown_version_404(client, auth_headers):
    resp = await client.post(
        f"{BASE}/strategies",
        json={"name": "Short lived", "underlying": "NIFTY", "definition": valid_definition()},
        headers=auth_headers,
    )
    strategy_id = resp.json()["id"]
    compare_resp = await client.get(
        f"{BASE}/strategies/{strategy_id}/compare?v1=1&v2=99", headers=auth_headers
    )
    assert compare_resp.status_code == 404
