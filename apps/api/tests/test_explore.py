"""Tests for /strategies/explore (prebuilt algo gallery)."""

import pytest

from app.templates import CATALOG

BASE = "/api/v1/strategies"


def test_catalog_definitions_all_valid():
    from app.quant.schema import validate_definition

    assert len(CATALOG) >= 30
    for algo in CATALOG:
        errs, _ = validate_definition(algo["definition"])
        assert not errs, f"{algo['id']}: {errs}"


@pytest.mark.asyncio
async def test_explore_endpoint_shape(client, auth_headers):
    resp = await client.get(f"{BASE}/explore", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 30
    ids = [c["id"] for c in data["categories"]]
    assert {"all", "option-buying", "credit-spread", "short-straddle"} <= set(ids)
    required = {"id", "name", "category", "description", "complexity", "min_capital", "definition"}
    assert all(required <= set(a) for a in data["algos"])


@pytest.mark.asyncio
async def test_explore_category_filter(client, auth_headers):
    resp = await client.get(f"{BASE}/explore?category=credit-spread", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert all(a["category"] == "credit-spread" for a in data["algos"])
