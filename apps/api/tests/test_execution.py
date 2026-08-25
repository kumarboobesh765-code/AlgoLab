"""Tests for Phase 10 execution: risk guards, algorithms, OMS, and API."""

from datetime import datetime, timedelta

import pytest

from app.execution.algorithms import ExecutionAlgo, build_schedule, pending_slices
from app.execution.gateway import (
    Exchange,
    MockGateway,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    Segment,
)
from app.execution.oms import OrderManager, reset_managers
from app.execution.risk import RiskConfig, RiskGuard, RiskViolation


def _req(qty=100, price=100.0, side=OrderSide.BUY, symbol="NIFTY"):
    return OrderRequest(
        symbol=symbol,
        exchange=Exchange.NSE,
        segment=Segment.EQUITY,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=qty,
        product=ProductType.MIS,
        price=price,
    )


# -- Risk guards -------------------------------------------------------------

def test_risk_pass_normal_order():
    guard = RiskGuard(RiskConfig(max_order_notional=1_000_000))
    viol = guard.check_order(_req(qty=100, price=1000), ref_price=1000)
    assert viol == []


def test_risk_block_kill_switch():
    guard = RiskGuard(RiskConfig(kill_switch=True))
    viol = guard.check_order(_req())
    assert any("Kill switch" in v for v in viol)


def test_risk_block_notional():
    guard = RiskGuard(RiskConfig(max_order_notional=10_000))
    viol = guard.check_order(_req(qty=1000, price=100))
    assert any("exceeds cap" in v for v in viol)


def test_risk_block_exchange():
    guard = RiskGuard(RiskConfig(allowed_exchanges={Exchange.NSE}))
    viol = guard.check_order(
        OrderRequest(symbol="X", exchange=Exchange.NCDEX, segment=Segment.COMMODITY,
                     side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    )
    assert any("not permitted" in v for v in viol)


def test_risk_block_daily_loss():
    guard = RiskGuard(RiskConfig(max_daily_loss=1000))
    viol = guard.check_order(_req(), daily_pnl=-2000)
    assert any("Daily loss" in v for v in viol)


def test_risk_require_safe_raises():
    guard = RiskGuard(RiskConfig(kill_switch=True))
    with pytest.raises(RiskViolation):
        guard.require_safe(_req())


# -- Algorithms --------------------------------------------------------------

def test_twap_schedule_sums_quantity():
    now = datetime(2024, 1, 1, 9, 15)
    end = now + timedelta(minutes=60)
    sched = build_schedule(ExecutionAlgo.TWAP, _req(qty=600), now, end, slices=6)
    assert len(sched) == 6
    assert sum(s.quantity for s in sched) == 600
    assert sched[0].scheduled_time == now
    assert sched[-1].scheduled_time == end


def test_vwap_schedule_respects_profile():
    now = datetime(2024, 1, 1, 9, 15)
    end = now + timedelta(minutes=30)
    profile = [1.0, 3.0, 1.0]  # middle slice should get most
    sched = build_schedule(ExecutionAlgo.VWAP, _req(qty=500), now, end, slices=3, volume_profile=profile)
    assert sum(s.quantity for s in sched) == 500
    assert sched[1].quantity > sched[0].quantity
    assert sched[1].quantity > sched[2].quantity


def test_tranche_schedule_with_jitter():
    now = datetime(2024, 1, 1, 9, 15)
    end = now + timedelta(minutes=30)
    sched = build_schedule(ExecutionAlgo.TRANCHE, _req(qty=300), now, end, slices=3, jitter_seconds=30)
    assert len(sched) == 3
    assert sum(s.quantity for s in sched) == 300


def test_pending_slices_filters_by_time():
    now = datetime(2024, 1, 1, 9, 15)
    end = now + timedelta(minutes=30)
    sched = build_schedule(ExecutionAlgo.TWAP, _req(qty=300), now, end, slices=3)
    due = pending_slices(sched, now + timedelta(minutes=5))
    assert len(due) == 1
    after = pending_slices(sched, end)
    assert len(after) == 3


# -- OMS ---------------------------------------------------------------------

@pytest.fixture
def manager():
    reset_managers()
    gw = MockGateway({})
    return OrderManager(gw, user="test@x.com")


async def test_oms_submit_order(manager):
    resp = await manager.submit_order(_req(qty=50, price=100))
    assert resp.status in (OrderStatus.OPEN, OrderStatus.COMPLETE)
    orders = await manager.get_orders()
    assert any(o.symbol == "NIFTY" for o in orders)


async def test_oms_kill_switch_blocks(manager):
    manager.set_kill_switch(True)
    with pytest.raises(RiskViolation):
        await manager.submit_order(_req())
    assert manager.get_risk_status()["kill_switch"] is True


async def test_oms_algo_tick_releases_slices(manager):
    now = datetime(2024, 1, 1, 9, 15)
    end = now + timedelta(minutes=30)
    parent = await manager.submit_algo(_req(qty=300, price=100), ExecutionAlgo.TWAP, now, end, slices=3)
    assert len(parent.schedule) == 3
    # No slices due yet
    released = await manager.tick_algos(now + timedelta(minutes=1))
    assert len(released) == 1
    # After end, all remaining released
    released2 = await manager.tick_algos(end + timedelta(seconds=1))
    assert len(released2) == 2
    orders = await manager.get_orders()
    assert sum(o.quantity for o in orders) == 300


async def test_oms_audit_trail(manager):
    await manager.submit_order(_req(qty=10, price=100))
    trail = manager.audit_trail
    assert any(e.action == "ORDER_PLACED" for e in trail)


# -- API ---------------------------------------------------------------------

async def test_list_brokers(client):
    resp = await client.get("/api/v1/execution/brokers")
    assert resp.status_code == 200
    assert "mock" in resp.json()
    assert "zerodha" in resp.json()


async def test_api_place_order(client, auth_headers):
    reset_managers()
    payload = {
        "broker": "mock",
        "symbol": "NIFTY",
        "exchange": "NSE",
        "segment": "EQUITY",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 25,
        "price": 100,
        "tag": "test",
    }
    resp = await client.post("/api/v1/execution/orders/place", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["filled_quantity"] + body["pending_quantity"] == 25


async def test_api_risk_rejects_kill(client, auth_headers):
    reset_managers()
    await client.post("/api/v1/execution/risk/kill?broker=mock&engaged=true", headers=auth_headers)
    payload = {
        "broker": "mock",
        "symbol": "NIFTY",
        "exchange": "NSE",
        "segment": "EQUITY",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 10,
    }
    resp = await client.post("/api/v1/execution/orders/place", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "risk_violations" in resp.json()["detail"]


async def test_api_funds_and_positions(client, auth_headers):
    reset_managers()
    f = await client.get("/api/v1/execution/funds?broker=mock", headers=auth_headers)
    assert f.status_code == 200
    assert f.json()["available_cash"] == 1000000
    p = await client.get("/api/v1/execution/positions?broker=mock", headers=auth_headers)
    assert p.status_code == 200
    assert p.json() == []


async def test_api_algo_and_tick(client, auth_headers):
    reset_managers()
    now = datetime(2024, 1, 1, 9, 15)
    end = now + timedelta(minutes=30)
    payload = {
        "broker": "mock",
        "symbol": "NIFTY",
        "exchange": "NSE",
        "segment": "EQUITY",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 300,
        "price": 100,
        "algo": "TWAP",
        "start": now.isoformat(),
        "end": end.isoformat(),
        "slices": 3,
    }
    resp = await client.post("/api/v1/execution/orders/algo", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total_slices"] == 3
    tick = await client.post("/api/v1/execution/orders/algo/tick?broker=mock", headers=auth_headers)
    assert tick.status_code == 200
    # Schedule dates are in the past relative to "now", so all 3 slices release.
    assert len(tick.json()) == 3
