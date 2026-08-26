"""Tests for the execution confirm-mode gradient."""

import pytest

from app.execution.gateway import (
    Exchange,
    MockGateway,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Segment,
)
from app.execution.oms import OrderManager

BASE = "/api/v1/execution"


def _order() -> OrderRequest:
    return OrderRequest(
        symbol="NIFTY", exchange=Exchange.NSE, segment=Segment.EQUITY,
        side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=10, price=100.0,
    )


@pytest.mark.asyncio
async def test_confirm_mode_stages_instead_of_routing():
    gw = MockGateway({})
    await gw.connect()
    mgr = OrderManager(gw, user="confirm-test")
    mgr.confirm_required = True

    resp = await mgr.submit_order(_order())
    assert resp.status == OrderStatus.PENDING
    assert resp.order_id.startswith("PEND_")
    assert len(mgr.list_pending()) == 1

    out = await mgr.confirm_pending(resp.order_id)
    assert out.status == OrderStatus.COMPLETE
    assert mgr.list_pending() == []


@pytest.mark.asyncio
async def test_discard_removes_pending():
    gw = MockGateway({})
    await gw.connect()
    mgr = OrderManager(gw, user="discard-test")
    mgr.confirm_required = True

    resp = await mgr.submit_order(_order())
    assert mgr.discard_pending(resp.order_id) is True
    assert mgr.list_pending() == []
    # Double-discard fails cleanly
    assert mgr.discard_pending(resp.order_id) is False


@pytest.mark.asyncio
async def test_confirm_unknown_id_rejected():
    gw = MockGateway({})
    await gw.connect()
    mgr = OrderManager(gw, user="unknown-test")
    resp = await mgr.confirm_pending("PEND_nope")
    assert resp.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_normal_mode_unaffected_by_gate_flag():
    gw = MockGateway({})
    await gw.connect()
    mgr = OrderManager(gw, user="normal-test")
    mgr.confirm_required = False
    resp = await mgr.submit_order(_order())
    assert resp.status == OrderStatus.COMPLETE


@pytest.mark.asyncio
async def test_confirm_mode_api_flow(client, auth_headers):
    # Enable confirm mode via API
    r = await client.post(f"{BASE}/risk/confirm-mode?enabled=true&broker=mock", headers=auth_headers)
    assert r.status_code == 200

    place = await client.post(
        f"{BASE}/orders/place",
        json={"broker": "mock", "symbol": "NIFTY", "exchange": "NSE", "segment": "EQUITY",
              "side": "BUY", "order_type": "MARKET", "quantity": 10, "price": 100.0},
        headers=auth_headers,
    )
    assert place.status_code == 200
    body = place.json()
    assert body["status"] == "PENDING"
    pending_id = body["order_id"]

    listing = (await client.get(f"{BASE}/orders/pending/list?broker=mock", headers=auth_headers)).json()
    assert any(p["pending_id"] == pending_id for p in listing)

    confirmed = await client.post(f"{BASE}/orders/{pending_id}/confirm?broker=mock", headers=auth_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "COMPLETE"

    # Disable confirm mode again; orders route directly
    off = await client.post(f"{BASE}/risk/confirm-mode?enabled=false&broker=mock", headers=auth_headers)
    assert off.status_code == 200
