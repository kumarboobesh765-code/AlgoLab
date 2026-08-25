"""Execution API routes (Phase 10 — broker gateway / OMS / risk).

All mutating endpoints are enforced through the Order Management System, which
applies risk guards and writes a compliance audit trail before any order
reaches a broker.
"""

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser
from app.execution import list_brokers
from app.execution.gateway import OrderRequest, Validity
from app.execution.oms import get_order_manager
from app.execution.risk import RiskViolation
from app.schemas.execution import (
    AlgoOrderRequest,
    AlgoParentOut,
    AuditOut,
    FundsOut,
    OrderOut,
    PlaceOrderRequest,
    PositionOut,
    RiskStatusOut,
)

router = APIRouter(prefix="/execution", tags=["execution"])


def _broker_config(broker: str) -> dict:
    if broker == "zerodha":
        return {
            "api_key": os.environ.get("ZERODHA_API_KEY", ""),
            "access_token": os.environ.get("ZERODHA_ACCESS_TOKEN", ""),
        }
    return {}


def _to_order_request(req) -> OrderRequest:
    return OrderRequest(
        symbol=req.symbol,
        exchange=req.exchange,
        segment=req.segment,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        product=req.product,
        validity=getattr(req, "validity", Validity.DAY),
        price=req.price,
        trigger_price=req.trigger_price,
        disclosed_quantity=getattr(req, "disclosed_quantity", 0),
        tag=getattr(req, "tag", None) or getattr(req, "strategy_tag", None),
        is_amo=getattr(req, "is_amo", False),
    )


def _order_out(o) -> OrderOut:
    return OrderOut(
        order_id=o.order_id,
        broker_order_id=o.broker_order_id,
        symbol=o.symbol,
        exchange=o.exchange.value,
        segment=o.segment.value,
        side=o.side.value,
        order_type=o.order_type.value,
        product=o.product.value,
        quantity=o.quantity,
        price=o.price,
        trigger_price=o.trigger_price,
        filled_quantity=o.filled_quantity,
        pending_quantity=o.pending_quantity,
        status=o.status.value,
        average_price=o.average_price,
        tag=o.tag,
        rejection_reason=o.rejection_reason,
    )


@router.get("/brokers", response_model=list[str])
async def brokers() -> list[str]:
    return list_brokers()


@router.post("/orders/place", response_model=OrderOut)
async def place_order(req: PlaceOrderRequest, user: CurrentUser) -> OrderOut:
    mgr = get_order_manager(req.broker, _broker_config(req.broker), user=user.email)
    try:
        resp = await mgr.submit_order(_to_order_request(req), strategy_tag=req.strategy_tag)
    except RiskViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"risk_violations": exc.violations},
        ) from exc
    orders = await mgr.get_orders()
    match = next((o for o in orders if o.broker_order_id == resp.broker_order_id), None)
    if match is None:
        # Mock gateway stores locally; surface minimal info
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Order not mirrored")
    return _order_out(match)


@router.post("/orders/algo", response_model=AlgoParentOut)
async def place_algo(req: AlgoOrderRequest, user: CurrentUser) -> AlgoParentOut:
    mgr = get_order_manager(req.broker, _broker_config(req.broker), user=user.email)
    try:
        start = datetime.fromisoformat(req.start)
        end = datetime.fromisoformat(req.end)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start/end must be ISO datetimes",
        ) from exc
    parent = await mgr.submit_algo(
        request=_to_order_request(req),
        algo=req.algo,
        start=start,
        end=end,
        slices=req.slices,
        volume_profile=req.volume_profile,
        jitter_seconds=req.jitter_seconds,
        strategy_tag=req.tag,
    )
    released = sum(1 for s in parent.schedule if s.sent)
    return AlgoParentOut(
        parent_id=parent.parent_id,
        broker=parent.broker,
        symbol=parent.request.symbol,
        side=parent.request.side.value,
        quantity=parent.request.quantity,
        algo=parent.algo.value,
        total_slices=len(parent.schedule),
        released_slices=released,
    )


@router.post("/orders/algo/tick", response_model=list[OrderOut])
async def tick_algos(user: CurrentUser, broker: str = "mock") -> list[OrderOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    resps = await mgr.tick_algos()
    orders = await mgr.get_orders()
    by_id = {o.broker_order_id: o for o in orders}
    out = []
    for r in resps:
        o = by_id.get(r.broker_order_id)
        if o:
            out.append(_order_out(o))
    return out


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(order_id: str, user: CurrentUser, broker: str = "mock") -> OrderOut:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    await mgr.cancel_order(order_id)
    orders = await mgr.get_orders()
    match = next((o for o in orders if o.broker_order_id == order_id or o.order_id == order_id), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return _order_out(match)


@router.get("/orders", response_model=list[OrderOut])
async def get_orders(user: CurrentUser, broker: str = "mock") -> list[OrderOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    orders = await mgr.get_orders()
    return [_order_out(o) for o in orders]


@router.get("/positions", response_model=list[PositionOut])
async def get_positions(user: CurrentUser, broker: str = "mock") -> list[PositionOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    positions = await mgr.get_positions()
    return [
        PositionOut(
            symbol=p.symbol,
            exchange=p.exchange.value,
            segment=p.segment.value,
            product=p.product.value,
            side=p.side.value,
            quantity=p.quantity,
            average_price=p.average_price,
            last_price=p.last_price,
            unrealized_pnl=p.unrealized_pnl,
            realized_pnl=p.realized_pnl,
            value=p.value,
        )
        for p in positions
    ]


@router.get("/funds", response_model=FundsOut)
async def get_funds(user: CurrentUser, broker: str = "mock") -> FundsOut:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    f = await mgr.get_funds()
    return FundsOut(
        equity=f.equity,
        commodity=f.commodity,
        used_margin=f.used_margin,
        available_cash=f.available_cash,
        collateral=f.collateral,
    )


@router.get("/risk", response_model=RiskStatusOut)
async def risk_status(user: CurrentUser, broker: str = "mock") -> RiskStatusOut:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    s = mgr.get_risk_status()
    return RiskStatusOut(**s)


@router.post("/risk/kill", response_model=RiskStatusOut)
async def set_kill(broker: str, engaged: bool, user: CurrentUser) -> RiskStatusOut:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    mgr.set_kill_switch(engaged)
    return RiskStatusOut(**mgr.get_risk_status())


@router.get("/algos", response_model=list[AlgoParentOut])
async def list_algos(user: CurrentUser, broker: str = "mock") -> list[AlgoParentOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    out = []
    for p in mgr.list_algos():
        out.append(AlgoParentOut(
            parent_id=p.parent_id,
            broker=p.broker,
            symbol=p.request.symbol,
            side=p.request.side.value,
            quantity=p.request.quantity,
            algo=p.algo.value,
            total_slices=len(p.schedule),
            released_slices=sum(1 for s in p.schedule if s.sent),
        ))
    return out


@router.get("/audit", response_model=list[AuditOut])
async def audit_trail(user: CurrentUser, broker: str = "mock") -> list[AuditOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    return [
        AuditOut(
            timestamp=e.timestamp.isoformat(),
            action=e.action,
            detail=e.detail,
            broker_order_id=e.broker_order_id,
            user=e.user,
        )
        for e in mgr.audit_trail
    ]
