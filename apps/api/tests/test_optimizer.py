"""Unit tests for the optimization engine."""

from datetime import UTC, datetime, timedelta

from app.marketdata.base import Candle
from app.optimizer import OptConfig, apply_params, generate_param_grid, run_grid_search, run_walk_forward
from app.quant.schema import StrategyDefinition

T0 = datetime(2026, 8, 3, 9, 15, tzinfo=UTC)

# 200-bar series with a clear trend so SMA-based strategies produce trades.
SERIES = [100 + i * 0.5 + ((-1) ** i) * 2 for i in range(200)]


def make_candles(closes: list[float]) -> list[Candle]:
    candles = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev if i > 0 else c
        candles.append(
            Candle(
                timestamp=T0 + timedelta(minutes=5 * i),
                instrument_id="TEST",
                open=o,
                high=max(o, c) + 0.5,
                low=min(o, c) - 0.5,
                close=c,
            )
        )
        prev = c
    return candles


def cross_def() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "TEST"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 5}},
            {"id": "s", "type": "SMA", "params": {"length": 20}},
        ],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "s"}}
            ],
        },
        "exit": {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "s"}}
            ],
        },
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }


async def test_generate_param_grid():
    grid = generate_param_grid({"a": [1, 2], "b": [10, 20, 30]})
    assert len(grid) == 6
    assert {"a": 1, "b": 10} in grid
    assert {"a": 2, "b": 30} in grid

    empty = generate_param_grid({})
    assert empty == [{}]


async def test_apply_params():
    definition = StrategyDefinition.model_validate(cross_def())
    modified = apply_params(definition, {"indicators.f.params.length": 50})
    assert modified.indicators[0].params["length"] == 50
    # Original unchanged
    assert definition.indicators[0].params["length"] == 5


async def test_grid_search_produces_ranked_results():
    definition = StrategyDefinition.model_validate(cross_def())
    candles = make_candles(SERIES)
    param_ranges = {"indicators.f.params.length": [5, 10, 20]}

    results = run_grid_search(
        definition, candles, param_ranges,
        OptConfig(initial_capital=100_000, costs_pct=0.0, target_metric="sharpe_ratio"),
    )
    assert len(results) == 3
    # All should be completed (the series is long enough)
    completed = [r for r in results if r.status == "completed"]
    assert len(completed) == 3
    # Should be sorted by sharpe descending
    sharpes = [r.sharpe_ratio for r in completed]
    assert sharpes == sorted(sharpes, reverse=True)


async def test_grid_search_single_param():
    definition = StrategyDefinition.model_validate(cross_def())
    candles = make_candles(SERIES)
    results = run_grid_search(definition, candles, {"risk.stop_loss_pct": [2.0, 5.0]})
    assert len(results) == 2
    assert all(r.params.get("risk.stop_loss_pct") in (2.0, 5.0) for r in results)


async def test_walk_forward_produces_train_test():
    definition = StrategyDefinition.model_validate(cross_def())
    candles = make_candles(SERIES)
    param_ranges = {"indicators.f.params.length": [5, 10]}

    results = run_walk_forward(
        definition, candles, param_ranges,
        OptConfig(initial_capital=100_000, costs_pct=0.0, train_pct=0.7),
    )
    assert len(results) == 2
    for r in results:
        assert r.train_sharpe is not None
        assert r.test_sharpe is not None
        # Should be sorted by train_sharpe descending
    sharpes = [r.train_sharpe for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


async def test_walk_forward_overfitting_detection():
    """If train >> test, the strategy is likely overfitted."""
    definition = StrategyDefinition.model_validate(cross_def())
    # Use a noisy series where random luck may differ between train/test
    import random
    random.seed(42)
    noisy = [100 + random.gauss(0, 5) for _ in range(200)]
    candles = make_candles(noisy)

    results = run_walk_forward(
        definition, candles, {"indicators.f.params.length": [5, 10, 20, 50]},
        OptConfig(initial_capital=100_000, costs_pct=0.0, train_pct=0.7),
    )
    assert len(results) == 4
    # At least one result should have different train/test sharpes
    has_diff = any(abs((r.train_sharpe or 0) - (r.test_sharpe or 0)) > 0.1 for r in results)
    assert has_diff
