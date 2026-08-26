"""Unit tests for the pure backtest engine."""

from datetime import UTC, datetime, timedelta

from app.backtest import BacktestConfig, BacktestError, run_backtest
from app.marketdata.base import Candle

T0 = datetime(2026, 6, 1, 9, 15, tzinfo=UTC)


def make_candles(closes: list[float], spread: float = 1.0) -> list[Candle]:
    """Build candles from a close series; open = prev close, high/low bracket."""
    candles = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev if i > 0 else c
        hi = max(o, c) + spread / 2
        lo = min(o, c) - spread / 2
        candles.append(
            Candle(
                timestamp=T0 + timedelta(minutes=5 * i),
                instrument_id="TEST",
                open=o,
                high=hi,
                low=lo,
                close=c,
            )
        )
        prev = c
    return candles


def cross_def(**overrides) -> dict:
    d = {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "TEST"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 2}},
            {"id": "s", "type": "SMA", "params": {"length": 4}},
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
    }
    d.update(overrides)
    return d


# Warmup (SMA4 needs 4 bars), up-leg -> entry, down-leg -> exit while holding,
# second up-leg -> re-entry. Guarantees two round trips in long_only mode.
ROUND_TRIPS = [
    100, 100, 100, 100, 100,
    104, 108, 112,          # cross above -> enter
    110, 106, 102,          # cross below -> exit
    98, 96,                 # keep falling
    100, 104, 108,          # cross above again -> re-enter
]


async def test_basic_long_cycle_produces_trades():
    from app.quant.schema import StrategyDefinition

    result = run_backtest(
        StrategyDefinition.model_validate(cross_def()), make_candles(ROUND_TRIPS)
    )
    assert len(result.trades) >= 2
    longs = [t for t in result.trades if t.direction == "long"]
    assert longs, "expected at least one long trade"
    # next-bar-open execution: entry never at the signal bar itself is hard to
    # assert directly, but bars_held must be >= 1 for signal exits.
    for t in result.trades:
        if t.exit_reason == "signal":
            assert t.bars_held >= 1
    s = result.summary
    assert s["total_trades"] == len(result.trades)
    assert s["initial_capital"] == 100_000.0
    assert len(result.equity_curve) == len(ROUND_TRIPS)
    assert result.equity_curve[0]["equity"] == 100_000.0


async def test_no_lookahead_entry_price_is_next_open():
    """Entry fill must be the bar AFTER the signal bar's open."""
    from app.quant.schema import StrategyDefinition

    candles = make_candles(ROUND_TRIPS)
    result = run_backtest(
        StrategyDefinition.model_validate(cross_def()), candles
    )
    assert result.trades, "expected trades"
    t = result.trades[0]
    entry_idx = next(
        i for i, c in enumerate(candles) if c.timestamp == t.entry_time
    )
    assert t.entry_price == candles[entry_idx].open


async def test_stop_loss_triggers():
    from app.quant.schema import StrategyDefinition

    d = cross_def(risk={"stop_loss_pct": 5.0})
    # Flat warmup -> entry -> crash through the stop.
    closes = [100, 100, 100, 100, 100, 102, 104, 106, 108, 80, 79, 78]
    result = run_backtest(StrategyDefinition.model_validate(d), make_candles(closes))
    stops = [t for t in result.trades if t.exit_reason in ("stop_loss", "trailing_stop")]
    assert stops, "expected a stop exit"
    t = stops[0]
    assert t.pnl < 0


async def test_target_triggers():
    from app.quant.schema import StrategyDefinition

    d = cross_def(position={"quantity_type": "fixed", "quantity": 100}, risk={"target_pct": 1.0})
    closes = [100, 100, 100, 100, 100, 102, 104, 106, 108, 110]
    result = run_backtest(
        StrategyDefinition.model_validate(d),
        make_candles(closes),
        config=BacktestConfig(costs_pct=0.001),
    )
    targets = [t for t in result.trades if t.exit_reason == "target"]
    assert targets, "expected a target exit"
    assert targets[0].pnl > 0


async def test_trailing_stop_ratchets():
    from app.quant.schema import StrategyDefinition

    d = cross_def(position={"quantity_type": "fixed", "quantity": 100}, risk={"trailing_sl_pct": 1.0})
    closes = [100, 100, 100, 100, 100, 104, 108, 112, 116, 120, 124, 128, 120, 116]
    result = run_backtest(
        StrategyDefinition.model_validate(d),
        make_candles(closes, spread=0.1),
        config=BacktestConfig(costs_pct=0.001),
    )
    trails = [t for t in result.trades if t.exit_reason == "trailing_stop"]
    assert trails, "expected trailing stop exit"
    assert trails[0].pnl > 0


async def test_short_only_direction():
    from app.quant.schema import StrategyDefinition

    d = cross_def(position={"quantity_type": "fixed", "quantity": 10, "direction": "short_only"})
    result = run_backtest(StrategyDefinition.model_validate(d), make_candles(ROUND_TRIPS))
    shorts = [t for t in result.trades if t.direction == "short"]
    assert shorts, "expected short trades"
    assert all(t.direction == "short" for t in result.trades)


async def test_costs_are_charged_per_side():
    from app.quant.schema import StrategyDefinition

    d = cross_def(position={"quantity_type": "fixed", "quantity": 100, "direction": "long_only"})
    candles = make_candles(ROUND_TRIPS)

    free = run_backtest(
        StrategyDefinition.model_validate(d), candles, BacktestConfig(costs_pct=0.0)
    )
    priced = run_backtest(
        StrategyDefinition.model_validate(d), candles, BacktestConfig(costs_pct=0.5)
    )
    assert priced.summary["net_pnl"] < free.summary["net_pnl"]
    assert priced.summary["total_costs"] > 0


async def test_capital_pct_sizing():
    from app.quant.schema import StrategyDefinition

    d = cross_def(
        position={"quantity_type": "capital_pct", "capital_pct": 50, "direction": "long_only"}
    )
    result = run_backtest(StrategyDefinition.model_validate(d), make_candles(ROUND_TRIPS))
    t = result.trades[0]
    expected_qty = 100_000 * 0.5 / t.entry_price
    assert abs(t.quantity - expected_qty) < expected_qty * 0.01  # equity moved slightly


async def test_end_of_data_force_close():
    from app.quant.schema import StrategyDefinition

    # Flat warmup then a clean up-leg: entry happens, no exit signal before data ends.
    closes = [100, 100, 100, 100, 100, 102, 104, 106, 108]
    result = run_backtest(StrategyDefinition.model_validate(cross_def()), make_candles(closes))
    assert result.trades
    assert result.trades[-1].exit_reason == "end_of_data"


async def test_insufficient_inputs_raise():
    from app.quant.schema import StrategyDefinition

    try:
        run_backtest(StrategyDefinition.model_validate(cross_def()), make_candles([100]))
        raise AssertionError("expected BacktestError")
    except BacktestError:
        pass
    try:
        run_backtest(
            StrategyDefinition.model_validate(cross_def()),
            make_candles(ROUND_TRIPS),
            BacktestConfig(initial_capital=-5),
        )
        raise AssertionError("expected BacktestError")
    except BacktestError:
        pass


async def test_summary_metrics_consistency():
    from app.quant.schema import StrategyDefinition

    result = run_backtest(StrategyDefinition.model_validate(cross_def()), make_candles(ROUND_TRIPS))
    s = result.summary
    assert s["winning_trades"] + s["losing_trades"] == s["total_trades"]
    if s["total_trades"]:
        expected_wr = round(s["winning_trades"] / s["total_trades"] * 100, 2)
        assert s["win_rate"] == expected_wr
        pnl_sum = round(sum(t.pnl for t in result.trades), 2)
        # net pnl equals sum of trade pnls (cash accounting identity)
        assert abs(pnl_sum - s["net_pnl"]) < 0.01


# ---- adverse slippage (2026 addition) ----


def _zigzag_candles(n: int = 60):
    import math
    from datetime import datetime, timedelta

    from app.marketdata.base import Candle

    prices = [100 + 20 * math.sin(i / 4.0) for i in range(n)]
    base = datetime(2026, 1, 1)
    return [
        Candle(
            timestamp=base + timedelta(days=i), instrument_id="X",
            open=prices[i], high=prices[i] + 2, low=prices[i] - 2,
            close=prices[i], volume=0,
        )
        for i in range(n)
    ]


def _cross_definition():
    return {
        "version": 1, "timeframe": "1d", "instrument": {"symbol": "X"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 3}},
            {"id": "s", "type": "SMA", "params": {"length": 10}},
        ],
        "entry": {"logic": "ALL", "conditions": [
            {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "s"}}]},
        "exit": {"logic": "ALL", "conditions": [
            {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "s"}}]},
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }


def test_slippage_reduces_long_pnl_and_shifts_entries():
    from app.backtest import BacktestConfig, run_backtest
    from app.quant.schema import StrategyDefinition

    candles = _zigzag_candles()
    defn = StrategyDefinition.model_validate(_cross_definition())

    base = run_backtest(defn, candles, BacktestConfig(initial_capital=100_000, costs_pct=0.0))
    slipped = run_backtest(defn, candles, BacktestConfig(initial_capital=100_000, costs_pct=0.0, slippage_pct=0.5))

    assert base.summary["total_trades"] > 0
    # Same trades identified, but every fill is worse for the trader
    assert slipped.summary["total_trades"] == base.summary["total_trades"]
    assert slipped.summary["net_pnl"] < base.summary["net_pnl"]
    # First long entry fills above the bar open
    b0 = base.trades[0]
    s0 = slipped.trades[0]
    assert s0.entry_price > b0.entry_price
    assert s0.exit_price < b0.exit_price


def test_zero_slippage_matches_legacy_behavior():
    from app.backtest import BacktestConfig, run_backtest
    from app.quant.schema import StrategyDefinition

    candles = _zigzag_candles()
    defn = StrategyDefinition.model_validate(_cross_definition())
    a = run_backtest(defn, candles, BacktestConfig(costs_pct=0.01))
    b = run_backtest(defn, candles, BacktestConfig(costs_pct=0.01, slippage_pct=0.0))
    assert a.summary == b.summary
