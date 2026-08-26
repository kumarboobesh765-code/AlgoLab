"""Automation loop: evaluate a strategy's latest signal and route orders.

Bridges the quant engine and the execution layer:
  stored candles -> evaluate_definition -> last-bar entry/exit signal
    -> position-state machine -> OrderRequest -> OrderManager.submit_order

The OrderManager enforces every SEBI/risk guard (kill switch, notional caps,
OPS limiter) and honours confirm-mode staging, so automation inherits those
controls without duplicating them.

Position state is kept in-process (per user+strategy); this is a research
platform seam — persistent deployment state arrives with the multi-process
worker story.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.gateway import (
    Exchange,
    MockGateway,
    OrderRequest,
    OrderSide,
    OrderType,
    Segment,
)
from app.execution.oms import OrderManager, get_order_manager
from app.models import Strategy
from app.quant.engine import evaluate_definition
from app.quant.schema import StrategyDefinition
from app.services.candles import load_candles


class AutomationError(ValueError):
    pass


@dataclass
class AutomationState:
    strategy_id: uuid.UUID
    user_email: str
    broker: str = "mock"
    mode: str = "paper"  # paper | confirm | live
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_run_at: datetime | None = None
    runs: int = 0
    orders_placed: int = 0
    direction: str | None = None  # None | "long" | "short"
    last_message: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.user_email, str(self.state_strategy_id()))

    def state_strategy_id(self) -> uuid.UUID:
        return self.strategy_id

    def as_dict(self) -> dict:
        return {
            "strategy_id": str(self.strategy_id),
            "broker": self.broker,
            "mode": self.mode,
            "started_at": self.started_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "runs": self.runs,
            "orders_placed": self.orders_placed,
            "direction": self.direction,
            "last_message": self.last_message,
        }


_REGISTRY: dict[tuple[str, str], AutomationState] = {}


def list_automations(user_email: str) -> list[AutomationState]:
    return [s for k, s in _REGISTRY.items() if k[0] == user_email]


def get_automation(user_email: str, strategy_id: str) -> AutomationState | None:
    return _REGISTRY.get((user_email, strategy_id))


def stop_automation(user_email: str, strategy_id: str) -> bool:
    return _REGISTRY.pop((user_email, strategy_id), None) is not None


async def run_once(
    db: AsyncSession,
    user_email: str,
    strategy_id: uuid.UUID,
    *,
    lookback_days: int = 30,
) -> dict:
    """Evaluate the strategy's most recent stored bars and act on the signal."""
    row = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = row.scalars().first()
    if strategy is None:
        raise AutomationError("Strategy not found")
    if not strategy.definition:
        raise AutomationError("Strategy has no definition")

    state = _REGISTRY.get((user_email, str(strategy.id)))
    if state is None:
        raise AutomationError("Automation not started for this strategy")

    try:
        definition = StrategyDefinition.model_validate(strategy.definition)
    except Exception as exc:  # noqa: BLE001
        raise AutomationError(f"Invalid stored definition: {exc}") from exc

    end = datetime.now(UTC)
    start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    start = end - timedelta(days=lookback_days)

    candles = await load_candles(
        db, symbol=strategy.underlying.upper(), interval=definition.timeframe,
        start=start, end=end,
    )
    if len(candles) < 5:
        raise AutomationError(
            f"No stored candles for {strategy.underlying} {definition.timeframe} — ingest first"
        )

    result = evaluate_definition(definition, candles)
    entry_now = bool(result.entry_signals[-1])
    exit_now = bool(result.exit_signals[-1])

    mgr: OrderManager = get_order_manager(
        state.broker, {}, user=user_email,
    )
    if isinstance(mgr.gateway, MockGateway):
        await mgr.gateway.connect()

    actions: list[str] = []
    pos_cfg = definition.position

    def _order(side: str) -> OrderRequest:
        return OrderRequest(
            symbol=strategy.underlying.upper(),
            exchange=Exchange.NSE,
            segment=Segment.EQUITY,
            side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=max(int(pos_cfg.quantity), 1),
            price=0.0,
            tag=f"auto:{str(strategy.id)[:8]}",
        )

    # Exit first, then enter (stop-and-reverse friendly)
    if state.direction is not None and exit_now:
        resp = await mgr.submit_order(_order("SELL"))
        actions.append(f"EXIT:{resp.status.value}:{resp.message}")
        if resp.status.value not in ("REJECTED",):
            state.orders_placed += 1
            state.direction = None

    if state.direction is None and entry_now:
        side = "BUY" if pos_cfg.direction in ("long_only", "both") else "SELL"
        resp = await mgr.submit_order(_order(side))
        actions.append(f"{side}:{resp.status.value}:{resp.message}")
        if resp.status.value == "PENDING":
            state.direction = "long"  # staged; optimistic until confirmed/rejected
        elif resp.status.value not in ("REJECTED",):
            state.direction = "long" if side == "BUY" else "short"
            state.orders_placed += 1

    state.runs += 1
    state.last_run_at = datetime.now(UTC)
    state.last_message = "; ".join(actions) if actions else (
        f"no action (entry={entry_now}, exit={exit_now}, dir={state.direction})"
    )
    return {
        "symbol": strategy.underlying.upper(),
        "bars_evaluated": len(candles),
        "entry_signal": entry_now,
        "exit_signal": exit_now,
        "direction": state.direction,
        "actions": actions,
        "message": state.last_message,
    }


def start_automation(
    user_email: str,
    strategy_id: uuid.UUID,
    *,
    broker: str = "mock",
    mode: str = "paper",
) -> AutomationState:
    if mode not in ("paper", "confirm", "live"):
        raise AutomationError("mode must be paper|confirm|live")
    existing = _REGISTRY.get((user_email, str(strategy_id)))
    if existing:
        existing.broker = broker
        existing.mode = mode
        return existing
    st = AutomationState(strategy_id=strategy_id, user_email=user_email, broker=broker, mode=mode)
    if mode == "confirm":
        get_order_manager(broker, {}, user=user_email).confirm_required = True
    _REGISTRY[(user_email, str(strategy_id))] = st
    return st
