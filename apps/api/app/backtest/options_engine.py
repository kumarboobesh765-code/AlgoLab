"""Options backtest engine.

Simulates multi-leg options strategies over historical candles with:
- Black-Scholes pricing for entry/exit marks
- Greeks tracking
- Assignment/exercise logic at expiry
- Auto-rollover for calendar spreads
- Indian F&O cost structure (STT, brokerage, etc.)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.marketdata.base import Candle
from app.quant.options import (
    black_scholes_price,
    days_to_expiry,
    get_monthly_expiry,
    get_weekly_expiry,
    parse_strike_formula,
)
from app.quant.schema import StrategyDefinition


class OptionsBacktestError(ValueError):
    """Raised for invalid options backtest inputs."""


@dataclass(slots=True)
class OptionsLegPnL:
    """P&L tracking for a single option leg."""

    leg_index: int
    action: str  # "buy" | "sell"
    option_type: str  # "CE" | "PE"
    strike: float
    expiry: date
    lots: int
    entry_price: float
    entry_date: date
    current_price: float
    current_date: date
    days_held: int
    gross_pnl: float
    costs: dict[str, float]
    net_pnl: float
    exit_reason: str | None = None


@dataclass(slots=True)
class OptionsBacktestResult:
    """Complete options backtest result."""

    legs: list[OptionsLegPnL]
    daily_values: list[dict]  # Daily MTM
    summary: dict
    cost_breakdown: dict[str, float]


@dataclass(slots=True)
class OptionsConfig:
    """Options backtest configuration."""

    initial_capital: float = 100_000.0
    volatility: float = 0.20  # Implied volatility assumption
    rate: float = 0.06  # Risk-free rate
    dividend_yield: float = 0.012  # Index dividend yield
    lot_size: int = 50  # NIFTY lot size
    strike_interval: float = 50.0  # NIFTY strike interval
    auto_roll: bool = True  # Auto-roll expiring positions


def _leg_costs(price: float, qty: float, is_sell: bool, trade_date: date | None = None) -> dict:
    """Indian F&O per-fill cost breakdown (INR).

    STT applies on the sell side only — date-aware per Budget 2026:
    0.10% of premium before Apr 1 2026, 0.15% on/after.
    """
    from app.services.market_calendar import stt_options_sell

    d = trade_date or date.today()
    notional = abs(qty) * price
    stt = stt_options_sell(notional, d) if is_sell else 0.0
    stamp = 0.0003 * notional
    exchange = 0.0005 * notional
    sebi = 0.000001 * notional
    brokerage = 20.0
    gst = 0.18 * (brokerage + exchange + sebi)
    return {"stt": stt, "stamp": stamp, "exchange": exchange, "sebi": sebi, "brokerage": brokerage, "gst": gst}


def _resolve_expiry(expiry_formula: str, reference_date: date) -> date:
    """Resolve expiry formula to actual date."""
    formula = expiry_formula.strip().upper() if expiry_formula else "THIS_WEEK"
    if formula in ("THIS_WEEK", "WEEKLY"):
        return get_weekly_expiry(reference_date)
    if formula == "NEXT_WEEK":
        this_week = get_weekly_expiry(reference_date)
        from datetime import timedelta
        next_week = this_week + timedelta(days=7)
        while next_week.weekday() >= 5:
            next_week += timedelta(days=1)
        return next_week
    if formula in ("THIS_MONTH", "MONTHLY"):
        return get_monthly_expiry(reference_date)
    if formula == "NEXT_MONTH":
        from datetime import timedelta
        next_month = reference_date.month + 1 if reference_date.month < 12 else 1
        next_year = reference_date.year if reference_date.month < 12 else reference_date.year + 1
        return get_monthly_expiry(date(next_year, next_month, 1))
    try:
        return date.fromisoformat(formula)
    except ValueError:
        return get_weekly_expiry(reference_date)


def _resolve_strike(strike_formula: str, spot: float, strike_interval: float,
                     days_to_expiry: float, volatility: float, option_type: str) -> float:
    """Resolve strike formula to actual strike price."""
    result = parse_strike_formula(
        strike_formula,
        spot,
        strike_interval,
        days_to_expiry,
        volatility,
        option_type=option_type,
    )
    return result.strike


def _calculate_leg_price(spot: float, strike: float, days_to_exp: float,
                          volatility: float, option_type: str, is_entry: bool = True) -> float:
    """Calculate option leg price with bid-ask spread."""
    price = black_scholes_price(
        spot, strike, days_to_exp, volatility,
        rate=0.06, dividend_yield=0.012, option_type=option_type
    )
    # Add simulated spread
    spread = price * 0.01  # 1% spread
    if is_entry:
        return price + spread / 2  # Buy at ask
    else:
        return price - spread / 2  # Sell at bid


def run_options_backtest(
    definition: StrategyDefinition,
    candles: Sequence[Candle],
    config: OptionsConfig | None = None,
    leg_premium_lookup: list[dict[date, float]] | None = None,
) -> OptionsBacktestResult:
    """Run backtest for options strategy.

    Args:
        definition: Strategy definition with legs
        candles: Historical underlying candles
        config: Options backtest configuration
        leg_premium_lookup: Optional per-leg {date -> real premium close} maps
            (from expired-options history). When present for a leg/date, real
            traded premiums mark the position; Black-Scholes is the fallback.

    Returns:
        OptionsBacktestResult with leg P&L and summary
    """
    cfg = config or OptionsConfig()
    lookup = leg_premium_lookup or []

    def _real(j: int, d: date) -> float | None:
        if j < len(lookup) and lookup[j]:
            return lookup[j].get(d)
        return None

    if len(candles) < 2:
        raise OptionsBacktestError("Need at least 2 candles")

    if not definition.legs:
        raise OptionsBacktestError("Strategy must have at least one leg")

    # Get spot price series from candles
    spot_prices = [c.close for c in candles]
    timestamps = [c.timestamp for c in candles]

    # Initialize legs
    legs = []
    for i, leg_def in enumerate(definition.legs):
        leg = {
            "action": leg_def.action,
            "option_type": leg_def.option_type,
            "strike_formula": leg_def.strike_formula or "ATM",
            "lots": leg_def.lots,
            "lots_formula": leg_def.lots_formula,
            "expiry_formula": leg_def.expiry_formula or "THIS_WEEK",
            "strike": leg_def.strike,
            "expiry": date.fromisoformat(leg_def.expiry) if leg_def.expiry else None,
        }
        legs.append(leg)

    # Resolve initial strikes and expiries
    resolved_legs = []
    for leg in legs:
        ref_date = timestamps[0].date() if hasattr(timestamps[0], 'date') else date.today()
        expiry = leg["expiry"] or _resolve_expiry(leg["expiry_formula"], ref_date)
        strike = leg["strike"] or _resolve_strike(
            leg["strike_formula"], spot_prices[0], cfg.strike_interval,
            days_to_expiry(ref_date, expiry), cfg.volatility, leg["option_type"]
        )
        resolved_legs.append({
            **leg,
            "strike": strike,
            "expiry": expiry,
        })

    # Simulate each bar
    leg_pnls: list[OptionsLegPnL] = []
    leg_entries = [None] * len(resolved_legs)
    daily_values = []

    for i, (ts, spot) in enumerate(zip(timestamps, spot_prices)):
        current_date = ts.date() if hasattr(ts, 'date') else date.today()

        # Check for expiry and rollover
        for j, leg in enumerate(resolved_legs):
            if leg_entries[j] is not None:
                entry = leg_entries[j]
                if current_date >= entry["expiry"]:
                    # Exercise/assignment at expiry
                    entry_price = entry["price"]
                    intrinsic = max(spot - entry["strike"], 0) if entry["option_type"] == "CE" else max(entry["strike"] - spot, 0)
                    exit_price = intrinsic

                    qty = entry["lots"] * cfg.lot_size
                    if entry["action"] == "sell":
                        gross_pnl = (entry_price - exit_price) * qty
                    else:
                        gross_pnl = (exit_price - entry_price) * qty

                    costs = _leg_costs(exit_price, qty, is_sell=True)
                    total_costs = sum(costs.values())
                    net_pnl = gross_pnl - total_costs

                    leg_pnls.append(OptionsLegPnL(
                        leg_index=j,
                        action=entry["action"],
                        option_type=entry["option_type"],
                        strike=entry["strike"],
                        expiry=entry["expiry"],
                        lots=entry["lots"],
                        entry_price=entry_price,
                        entry_date=entry["entry_date"],
                        current_price=exit_price,
                        current_date=current_date,
                        days_held=(current_date - entry["entry_date"]).days,
                        gross_pnl=gross_pnl,
                        costs=costs,
                        net_pnl=net_pnl,
                        exit_reason="expiry",
                    ))

                    # Rollover if enabled
                    if cfg.auto_roll:
                        new_expiry = _resolve_expiry(entry["expiry_formula"], current_date)
                        new_dte = days_to_expiry(current_date, new_expiry)
                        new_strike = _resolve_strike(
                            entry["strike_formula"], spot, cfg.strike_interval,
                            new_dte, cfg.volatility, entry["option_type"]
                        )
                        new_price = _calculate_leg_price(spot, new_strike, new_dte, cfg.volatility, entry["option_type"])
                        leg_entries[j] = {
                            **entry,
                            "strike": new_strike,
                            "expiry": new_expiry,
                            "price": new_price,
                            "entry_date": current_date,
                            "entry_price": new_price,
                        }
                    else:
                        leg_entries[j] = None

        # Enter all legs at the start of the simulation
        if i == 0:
            for j, leg in enumerate(resolved_legs):
                if leg_entries[j] is None:
                    dte = days_to_expiry(current_date, leg["expiry"])
                    real = _real(j, current_date)
                    price = real if real is not None else _calculate_leg_price(
                        spot, leg["strike"], dte, cfg.volatility, leg["option_type"]
                    )
                    leg_entries[j] = {
                        "action": resolved_legs[j]["action"],
                        "option_type": resolved_legs[j]["option_type"],
                        "strike": resolved_legs[j]["strike"],
                        "strike_formula": resolved_legs[j]["strike_formula"],
                        "expiry": resolved_legs[j]["expiry"],
                        "expiry_formula": resolved_legs[j]["expiry_formula"],
                        "lots": resolved_legs[j]["lots"],
                        "price": price,
                        "entry_date": current_date,
                        "entry_price": price,
                    }

        # Daily MTM
        daily_mtm = 0.0
        for j, entry in enumerate(leg_entries):
            if entry is not None:
                dte = days_to_expiry(current_date, entry["expiry"])
                real = _real(j, current_date)
                current_price = (
                    real if real is not None
                    else black_scholes_price(
                        spot, entry["strike"], dte, cfg.volatility,
                        rate=0.06, dividend_yield=0.012, option_type=entry["option_type"]
                    )
                )
                qty = entry["lots"] * cfg.lot_size
                if entry["action"] == "sell":
                    daily_mtm += (entry["price"] - current_price) * qty
                else:
                    daily_mtm += (current_price - entry["price"]) * qty

        daily_values.append({
            "date": current_date.isoformat(),
            "spot": spot,
            "mtm": round(daily_mtm, 2),
            "legs_open": sum(1 for e in leg_entries if e is not None),
        })

    # Close any remaining positions
    for j, entry in enumerate(leg_entries):
        if entry is not None:
            final_spot = spot_prices[-1]
            final_date = timestamps[-1].date() if hasattr(timestamps[-1], 'date') else date.today()
            dte = days_to_expiry(final_date, entry["expiry"])
            real = _real(j, final_date)
            exit_price = (
                real if real is not None
                else black_scholes_price(
                    final_spot, entry["strike"], dte, cfg.volatility,
                    rate=0.06, dividend_yield=0.012, option_type=entry["option_type"]
                )
            )
            qty = entry["lots"] * cfg.lot_size
            if entry["action"] == "sell":
                gross_pnl = (entry["price"] - exit_price) * qty
            else:
                gross_pnl = (exit_price - entry["price"]) * qty
            costs = _leg_costs(exit_price, qty, is_sell=True)
            total_costs = sum(costs.values())
            net_pnl = gross_pnl - total_costs
            leg_pnls.append(OptionsLegPnL(
                leg_index=j,
                action=entry["action"],
                option_type=entry["option_type"],
                strike=entry["strike"],
                expiry=entry["expiry"],
                lots=entry["lots"],
                entry_price=entry["price"],
                entry_date=entry["entry_date"],
                current_price=exit_price,
                current_date=final_date,
                days_held=(final_date - entry["entry_date"]).days,
                gross_pnl=gross_pnl,
                costs=costs,
                net_pnl=net_pnl,
                exit_reason="end_of_data",
            ))

    # Build summary
    summary = _build_options_summary(leg_pnls, daily_values, cfg)
    cost_breakdown = _build_cost_breakdown(leg_pnls)

    return OptionsBacktestResult(
        legs=leg_pnls,
        daily_values=daily_values,
        summary=summary,
        cost_breakdown=cost_breakdown,
    )


def _build_options_summary(legs: list[OptionsLegPnL], daily_values: list[dict], cfg: OptionsConfig) -> dict:
    """Build summary statistics for options backtest."""
    if not legs:
        return {}

    total_gross_pnl = sum(leg.gross_pnl for leg in legs)
    total_net_pnl = sum(leg.net_pnl for leg in legs)
    total_costs = sum(sum(leg.costs.values()) for leg in legs)
    wins = [leg for leg in legs if leg.net_pnl > 0]
    losses = [leg for leg in legs if leg.net_pnl <= 0]

    # Daily equity curve
    equity = [cfg.initial_capital]
    for dv in daily_values:
        equity.append(equity[-1] + dv["mtm"])
    equity_peak = max(equity) if equity else cfg.initial_capital
    max_dd = max((equity_peak - e) / equity_peak * 100 for e in equity) if equity else 0.0

    return {
        "initial_capital": cfg.initial_capital,
        "final_equity": round(equity[-1], 2) if equity else cfg.initial_capital,
        "net_pnl": round(total_net_pnl, 2),
        "gross_pnl": round(total_gross_pnl, 2),
        "return_pct": round(total_net_pnl / cfg.initial_capital * 100, 2),
        "total_legs": len(legs),
        "winning_legs": len(wins),
        "losing_legs": len(losses),
        "win_rate": round(len(wins) / len(legs) * 100, 2) if legs else 0,
        "avg_win": round(sum(leg.net_pnl for leg in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(abs(sum(leg.net_pnl for leg in losses) / len(losses)), 2) if losses else 0,
        "max_drawdown_pct": round(max_dd, 2),
        "total_costs": round(total_costs, 2),
        "volatility_assumption": cfg.volatility,
    }


def _build_cost_breakdown(legs: list[OptionsLegPnL]) -> dict[str, float]:
    """Aggregate cost breakdown across all legs."""
    totals: dict[str, float] = {}
    for leg in legs:
        for key, value in leg.costs.items():
            totals[key] = totals.get(key, 0.0) + value
    return {k: round(v, 2) for k, v in totals.items()}


def run_options_backtest_quick(
    legs: list[dict],
    candles: Sequence[Candle],
    config: OptionsConfig | None = None,
) -> OptionsBacktestResult:
    """Quick backtest for options legs without full strategy definition.

    Args:
        legs: List of leg dicts with action, option_type, strike, lots
        candles: Historical underlying candles
        config: Options backtest configuration

    Returns:
        OptionsBacktestResult
    """
    from app.quant.schema import InstrumentRef, OptionLeg, PositionConfig, StrategyDefinition

    leg_models = [
        OptionLeg(
            action=leg.get("action", "buy"),
            option_type=leg.get("option_type", "CE"),
            strike=leg.get("strike"),
            strike_formula=leg.get("strike_formula", "ATM"),
            lots=leg.get("lots", 1),
            expiry_formula=leg.get("expiry_formula", "THIS_WEEK"),
        )
        for leg in legs
    ]

    definition = StrategyDefinition(
        version=1,
        timeframe="1d",
        instrument=InstrumentRef(symbol="NIFTY", exchange="NSE", segment="index"),
        legs=leg_models,
        entry={"logic": "ALL", "conditions": [{"left": {"kind": "constant", "value": 1}, "op": ">", "right": {"kind": "constant", "value": 0}}]},
        position=PositionConfig(direction="both"),
    )

    cfg = config or OptionsConfig()
    return run_options_backtest(definition, candles, cfg)
