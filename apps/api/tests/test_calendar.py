"""Tests for /calendar endpoints (holidays + cost calculator)."""

from datetime import date

import pytest

from app.services.market_calendar import (
    upcoming_expiries,
    validate_order_quantity,
)

BASE = "/api/v1"


@pytest.mark.asyncio
async def test_holidays_current_year(client, auth_headers):
    resp = await client.get(f"{BASE}/calendar/holidays?year=2025", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    dates = [h["date"] for h in data["holidays"]]
    assert "2025-08-15" in dates
    assert "2025-10-02" in dates
    for h in data["holidays"]:
        assert h["weekday"] in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@pytest.mark.asyncio
async def test_holidays_range_filter(client, auth_headers):
    resp = await client.get(
        f"{BASE}/calendar/holidays?start=2025-08-01&end=2025-12-31",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all("2025-08-01" <= h["date"] <= "2025-12-31" for h in data["holidays"])
    assert data["count"] >= 4


@pytest.mark.asyncio
async def test_costs_equity_delivery(client, auth_headers):
    payload = {
        "buy_value": 100000,
        "sell_value": 100000,
        "brokerage_per_order": 0.0,
        "segment": "equity",
        "product": "delivery",
    }
    resp = await client.post(f"{BASE}/calendar/costs", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    b = data["breakdown"]
    # STT delivery = 0.1% both sides = 200 on 1L + 1L turnover
    assert abs(b["stt"] - 200.0) < 1.0
    assert b["total"] > 200.0
    assert data["cost_pct_of_turnover"] > 0


@pytest.mark.asyncio
async def test_costs_options_sell_side_stt(client, auth_headers):
    payload = {
        "buy_value": 50000,
        "sell_value": 50000,
        "segment": "options",
        "product": "options",
    }
    resp = await client.post(f"{BASE}/calendar/costs", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Options STT is on sell premium only: 0.1% of 50k = 50
    assert abs(data["breakdown"]["stt"] - 50.0) < 1.0


@pytest.mark.asyncio
async def test_costs_requires_auth(client):
    resp = await client.post(
        f"{BASE}/calendar/costs",
        json={"buy_value": 1000, "sell_value": 1000},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_holidays_unauthenticated(client):
    resp = await client.get(f"{BASE}/calendar/holidays")
    assert resp.status_code in (401, 403)


# ---- service-level: expiries + lot validation ----


def test_nifty_weekly_expiries_are_tuesdays():
    days = upcoming_expiries("NIFTY", date(2026, 1, 1), count=4)
    assert len(days) == 4
    for d in days:
        assert d.weekday() == 1  # Tuesday


def test_banknifty_monthly_third_wednesday():
    days = upcoming_expiries("BANKNIFTY", date(2026, 8, 1), count=2)
    assert len(days) == 2
    # Third Wednesday convention
    for d in days:
        assert d.weekday() == 2  # Wednesday
        assert 15 <= d.day <= 21


def test_lot_size_validation():
    issues = validate_order_quantity("NIFTY", 100)  # lot 75 → not a multiple
    assert any("lot" in i.lower() for i in issues)
    ok = validate_order_quantity("NIFTY", 150)  # 2 lots of 75
    assert ok == []


def test_freeze_quantity_validation():
    issues = validate_order_quantity("NIFTY", 1875)  # 25 lots but > freeze 1800
    assert any("freeze" in i.lower() for i in issues)


def test_unknown_symbol_passes_through():
    assert validate_order_quantity("RELIANCE-JUN-FUT", 1) == []
