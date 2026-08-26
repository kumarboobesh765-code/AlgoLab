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
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Trade,
)
from app.execution.risk import RiskGuard, RiskViolation
from app.execution.sebi import RegisteredAlgo, get_algo_registry
from app.execution.stream import StreamManager, Tick
from app.execution.throttle import OTRTracker, get_rate_limiter


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


@dataclass
class BracketParent:
    parent_id: str
    entry_order_id: str
    target: OrderRequest
    stop: OrderRequest
    armed: bool = False
    done: bool = False


@dataclass
class PendingOrder:
    """An order staged for manual confirmation (Tradetron-style gradient)."""

    pending_id: str
    request: OrderRequest
    created_at: datetime = field(default_factory=datetime.now)
    ref_price: float | None = None
    strategy_tag: str | None = None


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
        self._brackets: dict[str, BracketParent] = {}
        self._ref_prices: dict[str, float] = {}
        self.stream = StreamManager()
        self.limiter = get_rate_limiter()  # SEBI OPS cap, shared per process
        self.otr = OTRTracker()
        self._counted_fills: dict[str, int] = {}
        self.confirm_required: bool = False
        self._pending: dict[str, PendingOrder] = {}

    # -- audit ---------------------------------------------------------------

    def _log(self, action: str, detail: str, broker_order_id: str = "") -> None:
        self._audit.append(
            AuditEntry(
                timestamp=datetime.now().astimezone(),  # tz-aware; µs precision
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
        status = {
            "kill_switch": cfg.kill_switch,
            "max_order_notional": cfg.max_order_notional,
            "max_position_notional": cfg.max_position_notional,
            "max_orders_per_day": cfg.max_orders_per_day,
            "orders_today": self._orders_today,
            "daily_pnl": round(self._daily_pnl, 2),
            "max_daily_loss": cfg.max_daily_loss,
            # SEBI compliance telemetry
            "ops_limit": self.limiter.max_ops,
            "ops_current": self.limiter.current_rate(self.user),
            "orders_placed": self.otr.orders_placed,
            "trades_executed": self.otr.trades_executed,
            "order_to_trade_ratio": self.otr.ratio,
        }
        if self.otr.is_excessive():
            status["otr_warning"] = (
                f"Order-to-trade ratio {self.otr.ratio} exceeds "
                f"{self.otr.warn_threshold} — exchanges may flag this account"
            )
        return status

    # -- order submission ----------------------------------------------------

    async def submit_order(
        self,
        request: OrderRequest,
        ref_price: float | None = None,
        strategy_tag: str | None = None,
        _confirmed: bool = False,
    ) -> OrderResponse:
        if not await self.gateway.is_connected():
            await self.gateway.connect()

        # Confirm-mode gate (Tradetron-style execution gradient): stage the
        # order for manual approval instead of routing it.
        if self.confirm_required and not _confirmed:
            pid = f"PEND_{uuid.uuid4().hex[:10]}"
            self._pending[pid] = PendingOrder(
                pending_id=pid, request=request, ref_price=ref_price,
                strategy_tag=strategy_tag,
            )
            self._log("ORDER_PENDING_CONFIRM", f"{request.side.value} {request.quantity} {request.symbol}", pid)
            return OrderResponse(
                order_id=pid,
                broker_order_id="",
                status=OrderStatus.PENDING,
                message=f"Order staged as {pid} — awaiting confirmation",
            )

        # Market orders have no price; fetch a reference price for sizing/risk.
        ref = ref_price
        if request.price <= 0:
            quote = await self.get_quote(request.symbol)
            if quote and quote.get("last_price"):
                ref = quote["last_price"]

        funds = await self._safe_funds()
        positions = await self._safe_positions()

        violations = self.risk.check_order(
            request,
            funds=funds,
            positions=positions,
            orders_today=self._orders_today,
            daily_pnl=self._daily_pnl,
            ref_price=ref,
        )
        if violations:
            self._log("ORDER_REJECTED_RISK", "; ".join(violations))
            raise RiskViolation(violations)

        # SEBI OPS cap: refuse submissions beyond the orders-per-second limit.
        if not self.limiter.allow(self.user):
            msg = (
                f"Order rate exceeds SEBI limit of {self.limiter.max_ops} "
                f"orders/second — slow down"
            )
            self._log("ORDER_REJECTED_OPS", msg)
            raise RiskViolation([msg])

        effective_tag = strategy_tag or request.tag
        if request.algo_id:
            effective_tag = f"{effective_tag or ''}|ALGO:{request.algo_id}".strip("|")
        req = request
        if effective_tag != request.tag or request.algo_id:
            req = OrderRequest(
                symbol=request.symbol,
                exchange=request.exchange,
                segment=request.segment,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                product=request.product,
                validity=request.validity,
                price=request.price,
                trigger_price=request.trigger_price,
                disclosed_quantity=request.disclosed_quantity,
                tag=effective_tag or None,
                is_amo=request.is_amo,
                algo_id=request.algo_id,
            )

        try:
            resp = await self.gateway.place_order(req)
        except Exception as exc:  # broker-level failure
            self._log("ORDER_FAILED", str(exc))
            raise

        if resp.status not in (OrderStatus.REJECTED,):
            self._orders_today += 1
            self.otr.record_order()
            self._log("ORDER_PLACED", f"{req.side.value} {req.quantity} {req.symbol}", resp.broker_order_id)
        return resp

    # -- confirm-mode management ----------------------------------------------

    def list_pending(self) -> list[PendingOrder]:
        return list(self._pending.values())

    async def confirm_pending(self, pending_id: str) -> OrderResponse:
        """Execute a staged order (bypasses the confirm gate exactly once)."""
        pending = self._pending.pop(pending_id, None)
        if pending is None:
            return OrderResponse(
                order_id=pending_id, broker_order_id="",
                status=OrderStatus.REJECTED, message="Unknown or already-handled pending order",
            )
        self._log("ORDER_CONFIRMED", f"{pending.request.side.value} {pending.request.quantity} {pending.request.symbol}", pending_id)
        return await self.submit_order(
            pending.request,
            ref_price=pending.ref_price,
            strategy_tag=pending.strategy_tag,
            _confirmed=True,
        )

    def discard_pending(self, pending_id: str) -> bool:
        pending = self._pending.pop(pending_id, None)
        if pending is None:
            return False
        self._log("ORDER_DISCARDED", f"{pending.request.side.value} {pending.request.quantity} {pending.request.symbol}", pending_id)
        return True

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

    # -- SEBI algo registration ----------------------------------------------

    def register_algo(
        self, name: str, segment: str, exchange: str, strategy_id: str | None = None
    ) -> RegisteredAlgo:
        algo = get_algo_registry().register(name, segment, exchange, strategy_id)
        self._log("ALGO_REGISTERED", f"{algo.algo_id} {name} ({segment}/{exchange})", algo.algo_id)
        return algo

    def list_registered_algos(self) -> list[RegisteredAlgo]:
        return get_algo_registry().list_algos()

    def deactivate_algo(self, algo_id: str) -> bool:
        ok = get_algo_registry().deactivate(algo_id)
        if ok:
            self._log("ALGO_DEACTIVATED", algo_id, algo_id)
        return ok

    # -- bracket / cover (OCO) orders ----------------------------------------

    async def submit_bracket_order(
        self,
        entry: OrderRequest,
        target_price: float,
        stop_loss_price: float,
        trailing_stop: float | None = None,
    ) -> BracketParent:
        """Place an entry, then auto-arm target + stop-loss on fill.

        The entry carries `entry.algo_id` (SEBI tag) when provided; child
        orders inherit it. Children are released by :meth:`process_fills`
        once the entry is filled.
        """
        resp = await self.submit_order(entry)
        exit_side = OrderSide.SELL if entry.side == OrderSide.BUY else OrderSide.BUY
        target = OrderRequest(
            symbol=entry.symbol,
            exchange=entry.exchange,
            segment=entry.segment,
            side=exit_side,
            order_type=OrderType.LIMIT,
            quantity=entry.quantity,
            product=entry.product,
            validity=entry.validity,
            price=target_price,
            tag=f"{entry.tag or ''}|TGT".strip("|"),
            algo_id=entry.algo_id,
        )
        stop = OrderRequest(
            symbol=entry.symbol,
            exchange=entry.exchange,
            segment=entry.segment,
            side=exit_side,
            order_type=OrderType.SL,
            quantity=entry.quantity,
            product=entry.product,
            validity=entry.validity,
            trigger_price=stop_loss_price,
            price=stop_loss_price,
            tag=f"{entry.tag or ''}|SL".strip("|"),
            algo_id=entry.algo_id,
        )
        parent = BracketParent(
            parent_id=f"BRK_{uuid.uuid4().hex[:10]}",
            entry_order_id=resp.broker_order_id,
            target=target,
            stop=stop,
        )
        self._brackets[parent.parent_id] = parent
        self._log("BRACKET_CREATED", f"entry {resp.broker_order_id} tgt {target_price} sl {stop_loss_price}", parent.parent_id)
        return parent

    async def submit_oco(
        self, entry: OrderRequest, target: OrderRequest, stop_loss: OrderRequest
    ) -> BracketParent:
        """Place an entry, then on fill place a one-cancels-other (target + SL)."""
        resp = await self.submit_order(entry)
        parent = BracketParent(
            parent_id=f"OCO_{uuid.uuid4().hex[:10]}",
            entry_order_id=resp.broker_order_id,
            target=target,
            stop=stop_loss,
        )
        self._brackets[parent.parent_id] = parent
        self._log("OCO_CREATED", f"entry {resp.broker_order_id}", parent.parent_id)
        return parent

    async def process_fills(self) -> list[OrderResponse]:
        """Arm bracket/OCO child orders once their entry is filled.

        Returns responses for any child orders placed during this pass.
        """
        placed: list[OrderResponse] = []
        for parent in list(self._brackets.values()):
            if parent.done or parent.armed:
                continue
            entry = await self.gateway.get_order_history(parent.entry_order_id)
            entry_order = entry[0] if entry else None
            if not entry_order or entry_order.filled_quantity <= 0:
                continue
            # Entry filled — release target + stop loss (one-cancels-other)
            ref = self._ref_prices.get(parent.target.symbol)
            try:
                tgt_resp = await self.submit_order(parent.target, ref_price=ref)
                placed.append(tgt_resp)
                sl_resp = await self.submit_order(parent.stop, ref_price=ref)
                placed.append(sl_resp)
                parent.armed = True
                parent.done = True
                self._log(
                    "BRACKET_ARMED",
                    f"target {parent.target.order_type.value} {parent.target.price} / "
                    f"SL {parent.stop.trigger_price}",
                    parent.parent_id,
                )
            except RiskViolation as exc:
                self._log("BRACKET_BLOCKED", "; ".join(exc.violations), parent.parent_id)
            except Exception as exc:
                self._log("BRACKET_FAILED", str(exc), parent.parent_id)
        return placed

    def list_brackets(self) -> list[BracketParent]:
        return list(self._brackets.values())

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
            # Count executions for OTR telemetry (idempotent per fill snapshot)
            if o.filled_quantity > 0:
                seen = self._counted_fills.get(o.broker_order_id, 0)
                if o.filled_quantity > seen:
                    self.otr.record_trade(o.filled_quantity - seen)
                    self._counted_fills[o.broker_order_id] = o.filled_quantity
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

    async def refresh_quotes(self, symbols: list[str]) -> list[Tick]:
        """Fetch latest quotes for symbols and publish them to the stream."""
        from app.execution.gateway import Exchange, Instrument, Segment

        instruments = [
            Instrument(
                symbol=s,
                exchange=Exchange.NSE,
                segment=Segment.EQUITY,
                security_id=s,
                token="",
                name=s,
            )
            for s in symbols
        ]
        try:
            data = await self.gateway.get_quote(instruments)
        except Exception:
            return list(self.stream.snapshot())
        ticks: list[Tick] = []
        for s in symbols:
            q = data.get(s)
            if not q:
                continue
            tick = Tick(
                symbol=s,
                last_price=float(q.get("last_price", 0)),
                bid=float(q.get("bid", 0)),
                ask=float(q.get("ask", 0)),
                volume=int(q.get("volume", 0)),
                oi=int(q.get("oi", 0)),
                change=float(q.get("change", 0)),
                change_pct=float(q.get("change_pct", 0)),
            )
            self.stream.publish(tick)
            ticks.append(tick)
        return ticks

    def latest_quotes(self) -> list[Tick]:
        return self.stream.snapshot()


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
