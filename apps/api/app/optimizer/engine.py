"""Optimization engine: grid search and walk-forward.

Pure functions — the API layer owns persistence.

Grid search:
  - Generates every combination from the user's parameter ranges
  - Runs backtest for each and ranks by the target metric

Walk-forward:
  - Splits candles into in-sample (train) and out-of-sample (test) windows
  - Runs backtest on each window per parameter combination
  - Reports both train and test metrics so overfitting is visible
"""

import itertools
from dataclasses import dataclass

from app.backtest import BacktestConfig, run_backtest
from app.marketdata.base import Candle
from app.quant.schema import StrategyDefinition


class OptimizerError(ValueError):
    """Raised for invalid optimization inputs."""


@dataclass(slots=True)
class OptConfig:
    initial_capital: float = 100_000.0
    costs_pct: float = 0.03
    target_metric: str = "sharpe_ratio"
    train_pct: float = 0.7  # for walk_forward


@dataclass(slots=True)
class OptResult:
    params: dict
    net_pnl: float = 0.0
    return_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    total_trades: int = 0
    train_sharpe: float | None = None
    test_sharpe: float | None = None
    status: str = "completed"
    error: str | None = None

    def as_dict(self) -> dict:
        d = {
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "total_trades": self.total_trades,
            "status": self.status,
        }
        if self.train_sharpe is not None:
            d["train_sharpe"] = self.train_sharpe
        if self.test_sharpe is not None:
            d["test_sharpe"] = self.test_sharpe
        if self.error:
            d["error"] = self.error
        return d


def generate_param_grid(param_ranges: dict[str, list]) -> list[dict]:
    """Cartesian product of all parameter ranges.

    Keys use dot notation for nested params, e.g.:
      {"indicators.f.params.length": [5, 10, 20], "risk.stop_loss_pct": [1, 2, 5]}
    """
    if not param_ranges:
        return [{}]
    keys = list(param_ranges.keys())
    value_lists = [param_ranges[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


def apply_params(definition: StrategyDefinition, params: dict) -> StrategyDefinition:
    """Return a new definition with the given parameter overrides applied."""
    raw = definition.model_dump()
    for key, value in params.items():
        parts = key.split(".")
        target = raw
        for j, part in enumerate(parts[:-1]):
            if isinstance(target, list) and not part.isdigit():
                # Navigate into a list by ID match (e.g., indicators.f → indicators[{id: "f"}])
                found = False
                for item in target:
                    if isinstance(item, dict) and item.get("id") == part:
                        target = item
                        found = True
                        break
                if not found:
                    raise OptimizerError(f"Cannot find item with id '{part}' in key '{key}'")
            elif part.isdigit():
                target = target[int(part)]
            else:
                target = target[part]
        target[parts[-1]] = value
    return StrategyDefinition.model_validate(raw)


def _metric_value(result_summary: dict, metric: str) -> float:
    """Extract a metric from a backtest summary, defaulting to 0.0."""
    s = result_summary.get("summary", {})
    return float(s.get(metric, 0.0) or 0.0)


def _result_from_summary(params: dict, result_summary: dict) -> OptResult:
    s = result_summary.get("summary", {})
    return OptResult(
        params=params,
        net_pnl=s.get("net_pnl", 0.0),
        return_pct=s.get("return_pct", 0.0),
        win_rate=s.get("win_rate", 0.0),
        profit_factor=s.get("profit_factor", 0.0),
        max_drawdown_pct=s.get("max_drawdown_pct", 0.0),
        sharpe_ratio=s.get("sharpe_ratio", 0.0),
        total_trades=s.get("total_trades", 0),
    )


def run_grid_search(
    definition: StrategyDefinition,
    candles: list[Candle],
    param_ranges: dict[str, list],
    config: OptConfig | None = None,
) -> list[OptResult]:
    """Run backtest for every combination in param_ranges, return ranked results."""
    cfg = config or OptConfig()
    grid = generate_param_grid(param_ranges)
    if not grid:
        raise OptimizerError("No parameter combinations to test")

    results: list[OptResult] = []
    for params in grid:
        try:
            defn = apply_params(definition, params) if params else definition
            bt = run_backtest(
                defn, candles,
                BacktestConfig(initial_capital=cfg.initial_capital, costs_pct=cfg.costs_pct),
            )
            results.append(_result_from_summary(params, bt.summary))
        except Exception as exc:
            results.append(OptResult(params=params, status="failed", error=str(exc)[:500]))

    results.sort(key=lambda r: getattr(r, cfg.target_metric, 0.0), reverse=True)
    for i, r in enumerate(results):
        # rank is set externally after persisting
        pass
    return results


def run_walk_forward(
    definition: StrategyDefinition,
    candles: list[Candle],
    param_ranges: dict[str, list],
    config: OptConfig | None = None,
) -> list[OptResult]:
    """Split candles into train/test windows, run each combo on both, return results.

    The results are sorted by train_sharpe (best in-sample first) so the user
    can see whether test performance degrades — a signal of overfitting.
    """
    cfg = config or OptConfig()
    grid = generate_param_grid(param_ranges)
    if not grid:
        raise OptimizerError("No parameter combinations to test")
    if len(candles) < 20:
        raise OptimizerError("Need at least 20 candles for walk-forward analysis")

    split = int(len(candles) * cfg.train_pct)
    train_candles = candles[:split]
    test_candles = candles[split:]

    results: list[OptResult] = []
    for params in grid:
        try:
            defn = apply_params(definition, params) if params else definition
            bt_cfg = BacktestConfig(initial_capital=cfg.initial_capital, costs_pct=cfg.costs_pct)

            train_bt = run_backtest(defn, train_candles, bt_cfg)
            test_bt = run_backtest(defn, test_candles, bt_cfg)

            train_sharpe = train_bt.summary.get("sharpe_ratio", 0.0)
            test_sharpe = test_bt.summary.get("sharpe_ratio", 0.0)

            # Use the test-window summary for the main metrics
            r = _result_from_summary(params, test_bt.summary)
            r.train_sharpe = train_sharpe
            r.test_sharpe = test_sharpe
            results.append(r)
        except Exception as exc:
            results.append(OptResult(params=params, status="failed", error=str(exc)[:500]))

    # Sort by train_sharpe descending so overfitting is visible
    results.sort(key=lambda r: r.train_sharpe or 0.0, reverse=True)
    return results
