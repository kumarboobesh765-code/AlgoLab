"""Order Management System (OMS).

Sits on top of a :class:`BrokerGateway` and adds:

- Pre-trade risk enforcement (via :class:`RiskGuard`)
- Order lifecycle tracking (local mirror of broker orders)
- Position aggregation from the broker
- Parent/child execution-algorithm scheduling (TWAP/VWAP/Tranche)
- A compliance audit trail (SEBI algo-trading requirement)

The OMS is broker-agnostic: it only talks to the gateway interface.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.execution.algorithms import (
    ExecutionAlgo,
    OrderSlice,
    build_schedule,
    pending_slices,
)
from app.execution.gateway import (
    BrokerGateway,
    Funds,
    Order,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    Position,
    Trade,
)
from app.execution.risk import RiskGuard, RiskViolation


@dataclass
class AuditEntry:
    timestamp: datetime
    action: str
    detail: str
    broker_order_id: str = ""
    user: str = "system"


@dataclass
class AlgoParent:
    parent_id: str
    broker: str
    request: OrderRequest
    algo: ExecutionAlgo
    schedule: list[OrderSlice] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class OrderManager:
    """Stateful order manager bound to a single broker gateway."""

    def __init__(
        self,
        gateway: BrokerGateway,
        risk: RiskGuard | None = None,
        user: str = "system",
    ):
        self.gateway = gateway
        self.risk = risk or RiskGuard()
        self.user = user
        self._orders: dict[str, Order] = {}
        self._audit: list[AuditEntry] = []
        self._orders_today: int = 0
        self._daily_pnl: float = 0.0
        self._algos: dict[str, AlgoParent] = {}
        self._ref_prices: dict[str, float] = {}

    # -- audit ---------------------------------------------------------------

    def _log(self, action: str, detail: str, broker_order_id: str = "") -> None:
        self._audit.append(
            AuditEntry(
                timestamp=datetime.now(),
                action=action,
                detail=detail,
                broker_order_id=broker_order_id,
                user=self.user,
            )
        )

    @property
    def audit_trail(self) -> list[AuditEntry]:
        return list(self._audit)

    # -- risk config ---------------------------------------------------------

    def set_kill_switch(self, engaged: bool) -> None:
        self.risk.config.kill_switch = engaged
        self._log("KILL_SWITCH", f"engaged={engaged}")

    def get_risk_status(self) -> dict:
        cfg = self.risk.config
        return {
            "kill_switch": cfg.kill_switch,
            "max_order_notional": cfg.max_order_notional,
            "max_position_notional": cfg.max_position_notional,
            "max_orders_per_day": cfg.max_orders_per_day,
            "orders_today": self._orders_today,
            "daily_pnl": round(self._daily_pnl, 2),
            "max_daily_loss": cfg.max_daily_loss,
        }

    # -- order submission ----------------------------------------------------

    async def submit_order(
        self,
        request: OrderRequest,
        ref_price: float | None = None,
        strategy_tag: str | None = None,
    ) -> OrderResponse:
        if not await self.gateway.is_connected():
            await self.gateway.connect()

        funds = await self._safe_funds()
        positions = await self._safe_positions()

        violations = self.risk.check_order(
            request,
            funds=funds,
            positions=positions,
            orders_today=self._orders_today,
            daily_pnl=self._daily_pnl,
            ref_price=ref_price,
        )
        if violations:
            self._log("ORDER_REJECTED_RISK", "; ".join(violations))
            raise RiskViolation(violations)

        effective_tag = strategy_tag or request.tag
        req = request
        if effective_tag:
            req = OrderRequest(
                **{**request.__dict__, "tag": effective_tag}
            ) if not request.tag else request

        try:
            resp = await self.gateway.place_order(req)
        except Exception as exc:  # broker-level failure
            self._log("ORDER_FAILED", str(exc))
            raise

        if resp.status not in (OrderStatus.REJECTED,):
            self._orders_today += 1
            self._log("ORDER_PLACED", f"{req.side.value} {req.quantity} {req.symbol}", resp.broker_order_id)
        return resp

    # -- execution algorithms -------------------------------------------------

    async def submit_algo(
        self,
        request: OrderRequest,
        algo: ExecutionAlgo,
        start: datetime,
        end: datetime,
        slices: int = 10,
        volume_profile: list[float] | None = None,
        jitter_seconds: int = 0,
        strategy_tag: str | None = None,
    ) -> AlgoParent:
        parent_id = f"ALGO_{uuid.uuid4().hex[:10]}"
        tag = strategy_tag or request.tag or parent_id
        schedule = build_schedule(
            algo, request, start, end, slices, volume_profile, jitter_seconds, parent_tag=tag
        )
        parent = AlgoParent(parent_id=parent_id, broker=self.gateway.name, request=request, algo=algo, schedule=schedule)
        self._algos[parent_id] = parent
        self._log("ALGO_CREATED", f"{algo.value} {request.quantity} {request.symbol} -> {len(schedule)} slices", parent_id)
        return parent

    async def tick_algos(self, now: datetime | None = None) -> list[OrderResponse]:
        """Release any algo slices whose scheduled time has arrived."""
        now = now or datetime.now()
        released: list[OrderResponse] = []
        for parent in self._algos.values():
            for slice_ in pending_slices(parent.schedule, now):
                req = OrderRequest(
                    symbol=parent.request.symbol,
                    exchange=parent.request.exchange,
                    segment=parent.request.segment,
                    side=slice_.side,
                    order_type=slice_.order_type,
                    quantity=slice_.quantity,
                    product=parent.request.product,
                    validity=parent.request.validity,
                    price=slice_.price,
                    trigger_price=slice_.trigger_price,
                    tag=slice_.tag,
                )
                ref = self._ref_prices.get(parent.request.symbol)
                try:
                    resp = await self.submit_order(req, ref_price=ref)
                    slice_.sent = True
                    released.append(resp)
                except RiskViolation as exc:
                    self._log("ALGO_SLICE_BLOCKED", "; ".join(exc.violations), slice_.slice_id)
                except Exception as exc:
                    self._log("ALGO_SLICE_FAILED", str(exc), slice_.slice_id)
        return released

    def list_algos(self) -> list[AlgoParent]:
        return list(self._algos.values())

    # -- lifecycle passthroughs ----------------------------------------------

    async def cancel_order(self, order_id: str) -> OrderResponse:
        resp = await self.gateway.cancel_order(order_id)
        self._log("ORDER_CANCELLED", order_id, order_id)
        return resp

    async def modify_order(self, order_id: str, **kwargs) -> OrderResponse:
        resp = await self.gateway.modify_order(order_id, **kwargs)
        self._log("ORDER_MODIFIED", order_id, order_id)
        return resp

    async def refresh_orders(self) -> list[Order]:
        orders = await self.gateway.get_orders()
        for o in orders:
            self._orders[o.broker_order_id] = o
        return orders

    async def get_orders(self) -> list[Order]:
        return await self.refresh_orders()

    async def get_positions(self) -> list[Position]:
        return await self._safe_positions() or []

    async def get_funds(self) -> Funds:
        return await self._safe_funds() or Funds(equity=0, commodity=0, used_margin=0, available_cash=0)

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        return await self.gateway.get_trades(from_date, to_date)

    # -- helpers --------------------------------------------------------------

    async def _safe_funds(self) -> Funds | None:
        try:
            return await self.gateway.get_funds()
        except Exception:
            return None

    async def _safe_positions(self) -> list[Position] | None:
        try:
            return await self.gateway.get_positions()
        except Exception:
            return None

    def set_ref_price(self, symbol: str, price: float) -> None:
        self._ref_prices[symbol] = price

    async def get_quote(self, symbol: str) -> dict | None:
        try:
            from app.execution.gateway import Exchange, Instrument, Segment

            inst = Instrument(
                symbol=symbol,
                exchange=Exchange.NSE,
                segment=Segment.EQUITY,
                security_id=symbol,
                token="",
                name=symbol,
            )
            data = await self.gateway.get_quote([inst])
            return data.get(symbol)
        except Exception:
            return None


# -- per-broker manager registry (singletons across requests) ---------------

_MANAGERS: dict[str, OrderManager] = {}


def get_order_manager(broker: str, config: dict, user: str = "system") -> OrderManager:
    """Return (creating if needed) the singleton OrderManager for a broker."""
    from app.execution import get_broker_gateway

    key = f"{user}:{broker}"
    mgr = _MANAGERS.get(key)
    if mgr is None:
        gateway = get_broker_gateway(broker, config)
        mgr = OrderManager(gateway, user=user)
        _MANAGERS[key] = mgr
    return mgr


def reset_managers() -> None:
    """Clear all managers (used in tests)."""
    _MANAGERS.clear()
