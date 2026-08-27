"""Options backtest engine for multi-leg strategies.

Simulates per-leg option positions with AlgoTest-parity risk management.
Uses Black-Scholes to model option premiums from underlying candles.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.marketdata.base import Candle
from app.quant.schema import StrategyDefinition

RISK_FREE = 0.06
STRIKE_STEPS = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 75, "SENSEX": 100, "BANKEX": 100}


def _strike_step(symbol: str) -> int:
    return STRIKE_STEPS.get(symbol.upper(), 50)


def _bs_price(S: float, K: float, T: float, sigma: float, is_call: bool) -> float:
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if is_call else max(K - S, 0)
    d1 = (math.log(S / K) + (RISK_FREE + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
    if is_call:
        return S * nd1 - K * math.exp(-RISK_FREE * T) * nd2
    return K * math.exp(-RISK_FREE * T) * (1 - nd2) - S * (1 - nd1)


def _parse_time_hm(t: str | None) -> int | None:
    if not t:
        return None
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


class OptionsBacktestError(ValueError):
    pass


@dataclass(slots=True)
class LegTrade:
    leg_index: int
    action: str
    option_type: str
    strike: float
    entry_time: object
    entry_price: float
    exit_time: object
    exit_price: float
    exit_reason: str
    pnl: float
    lots: int

    def as_dict(self) -> dict:
        return {
            "leg_index": self.leg_index,
            "action": self.action,
            "option_type": self.option_type,
            "strike": self.strike,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": round(self.entry_price, 2),
            "exit_time": self.exit_time.isoformat(),
            "exit_price": round(self.exit_price, 2),
            "exit_reason": self.exit_reason,
            "pnl": round(self.pnl, 2),
            "lots": self.lots,
        }


@dataclass(slots=True)
class LegPosition:
    leg_index: int
    action: str
    option_type: str
    strike: float
    lots: int
    entry_index: int
    entry_price: float
    entry_underlying: float
    sl_price: float | None = None
    target_price: float | None = None
    trail_active: bool = False
    trail_step: float = 0.0
    trail_trigger: float = 0.0
    trail_extreme: float = 0.0
    reentry_count: int = 0
    max_reentries: int = 0
    reentry_on_sl: str | None = None
    reentry_on_target: str | None = None
    square_off: str = "partial"


@dataclass(slots=True)
class OptionsBacktestResult:
    trades: list[LegTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _compute_sl_target(leg, entry_price: float, entry_underlying: float, step: int) -> tuple[float | None, float | None]:
    sl = None
    tgt = None
    if leg.sl_mode and leg.sl_value:
        if leg.sl_mode == "pts":
            sl = entry_price - leg.sl_value if leg.action == "buy" else entry_price + leg.sl_value
        elif leg.sl_mode == "%":
            pct = leg.sl_value / 100.0
            sl = entry_price * (1 - pct) if leg.action == "buy" else entry_price * (1 + pct)
        elif leg.sl_mode in ("underlying_pts", "underlying_pct"):
            u_move = leg.sl_value if leg.sl_mode == "underlying_pts" else entry_underlying * leg.sl_value / 100.0
            sl = entry_price - u_move * 0.5 if leg.action == "buy" else entry_price + u_move * 0.5
    if leg.target_mode and leg.target_value:
        if leg.target_mode == "pts":
            tgt = entry_price + leg.target_value if leg.action == "buy" else entry_price - leg.target_value
        elif leg.target_mode == "%":
            pct = leg.target_value / 100.0
            tgt = entry_price * (1 + pct) if leg.action == "buy" else entry_price * (1 - pct)
        elif leg.target_mode in ("underlying_pts", "underlying_pct"):
            u_move = leg.target_value if leg.target_mode == "underlying_pts" else entry_underlying * leg.target_value / 100.0
            tgt = entry_price + u_move * 0.5 if leg.action == "buy" else entry_price - u_move * 0.5
    return sl, tgt


def run_options_backtest(
    definition: StrategyDefinition,
    candles: Sequence[Candle],
    initial_capital: float = 100_000.0,
    costs_pct: float = 0.03,
) -> OptionsBacktestResult:
    if len(candles) < 2:
        raise OptionsBacktestError("Need at least 2 candles")
    if not definition.legs:
        raise OptionsBacktestError("No legs defined")

    legs = definition.legs
    n = len(candles)
    step = _strike_step(definition.instrument.symbol)
    overall = definition.overall
    time_cfg = definition.time_control
    legwise = definition.legwise

    cash = initial_capital
    positions: list[LegPosition | None] = [None] * len(legs)
    pending_entries: list[bool] = [True] * len(legs)
    trades: list[LegTrade] = []
    equity_curve: list[dict] = []
    total_costs = 0.0
    overall_locked = 0.0
    overall_peak_pnl = 0.0
    iv = 0.20

    def _leg_premium(S: float, strike: float, T: float, opt_type: str) -> float:
        return max(_bs_price(S, strike, T, iv, opt_type == "CE"), 0.01)

    def _open_leg(li: int, bar, S: float, T: float) -> None:
        nonlocal cash, total_costs
        leg = legs[li]
        strike_offset = leg.strike_offset or 0
        strike = round(S / step) * step + strike_offset * step
        premium = _leg_premium(S, strike, T, leg.option_type)
        lots = leg.lots or 1
        cost = premium * lots * costs_pct / 100.0
        cash -= cost
        total_costs += cost
        sl, tgt = _compute_sl_target(leg, premium, S, step)
        trail_step_val = leg.trail_step or 0
        trail_by_val = leg.trail_by or 0
        positions[li] = LegPosition(
            leg_index=li, action=leg.action, option_type=leg.option_type,
            strike=strike, lots=lots, entry_index=i, entry_price=premium,
            entry_underlying=S, sl_price=sl, target_price=tgt,
            trail_active=bool(trail_by_val > 0 and trail_step_val > 0),
            trail_step=trail_step_val, trail_trigger=trail_by_val,
            trail_extreme=premium,
            max_reentries=leg.max_reentries or 0,
            reentry_on_sl=leg.reentry_on_sl, reentry_on_target=leg.reentry_on_target,
            square_off=leg.square_off or "partial",
        )

    def _close_leg(li: int, bar, reason: str) -> None:
        nonlocal cash, total_costs
        pos = positions[li]
        if pos is None:
            return
        S = bar.close
        T = max((n - i) / (252 * (375 / 5)), 1 / 375)
        premium = _leg_premium(S, pos.strike, T, pos.option_type)
        gross = (premium - pos.entry_price) * pos.lots
        if pos.action == "sell":
            gross = -gross
        cost = abs(premium * pos.lots * costs_pct / 100.0)
        cash += gross - cost
        total_costs += cost
        trades.append(LegTrade(
            leg_index=li, action=pos.action, option_type=pos.option_type,
            strike=pos.strike, entry_time=candles[pos.entry_index].timestamp,
            entry_price=pos.entry_price, exit_time=bar.timestamp,
            exit_price=premium, exit_reason=reason, pnl=gross - cost, lots=pos.lots,
        ))
        positions[li] = None

    def _compute_mtm(S: float, T: float) -> float:
        mtm = 0.0
        for li_pos, pos in enumerate(positions):
            if pos is None:
                continue
            premium = _leg_premium(S, pos.strike, T, pos.option_type)
            diff = premium - pos.entry_price
            if pos.action == "sell":
                diff = -diff
            mtm += diff * pos.lots
        return mtm

    for i in range(n):
        bar = candles[i]
        S = bar.close
        bar_min = _bar_minutes(bar.timestamp)
        T = max((n - i) / (252 * (375 / 5)), 1 / 375)

        no_entry = _parse_time_hm(time_cfg.no_entry_after) if time_cfg else None
        no_reentry = _parse_time_hm(time_cfg.no_reentry_after) if time_cfg else None
        force_exit = _parse_time_hm(time_cfg.time_exit) if time_cfg else None

        if force_exit and bar_min >= force_exit:
            for li in range(len(legs)):
                if positions[li] is not None:
                    _close_leg(li, bar, "time_exit")
            equity_curve.append({"time": bar.timestamp.isoformat(), "equity": round(cash, 2)})
            continue

        for li in range(len(legs)):
            if pending_entries[li] and positions[li] is None:
                if no_entry and bar_min >= no_entry:
                    pending_entries[li] = False
                    continue
                _open_leg(li, bar, S, T)
            pending_entries[li] = False

        for li in range(len(legs)):
            pos = positions[li]
            if pos is None:
                continue
            premium = _leg_premium(S, pos.strike, T, pos.option_type)
            if pos.sl_price is not None:
                triggered = (pos.action == "buy" and premium <= pos.sl_price) or (pos.action == "sell" and premium >= pos.sl_price)
                if triggered:
                    _close_leg(li, bar, "stop_loss")
                    if pos.reentry_on_sl and pos.reentry_count < pos.max_reentries:
                        if no_reentry is None or bar_min < no_reentry:
                            pending_entries[li] = True
                            pos.reentry_count += 1
                    continue
            if pos.target_price is not None:
                triggered = (pos.action == "buy" and premium >= pos.target_price) or (pos.action == "sell" and premium <= pos.target_price)
                if triggered:
                    _close_leg(li, bar, "target")
                    if pos.reentry_on_target and pos.reentry_count < pos.max_reentries:
                        if no_reentry is None or bar_min < no_reentry:
                            pending_entries[li] = True
                            pos.reentry_count += 1
                    continue
            if pos.trail_active and pos.trail_trigger > 0:
                if pos.action == "buy":
                    pos.trail_extreme = max(pos.trail_extreme, premium)
                    if pos.trail_extreme >= pos.trail_trigger:
                        new_sl = pos.trail_extreme - pos.trail_step
                        if pos.sl_price is None or new_sl > pos.sl_price:
                            pos.sl_price = new_sl
                else:
                    pos.trail_extreme = min(pos.trail_extreme, premium)
                    if pos.trail_extreme <= pos.trail_trigger:
                        new_sl = pos.trail_extreme + pos.trail_step
                        if pos.sl_price is None or new_sl < pos.sl_price:
                            pos.sl_price = new_sl

        if legwise and legwise.square_off_on_leg_sl:
            sl_hit = any(t.exit_reason == "stop_loss" and t.exit_time == bar.timestamp for t in trades)
            if sl_hit:
                for li in range(len(legs)):
                    if positions[li] is not None:
                        _close_leg(li, bar, "square_off_propagation")

        if overall:
            mtm = _compute_mtm(S, T)
            overall_peak_pnl = max(overall_peak_pnl, mtm)
            if overall.overall_sl is not None and mtm <= -overall.overall_sl:
                for li in range(len(legs)):
                    if positions[li] is not None:
                        _close_leg(li, bar, "overall_sl")
            if overall.overall_target is not None and mtm >= overall.overall_target:
                for li in range(len(legs)):
                    if positions[li] is not None:
                        _close_leg(li, bar, "overall_target")
            if overall.lock_profit is not None and overall.lock_at is not None:
                if mtm >= overall.lock_at:
                    overall_locked = max(overall_locked, overall.lock_profit)
            if overall.lock_and_trail_profit is not None and overall.lock_and_trail_at is not None and overall.lock_and_trail_by is not None:
                if mtm >= overall.lock_and_trail_at:
                    extra = (mtm - overall.lock_and_trail_at) * (overall.lock_and_trail_by / max(overall.lock_and_trail_at, 1))
                    overall_locked = max(overall_locked, overall.lock_and_trail_profit + extra)
            if overall_locked > 0 and mtm <= overall_locked:
                for li in range(len(legs)):
                    if positions[li] is not None:
                        _close_leg(li, bar, "lock_profit")
            if overall.overall_trail_sl is not None and overall.overall_trail_every is not None and overall_peak_pnl > 0:
                trail_sl_level = overall_peak_pnl - overall.overall_trail_sl
                if mtm <= trail_sl_level:
                    for li in range(len(legs)):
                        if positions[li] is not None:
                            _close_leg(li, bar, "overall_trail_sl")

        equity = cash
        for pos in positions:
            if pos is not None:
                premium = _leg_premium(S, pos.strike, T, pos.option_type)
                diff = premium - pos.entry_price
                if pos.action == "sell":
                    diff = -diff
                equity += diff * pos.lots
        equity_curve.append({"time": bar.timestamp.isoformat(), "equity": round(equity, 2)})

    for li in range(len(legs)):
        if positions[li] is not None:
            _close_leg(li, candles[-1], "end_of_data")
    if equity_curve:
        equity_curve[-1]["equity"] = round(cash, 2)

    summary = _build_summary(trades, equity_curve, initial_capital, total_costs, definition.timeframe)
    return OptionsBacktestResult(trades=trades, equity_curve=equity_curve, summary=summary)


def _build_summary(trades, equity_curve, initial_capital, total_costs, timeframe):
    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
    net_pnl = final_equity - initial_capital
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    max_dd = 0.0
    peak = initial_capital
    for pt in equity_curve:
        peak = max(peak, pt["equity"])
        if peak > 0:
            max_dd = max(max_dd, (peak - pt["equity"]) / peak * 100.0)
    return {
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(net_pnl / initial_capital * 100.0, 4),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else round(gross_win, 4) if gross_win > 0 else 0.0,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "largest_win": round(max((t.pnl for t in trades), default=0.0), 2),
        "largest_loss": round(min((t.pnl for t in trades), default=0.0), 2),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio": 0.0,
        "total_costs": round(total_costs, 2),
        "timeframe": timeframe,
    }
