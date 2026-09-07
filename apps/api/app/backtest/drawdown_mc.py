import random
from typing import TypedDict


class DrawdownMCResult(TypedDict):
    equity_curve: list[dict]
    drawdown_curve: list[dict]
    peak_equity: float
    trough_equity: float
    max_drawdown_pct: float
    mc_runs: int
    mc_stats: dict


def compute_drawdown_series(equity_curve: list[dict]) -> tuple[list[dict], float, float, float]:
    peak = equity_curve[0]["equity"]
    max_dd = 0.0
    trough = peak
    series = []
    for pt in equity_curve:
        equity = pt["equity"]
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        if equity < trough:
            trough = equity
        max_dd = max(max_dd, dd)
        series.append({"time": pt["time"], "drawdown_pct": round(dd, 2)})
    return series, peak, trough, round(max_dd, 2)


def bootstrap_monte_carlo(
    equity_curve: list[dict],
    n_runs: int = 1000,
    resample_years: float = 1.0,
) -> DrawdownMCResult:
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        curr = equity_curve[i]["equity"]
        ret = (curr - prev) / prev if prev > 0 else 0.0
        returns.append(ret)

    if len(returns) < 2:
        raise ValueError("Equity curve too short for Monte Carlo")

    n_periods = int(resample_years * len(returns))

    dd_stats = []
    for _ in range(n_runs):
        resampled = [random.choice(returns) for _ in range(n_periods)]
        initial = equity_curve[0]["equity"]
        synthetic = [initial]
        for r in resampled:
            synthetic.append(synthetic[-1] * (1 + r))
        _, _, _, max_dd = compute_drawdown_series(
            [{"time": equity_curve[i]["time"], "equity": synthetic[i]} for i in range(len(synthetic))]
        )
        dd_stats.append(max_dd)

    dd_stats.sort()
    n = len(dd_stats)
    mc_stats = {
        "mean_dd": round(sum(dd_stats) / n, 2),
        "std_dd": round(float((sum((x - sum(dd_stats) / n) ** 2 for x in dd_stats) / n) ** 0.5), 2),
        "p5_dd": round(dd_stats[int(n * 0.05)], 2),
        "p50_dd": round(dd_stats[n // 2], 2),
        "p95_dd": round(dd_stats[int(n * 0.95)], 2),
        "worst_dd": round(max(dd_stats), 2),
        "best_dd": round(min(dd_stats), 2),
        "prob_recovery": round(sum(1 for d in dd_stats if d < 20) / n * 100, 1),
    }

    dd_series, peak, trough, max_dd = compute_drawdown_series(equity_curve)

    return DrawdownMCResult(
        equity_curve=equity_curve,
        drawdown_curve=dd_series,
        peak_equity=round(peak, 2),
        trough_equity=round(trough, 2),
        max_drawdown_pct=max_dd,
        mc_runs=n_runs,
        mc_stats=mc_stats,
    )
