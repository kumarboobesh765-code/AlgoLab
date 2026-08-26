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
    AlgoRegisterOut,
    AlgoRegisterRequest,
    AuditOut,
    BracketOrderRequest,
    BracketOut,
    DeploymentOut,
    DeployOut,
    DeployRequest,
    FundsOut,
    OrderOut,
    PlaceOrderRequest,
    PositionOut,
    RegisteredAlgoOut,
    RiskStatusOut,
    TickOut,
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


# -- SEBI algo registration --------------------------------------------------

@router.post("/algo/register", response_model=AlgoRegisterOut)
async def register_algo(req: AlgoRegisterRequest, user: CurrentUser) -> AlgoRegisterOut:
    mgr = get_order_manager("mock", {}, user=user.email)
    algo = mgr.register_algo(req.name, req.segment.value, req.exchange.value, req.strategy_id)
    return AlgoRegisterOut(
        algo_id=algo.algo_id,
        name=algo.name,
        segment=algo.segment,
        exchange=algo.exchange,
        strategy_id=algo.strategy_id,
        active=algo.active,
    )


@router.get("/algo/registered", response_model=list[RegisteredAlgoOut])
async def registered_algos(user: CurrentUser) -> list[RegisteredAlgoOut]:
    mgr = get_order_manager("mock", {}, user=user.email)
    return [
        RegisteredAlgoOut(
            algo_id=a.algo_id,
            name=a.name,
            segment=a.segment,
            exchange=a.exchange,
            strategy_id=a.strategy_id,
            active=a.active,
            registered_at=a.registered_at.isoformat(),
        )
        for a in mgr.list_registered_algos()
    ]


@router.post("/algo/deactivate", response_model=dict)
async def deactivate_algo(algo_id: str, user: CurrentUser) -> dict:
    mgr = get_order_manager("mock", {}, user=user.email)
    ok = mgr.deactivate_algo(algo_id)
    return {"algo_id": algo_id, "deactivated": ok}


# -- bracket / cover (OCO) orders -------------------------------------------

@router.post("/orders/bracket", response_model=BracketOut)
async def place_bracket(req: BracketOrderRequest, user: CurrentUser) -> BracketOut:
    mgr = get_order_manager(req.broker, _broker_config(req.broker), user=user.email)
    entry = OrderRequest(
        symbol=req.symbol,
        exchange=req.exchange,
        segment=req.segment,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        product=req.product,
        price=req.price,
        trigger_price=req.trigger_price,
        tag=req.tag,
        algo_id=req.algo_id,
    )
    try:
        parent = await mgr.submit_bracket_order(entry, req.target_price, req.stop_loss_price, req.trailing_stop)
    except RiskViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"risk_violations": exc.violations},
        ) from exc
    return BracketOut(
        bracket_id=parent.parent_id,
        entry_order_id=parent.entry_order_id,
        target_price=req.target_price,
        stop_loss_price=req.stop_loss_price,
        armed=parent.armed,
        done=parent.done,
    )


@router.post("/orders/process-fills", response_model=list[OrderOut])
async def process_fills(user: CurrentUser, broker: str = "mock") -> list[OrderOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    resps = await mgr.process_fills()
    orders = await mgr.get_orders()
    by_id = {o.broker_order_id: o for o in orders}
    out = []
    for r in resps:
        o = by_id.get(r.broker_order_id)
        if o:
            out.append(_order_out(o))
    return out


@router.get("/brackets", response_model=list[BracketOut])
async def list_brackets(user: CurrentUser, broker: str = "mock") -> list[BracketOut]:
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    out = []
    for b in mgr.list_brackets():
        out.append(BracketOut(
            bracket_id=b.parent_id,
            entry_order_id=b.entry_order_id,
            target_price=b.target.price,
            stop_loss_price=b.stop.trigger_price,
            armed=b.armed,
            done=b.done,
        ))
    return out


@router.get("/quotes", response_model=list[TickOut])
async def live_quotes(user: CurrentUser, symbols: str = "", broker: str = "mock") -> list[TickOut]:
    """Fetch latest quotes for a comma-separated watchlist and publish to the stream."""
    mgr = get_order_manager(broker, _broker_config(broker), user=user.email)
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    ticks = await mgr.refresh_quotes(syms)
    return [TickOut(**t.__dict__) for t in ticks]


# -- strategy -> live execution deployment seam -----------------------------

@router.post("/deploy", response_model=DeployOut)
async def deploy_strategy(req: DeployRequest, user: CurrentUser) -> DeployOut:
    """Register a strategy as a SEBI algo and link it to a broker (paper/live)."""
    from app.execution.deploy import get_deployment_registry

    reg = get_deployment_registry()
    dep = reg.deploy(
        strategy_id=req.strategy_id,
        broker=req.broker,
        mode=req.mode,
        name=req.name,
        segment=req.segment,
        exchange=req.exchange,
    )
    mgr = get_order_manager(req.broker, _broker_config(req.broker), user=user.email)
    mgr._log("DEPLOY", f"{req.mode} {req.strategy_id} -> {dep.algo_id} ({req.broker})", dep.algo_id)
    return DeployOut(
        deployment_id=dep.deployment_id,
        strategy_id=dep.strategy_id,
        algo_id=dep.algo_id,
        broker=dep.broker,
        mode=dep.mode,
        name=dep.name,
        active=dep.active,
    )


@router.get("/deployments", response_model=list[DeploymentOut])
async def list_deployments(user: CurrentUser) -> list[DeploymentOut]:
    from app.execution.deploy import get_deployment_registry

    reg = get_deployment_registry()
    return [
        DeploymentOut(
            deployment_id=d.deployment_id,
            strategy_id=d.strategy_id,
            algo_id=d.algo_id,
            broker=d.broker,
            mode=d.mode,
            name=d.name,
            segment=d.segment,
            exchange=d.exchange,
            active=d.active,
            created_at=d.created_at.isoformat(),
        )
        for d in reg.list_deployments()
    ]
