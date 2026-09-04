"""Quick smoke test: load the AlgoTest Leg Builder definition and run a synthetic backtest."""

from datetime import UTC, datetime, timedelta

from app.backtest.options_engine import run_options_backtest
from app.marketdata.base import Candle
from app.quant.schema import StrategyDefinition


def make_candles(closes: list[float]) -> list[Candle]:
    candles = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev if i > 0 else c
        hi = max(o, c)
        lo = min(o, c)
        candles.append(Candle(
            timestamp=datetime(2026, 6, 1, 9, 15, tzinfo=UTC) + timedelta(minutes=5 * i),
            instrument_id="NIFTY", open=o, high=hi, low=lo, close=c, volume=1000, oi=5000,
        ))
        prev = c
    return candles


def load_definition() -> StrategyDefinition:
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent.parent / "strategy_algotest_leg_builder.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return StrategyDefinition.model_validate(data)


def test_definition_loads():
    definition = load_definition()
    assert definition.version == 1
    assert definition.builder == "legs"
    assert len(definition.legs) == 4
    assert definition.overall is not None
    assert definition.overall.overall_sl == 1000
    assert definition.overall.overall_target == 2500
    assert definition.overall.lock_and_trail_at == 4000
    assert definition.overall.lock_and_trail_profit == 3000
    assert definition.overall.lock_and_trail_by == 500


def test_backtest_runs():
    definition = load_definition()
    candles = make_candles([22000, 22100, 22200, 22300, 22400, 22500, 22600])
    result = run_options_backtest(definition, candles)
    assert result.summary["total_trades"] >= 1
    assert "net_pnl" in result.summary


if __name__ == "__main__":
    test_definition_loads()
    print("test_definition_loads: PASSED")
    test_backtest_runs()
    print("test_backtest_runs: PASSED")
