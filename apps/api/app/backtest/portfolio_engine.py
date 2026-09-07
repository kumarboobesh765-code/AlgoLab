"""Portfolio combination engine.

Pure function: takes multiple per-strategy backtest results and produces a
single combined equity curve + summary. All math is in normalized
percentage-return space so strategies of different initial capitals can be
combined meaningfully.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.backtest.engine import BacktestResult


@dataclass(slots=True)
class PortfolioInput:
    strategy_id: str
    strategy_name: str
    initial_capital: float
    result: BacktestResult


def _normalize_curve(curve: Sequence[dict], initial_capital: float) -> list[float]:
    """Convert an equity curve (absolute INR) to a cumulative pct-return curve."""
    if not curve or initial_capital <= 0:
        return []
    base = float(curve[0]["equity"])
    if base <= 0:
        return []
    return [float(p["equity"]) / base - 1.0 for p in curve]


def combine(runs: Sequence[PortfolioInput]) -> tuple[list[dict], dict]:
    """Combine multiple per-strategy backtest results.

    Returns (combined_equity_curve, combined_summary). The combined curve is
    built in normalized pct-return space (sum of per-strategy returns) and then
    scaled back to INR using the first run's initial capital.
    """
    if not runs:
        return [], {
            "initial_capital": 0.0,
            "final_equity": 0.0,
            "net_pnl": 0.0,
            "return_pct": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_costs": 0.0,
            "strategies": 0,
        }

    base_capital = float(runs[0].initial_capital)
    sum_init = sum(float(r.initial_capital) for r in runs)

    norm_curves: list[list[float]] = [
        _normalize_curve(r.result.equity_curve, r.initial_capital) for r in runs
    ]
    max_len = max((len(c) for c in norm_curves), default=0)

    if max_len == 0:
        return [], {
            "initial_capital": round(sum_init, 2),
            "final_equity": round(sum_init, 2),
            "net_pnl": 0.0,
            "return_pct": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_costs": 0.0,
            "strategies": len(runs),
        }

    anchor_time = ""
    for r in runs:
        if r.result.equity_curve:
            anchor_time = str(r.result.equity_curve[0]["time"])
            break

    combined_curve: list[dict] = []
    for i in range(max_len):
        total_ret = 0.0
        count = 0
        for c in norm_curves:
            if i < len(c):
                total_ret += c[i]
                count += 1
        if count == 0:
            continue
        avg_ret = total_ret / count
        equity = base_capital * (1.0 + avg_ret)
        combined_curve.append({"time": anchor_time, "equity": round(equity, 2)})

    final_equity = combined_curve[-1]["equity"] if combined_curve else base_capital
    total_pnl = 0.0
    total_trades = 0
    winning_trades = 0
    losing_trades = 0
    gross_win = 0.0
    gross_loss = 0.0
    total_costs = 0.0
    weighted_sharpe_num = 0.0
    weighted_sharpe_den = 0
    largest_win = 0.0
    largest_loss = 0.0

    for r in runs:
        s = r.result.summary or {}
        total_pnl += float(s.get("net_pnl", 0.0))
        n_trades = int(s.get("total_trades", 0))
        total_trades += n_trades
        winning_trades += int(s.get("winning_trades", 0))
        losing_trades += int(s.get("losing_trades", 0))
        total_costs += float(s.get("total_costs", 0.0))

        for t in r.result.trades:
            if t.pnl > 0:
                gross_win += t.pnl
                if t.pnl > largest_win:
                    largest_win = t.pnl
            else:
                gross_loss += t.pnl
                if t.pnl < largest_loss:
                    largest_loss = t.pnl

        sharpe = float(s.get("sharpe_ratio", 0.0))
        weighted_sharpe_num += sharpe * n_trades
        weighted_sharpe_den += n_trades

    peak = combined_curve[0]["equity"] if combined_curve else 0.0
    max_dd = 0.0
    for p in combined_curve:
        if p["equity"] > peak:
            peak = p["equity"]
        if peak > 0:
            dd = (peak - p["equity"]) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    combined_return_pct = (
        (final_equity - sum_init) / sum_init * 100.0 if sum_init > 0 else 0.0
    )
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = (gross_win / abs(gross_loss)) if gross_loss < 0 else (
        round(gross_win, 4) if gross_win > 0 else 0.0
    )
    weighted_sharpe = (
        weighted_sharpe_num / weighted_sharpe_den if weighted_sharpe_den > 0 else 0.0
    )

    avg_win = (gross_win / winning_trades) if winning_trades > 0 else 0.0
    avg_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0.0

    combined_summary = {
        "initial_capital": round(sum_init, 2),
        "final_equity": round(final_equity, 2),
        "net_pnl": round(total_pnl, 2),
        "return_pct": round(combined_return_pct, 4),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "largest_win": round(largest_win, 2),
        "largest_loss": round(largest_loss, 2),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio": round(weighted_sharpe, 4),
        "total_costs": round(total_costs, 2),
        "strategies": len(runs),
    }
    return combined_curve, combined_summary
