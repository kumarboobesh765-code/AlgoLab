"""Backtest engine.

Simulates a canonical strategy definition over historical candles:

- signals are evaluated on bar close, executed at the NEXT bar's open
  (no same-bar lookahead);
- risk exits (stop loss / target / trailing stop) fill intrabar with
  gap-aware prices; when both stop and target are touched inside one bar,
  the stop is assumed to hit first (pessimistic);
- costs (brokerage/slippage) are charged per side as % of traded value;
- open positions are force-closed at the last bar's close (`end_of_data`);
- `direction: both` runs stop-and-reverse — an exit signal closes the long
  and opens a short on the same next-bar open.

The engine is pure: definition + candles + config in, trades/equity/summary
out. No DB, no IO — the API layer owns persistence.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.marketdata.base import Candle
from app.quant.engine import evaluate_definition
from app.quant.schema import StrategyDefinition

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 375}


def _leg_costs(price: float, qty: float, is_sell: bool) -> dict:
    """Indian F&O per-fill cost breakdown (INR).

    STT applies on the sell side only (0.0625% of premium, post Oct-2024).
    Exchange txn charge ~0.05% of premium, SEBI ~0.0001% of turnover,
    stamp duty ~0.03% of premium, flat brokerage per order, GST 18% on
    (brokerage + exchange + SEBI).
    """
    notional = abs(qty) * price
    stt = 0.000625 * notional if is_sell else 0.0
    stamp = 0.0003 * notional
    exchange = 0.0005 * notional
    sebi = 0.000001 * notional
    brokerage = 20.0
    gst = 0.18 * (brokerage + exchange + sebi)
    return {"stt": stt, "stamp": stamp, "exchange": exchange, "sebi": sebi, "brokerage": brokerage, "gst": gst}


def _acc(target: dict, src: dict) -> None:
    for k, v in src.items():
        target[k] = target.get(k, 0.0) + v
    target["total"] = target.get("total", 0.0) + sum(src.values())


class BacktestError(ValueError):
    """Raised for invalid backtest inputs."""


@dataclass(slots=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    costs_pct: float = 0.03  # per side, % of traded value


@dataclass(slots=True)
class Trade:
    direction: str  # "long" | "short"
    quantity: float
    entry_time: object
    entry_price: float
    exit_time: object
    exit_price: float
    exit_reason: str
    pnl: float
    pnl_pct: float
    bars_held: int

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "quantity": self.quantity,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": round(self.entry_price, 6),
            "exit_time": self.exit_time.isoformat(),
            "exit_price": round(self.exit_price, 6),
            "exit_reason": self.exit_reason,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 4),
            "bars_held": self.bars_held,
        }


@dataclass(slots=True)
class _Position:
    dir_sign: int  # +1 long, -1 short
    quantity: float
    entry_index: int
    entry_price: float
    stop_price: float | None
    target_price: float | None
    trail_pct: float | None
    trailed: bool  # stop has been ratcheted at least once
    extreme: float  # highest high (long) / lowest low (short) since entry
    entry_cost: float = 0.0


@dataclass(slots=True)
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def run_backtest(
    definition: StrategyDefinition,
    candles: Sequence[Candle],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    cfg = config or BacktestConfig()
    if len(candles) < 2:
        raise BacktestError("Need at least 2 candles to run a backtest")
    if cfg.initial_capital <= 0:
        raise BacktestError("initial_capital must be positive")
    if cfg.costs_pct < 0 or cfg.costs_pct > 5:
        raise BacktestError("costs_pct must be between 0 and 5")

    evaluation = evaluate_definition(definition, candles)
    entry_signals = evaluation.entry_signals
    exit_signals = evaluation.exit_signals

    pos_cfg = definition.position
    direction_mode = pos_cfg.direction
    risk = definition.risk

    cash = cfg.initial_capital
    position: _Position | None = None
    pending_entry_dir: int | None = None  # +1/-1 set at signal close
    pending_exit = False
    trades: list[Trade] = []
    equity_curve: list[dict] = []
    total_costs = 0.0
    cost_breakdown: dict[str, float] = {
        "stt": 0.0,
        "exchange": 0.0,
        "sebi": 0.0,
        "stamp": 0.0,
        "brokerage": 0.0,
        "gst": 0.0,
        "total": 0.0,
    }
    equity_peak = cash
    max_drawdown = 0.0

    def size_quantity(price: float) -> float:
        if pos_cfg.quantity_type == "capital_pct":
            pct = pos_cfg.capital_pct if pos_cfg.capital_pct is not None else 100.0
            return max((cash * pct / 100.0) / price, 0.0)
        return max(pos_cfg.quantity, 0.0)

    def close_position(index: int, price: float, reason: str) -> None:
        nonlocal cash, position, total_costs, cost_breakdown
        assert position is not None
        gross = (price - position.entry_price) * position.quantity * position.dir_sign
        exit_costs = _leg_costs(price, position.quantity, is_sell=True)
        _acc(cost_breakdown, exit_costs)
        total_costs = cost_breakdown["total"]
        exit_cost_val = sum(exit_costs.values())
        cash += gross - exit_cost_val
        invested = position.entry_price * position.quantity
        pnl = gross - exit_cost_val - position.entry_cost
        if reason == "stop_loss" and position.trailed:
            reason = "trailing_stop"
        trades.append(
            Trade(
                direction="long" if position.dir_sign == 1 else "short",
                quantity=position.quantity,
                entry_time=candles[position.entry_index].timestamp,
                entry_price=position.entry_price,
                exit_time=candles[index].timestamp,
                exit_price=price,
                exit_reason=reason,
                pnl=pnl,
                pnl_pct=pnl / invested * 100.0 if invested > 0 else 0.0,
                bars_held=index - position.entry_index,
            )
        )
        position = None

    def open_position(index: int, dir_sign: int) -> None:
        nonlocal cash, position, total_costs, raw_costs
        price = candles[index].open
        qty = size_quantity(price)
        if qty <= 0:
            return
        entry_cost = price * qty * cfg.costs_pct / 100.0
        total_costs += entry_cost
        cash -= entry_cost
        _acc(raw_costs, _leg_costs(price, qty, is_sell=False))
        stop = target = trail = None
        if risk is not None:
            if risk.stop_loss_pct is not None:
                stop = price * (1 - dir_sign * risk.stop_loss_pct / 100.0)
            if risk.target_pct is not None:
                target = price * (1 + dir_sign * risk.target_pct / 100.0)
            if risk.trailing_sl_pct is not None:
                trail = risk.trailing_sl_pct / 100.0
                base_stop = price * (1 - dir_sign * trail)
                if stop is None:
                    stop = base_stop
                elif dir_sign == 1:
                    stop = max(stop, base_stop)
                else:
                    stop = min(stop, base_stop)
        position = _Position(
            dir_sign=dir_sign,
            quantity=qty,
            entry_index=index,
            entry_price=price,
            stop_price=stop,
            target_price=target,
            trail_pct=trail,
            trailed=False,
            extreme=candles[index].high if dir_sign == 1 else candles[index].low,
            entry_cost=entry_cost_val,
        )

    n = len(candles)
    for i in range(n):
        bar = candles[i]

        # 1. Execute pendings created at the previous bar's close.
        if pending_exit and position is not None:
            close_position(i, bar.open, "signal")
            if pending_entry_dir is not None and direction_mode == "both":
                # stop-and-reverse fills on the same next-bar open
                open_position(i, pending_entry_dir)
                pending_entry_dir = None
        elif pending_entry_dir is not None and position is None:
            open_position(i, pending_entry_dir)
        pending_exit = False
        pending_entry_dir = None

        # 2. Manage the open position through this bar.
        if position is not None:
            # Intrabar risk exits first (using the stop as of the prior bar),
            # pessimistic: stop before target.
            if position.dir_sign == 1:
                if position.stop_price is not None and bar.low <= position.stop_price:
                    close_position(i, min(bar.open, position.stop_price), "stop_loss")
                elif position.target_price is not None and bar.high >= position.target_price:
                    close_position(i, max(bar.open, position.target_price), "target")
            else:
                if position.stop_price is not None and bar.high >= position.stop_price:
                    close_position(i, max(bar.open, position.stop_price), "stop_loss")
                elif position.target_price is not None and bar.low <= position.target_price:
                    close_position(i, min(bar.open, position.target_price), "target")

            # Trailing stop ratchet happens AFTER the exit check so the current
            # bar's own extreme cannot stop itself out on the entry bar.
            if position is not None and position.trail_pct is not None:
                if position.dir_sign == 1:
                    position.extreme = max(position.extreme, bar.high)
                    trailed = position.extreme * (1 - position.trail_pct)
                    if position.stop_price is None or trailed > position.stop_price:
                        position.stop_price = trailed
                        position.trailed = True
                else:
                    position.extreme = min(position.extreme, bar.low)
                    trailed = position.extreme * (1 + position.trail_pct)
                    if position.stop_price is None or trailed < position.stop_price:
                        position.stop_price = trailed
                        position.trailed = True

        # 3. Read signals at this bar's close → schedule next-bar actions.
        if position is None and pending_entry_dir is None and entry_signals[i]:
            if direction_mode == "short_only":
                pending_entry_dir = -1
            elif direction_mode in ("long_only", "both"):
                pending_entry_dir = 1
        elif position is not None and not pending_exit and exit_signals[i]:
            pending_exit = True
            if direction_mode == "both":
                pending_entry_dir = -position.dir_sign

        # 4. Mark-to-market equity at this bar's close.
        equity = cash
        if position is not None:
            equity += (
                (bar.close - position.entry_price) * position.quantity * position.dir_sign
            )
        equity_curve.append({"time": bar.timestamp.isoformat(), "equity": round(equity, 2)})
        equity_peak = max(equity_peak, equity)
        if equity_peak > 0:
            max_drawdown = max(max_drawdown, (equity_peak - equity) / equity_peak * 100.0)

    # Force-close anything still open at the final bar's close.
    if position is not None:
        close_position(n - 1, candles[n - 1].close, "end_of_data")
        # The force-close charges an exit cost — make the final equity point
        # reflect true cash so summary math stays internally consistent.
        equity_curve[-1]["equity"] = round(cash, 2)

    summary = _build_summary(
        trades, equity_curve, cfg, definition.timeframe, total_costs, max_drawdown, cost_breakdown
    )
    return BacktestResult(trades=trades, equity_curve=equity_curve, summary=summary)


def _build_summary(
    trades: list[Trade],
    equity_curve: list[dict],
    cfg: BacktestConfig,
    timeframe: str,
    total_costs: float,
    max_drawdown: float,
    cost_breakdown: dict[str, float],
) -> dict:
    final_equity = equity_curve[-1]["equity"] if equity_curve else cfg.initial_capital
    net_pnl = final_equity - cfg.initial_capital
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))

    interval_minutes = INTERVAL_MINUTES.get(timeframe, 5)
    bars_per_year = 252 * (375 / interval_minutes)
    returns = [
        equity_curve[i]["equity"] / equity_curve[i - 1]["equity"] - 1
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1]["equity"] > 0
    ]
    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(var_r)
        sharpe = (mean_r / std_r) * math.sqrt(bars_per_year) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "initial_capital": cfg.initial_capital,
        "final_equity": round(final_equity, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(net_pnl / cfg.initial_capital * 100.0, 4),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "profit_factor": (
            round(gross_win / gross_loss, 4) if gross_loss > 0 else (round(gross_win, 4) if gross_win > 0 else 0.0)
        ),
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "largest_win": round(max((t.pnl for t in trades), default=0.0), 2),
        "largest_loss": round(min((t.pnl for t in trades), default=0.0), 2),
        "max_drawdown_pct": round(max_drawdown, 4),
        "sharpe_ratio": round(sharpe, 4),
        "total_costs": round(total_costs, 2),
        "cost_breakdown": {k: round(v, 2) for k, v in cost_breakdown.items()},
        "timeframe": timeframe,
    }
