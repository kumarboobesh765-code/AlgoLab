"""Tests for SEBI retail-algo compliance guards (OPS limiter, IP whitelist, OTR)."""

import pytest

from app.execution.gateway import (
    Exchange,
    MockGateway,
    OrderRequest,
    OrderSide,
    OrderType,
    Segment,
)
from app.execution.oms import OrderManager
from app.execution.throttle import OrderRateLimiter, OTRTracker

BASE = "/api/v1/execution"


def _order(symbol: str = "NIFTY") -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        exchange=Exchange.NSE,
        segment=Segment.EQUITY,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=100.0,
    )


# ---- unit: rate limiter ----


def test_limiter_allows_up_to_max_then_blocks():
    lim = OrderRateLimiter(max_ops=3)
    assert all(lim.allow("u", now=t) for t in (0.0, 0.1, 0.2))
    assert not lim.allow("u", now=0.3)  # 4th within the same second


def test_limiter_window_slides():
    lim = OrderRateLimiter(max_ops=2, window_seconds=1.0)
    assert lim.allow("u", now=0.0)
    assert lim.allow("u", now=0.5)
    assert not lim.allow("u", now=0.9)
    assert lim.allow("u", now=1.6)  # both earlier orders aged out


def test_limiter_keys_are_isolated():
    lim = OrderRateLimiter(max_ops=1)
    assert lim.allow("alice", now=0.0)
    assert lim.allow("bob", now=0.0)
    assert not lim.allow("alice", now=0.1)


def test_otr_ratio_and_warning():
    otr = OTRTracker()
    assert otr.ratio is None
    for _ in range(10):
        otr.record_order()
    assert not otr.is_excessive()
    otr.record_trade(10)
    assert otr.ratio == 1.0
    assert not otr.is_excessive()
    hot = OTRTracker()
    for _ in range(30):
        hot.record_order()
    hot.record_trade(1)
    assert hot.is_excessive()


# ---- integration: OPS gate in the OMS ----


@pytest.mark.asyncio
async def test_oms_blocks_beyond_ops_limit():
    gw = MockGateway({})
    await gw.connect()
    mgr = OrderManager(gw, user="ops-test")
    # Default limit is 10/s; fire 12 rapid orders — the 11th must raise.
    placed = 0
    blocked = False
    for _ in range(12):
        try:
            resp = await mgr.submit_order(_order())
            if resp.status.value == "REJECTED":
                continue
            placed += 1
        except Exception as exc:
            assert "orders/second" in str(exc).lower() or "rate" in str(exc).lower()
            blocked = True
            break
    assert blocked, "OPS limiter never engaged"
    assert placed <= 10
    actions = [a.action for a in mgr.audit_trail]
    assert "ORDER_REJECTED_OPS" in actions


@pytest.mark.asyncio
async def test_risk_status_includes_sebi_telemetry(client, auth_headers):
    resp = await client.get(f"{BASE}/risk?broker=mock", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ops_limit"] == 10
    assert "orders_placed" in data and "trades_executed" in data
    assert "order_to_trade_ratio" in data
