"""Risk guards for live order execution.

Pre-trade checks applied by the Order Management System before an order
reaches a broker. These enforce capital protection rules required for
SEBI-compliant algo trading:

- Global kill switch (instant block of all new orders)
- Per-order notional cap
- Per-symbol position notional cap
- Daily order count cap
- Daily realised + unrealised loss cap
- Allowed exchange / product whitelist
"""

from dataclasses import dataclass, field

from app.execution.gateway import (
    Exchange,
    Funds,
    OrderRequest,
    Position,
    ProductType,
)


@dataclass
class RiskConfig:
    """Configurable risk limits."""

    kill_switch: bool = False
    max_order_notional: float = 1_000_000.0
    max_position_notional: float = 5_000_000.0
    max_orders_per_day: int = 500
    max_daily_loss: float = 200_000.0
    allowed_exchanges: frozenset = field(
        default_factory=lambda: frozenset(
            {Exchange.NSE, Exchange.BSE, Exchange.NFO, Exchange.BFO, Exchange.MCX}
        )
    )
    allowed_products: frozenset = field(
        default_factory=lambda: frozenset(
            {ProductType.MIS, ProductType.NRML, ProductType.CNC}
        )
    )
    respect_kill_switch: bool = True


class RiskViolation(Exception):
    """Raised when an order breaches one or more risk limits."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))


class RiskGuard:
    """Stateless (config-driven) pre-trade risk checker."""

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def check_order(
        self,
        request: OrderRequest,
        funds: Funds | None = None,
        positions: list[Position] | None = None,
        orders_today: int = 0,
        daily_pnl: float = 0.0,
        ref_price: float | None = None,
    ) -> list[str]:
        """Validate an order. Returns a list of human-readable violations.

        An empty list means the order passes all checks.
        """
        violations: list[str] = []
        cfg = self.config

        if cfg.respect_kill_switch and cfg.kill_switch:
            violations.append("Kill switch is engaged — all new orders blocked")
            return violations

        # Exchange / product whitelist
        if request.exchange not in cfg.allowed_exchanges:
            violations.append(
                f"Exchange {request.exchange.value} not permitted (allowed: "
                f"{', '.join(e.value for e in cfg.allowed_exchanges)})"
            )
        if request.product not in cfg.allowed_products:
            violations.append(
                f"Product {request.product.value} not permitted (allowed: "
                f"{', '.join(p.value for p in cfg.allowed_products)})"
            )

        # Order notional cap
        price = request.price if request.price and request.price > 0 else (ref_price or 0.0)
        notional = price * request.quantity
        if price <= 0:
            violations.append("Cannot size order: no price and no reference price supplied")
        elif notional > cfg.max_order_notional:
            violations.append(
                f"Order notional {notional:,.0f} exceeds cap {cfg.max_order_notional:,.0f}"
            )

        # Daily order count cap
        if orders_today >= cfg.max_orders_per_day:
            violations.append(
                f"Daily order count {orders_today} reached cap {cfg.max_orders_per_day}"
            )

        # Daily loss cap
        if daily_pnl <= -cfg.max_daily_loss:
            violations.append(
                f"Daily loss {abs(daily_pnl):,.0f} reached cap {cfg.max_daily_loss:,.0f}"
            )

        # Per-symbol position notional cap
        if positions is not None and price > 0:
            existing = self._position_notional_for_symbol(positions, request.symbol)
            if request.side.value == "BUY":
                projected = existing + notional
            else:
                projected = existing - notional
            if abs(projected) > cfg.max_position_notional:
                violations.append(
                    f"Projected position notional {abs(projected):,.0f} on {request.symbol} "
                    f"exceeds cap {cfg.max_position_notional:,.0f}"
                )

        # Margin affordability
        if funds is not None and price > 0:
            if notional > funds.available_cash + funds.used_margin:
                violations.append(
                    f"Order notional {notional:,.0f} exceeds available margin "
                    f"{funds.available_cash + funds.used_margin:,.0f}"
                )

        return violations

    @staticmethod
    def _position_notional_for_symbol(positions: list[Position], symbol: str) -> float:
        total = 0.0
        for pos in positions:
            if pos.symbol == symbol:
                signed_qty = pos.quantity * (1 if pos.side.value == "BUY" else -1)
                total += signed_qty * pos.average_price
        return total

    def require_safe(
        self,
        request: OrderRequest,
        funds: Funds | None = None,
        positions: list[Position] | None = None,
        orders_today: int = 0,
        daily_pnl: float = 0.0,
        ref_price: float | None = None,
    ) -> None:
        """Like :meth:`check_order` but raise :class:`RiskViolation` on failure."""
        violations = self.check_order(
            request, funds, positions, orders_today, daily_pnl, ref_price
        )
        if violations:
            raise RiskViolation(violations)
