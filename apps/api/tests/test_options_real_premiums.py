"""Tests for real-premium integration in the options backtest engine."""

from datetime import UTC, datetime

from app.backtest.options_engine import run_options_backtest
from app.marketdata.base import Candle
from app.quant.schema import InstrumentRef, OptionLeg, StrategyDefinition


def _definition(legs: list[OptionLeg] | None = None) -> StrategyDefinition:
    if legs is None:
        legs = [
            OptionLeg(action="buy", option_type="CE", strike=24000, lots=1),
            OptionLeg(action="sell", option_type="CE", strike=24200, lots=1),
        ]
    return StrategyDefinition(
        version=1, timeframe="1d",
        instrument=InstrumentRef(symbol="NIFTY", exchange="NSE", segment="options"),
        legs=legs,
        entry={"logic": "ALL", "conditions": [
            {"left": {"kind": "constant", "value": 1}, "op": "GT", "right": {"kind": "constant", "value": 0}}]},
    )


def _candles(n: int = 10):
    return [
        Candle(
            timestamp=datetime(2026, 9, 1 + i, tzinfo=UTC), instrument_id="NIFTY",
            open=24000 + i * 10, high=24050 + i * 10, low=23980 + i * 10,
            close=24020 + i * 10, volume=0, oi=0,
        )
        for i in range(n)
    ]


def test_basic_two_leg_strategy():
    candles = _candles()
    defn = _definition()
    result = run_options_backtest(defn, candles)
    assert result.summary["total_trades"] >= 2
    assert len(result.equity_curve) == len(candles)


def test_single_long_call():
    candles = _candles(5)
    legs = [OptionLeg(action="buy", option_type="CE", strike=24000, lots=1)]
    result = run_options_backtest(_definition(legs), candles)
    assert result.summary["total_trades"] >= 1


def test_summary_has_required_fields():
    candles = _candles(5)
    result = run_options_backtest(_definition(), candles)
    s = result.summary
    assert "initial_capital" in s
    assert "final_equity" in s
    assert "net_pnl" in s
    assert "return_pct" in s
    assert "total_trades" in s
    assert "win_rate" in s
    assert "max_drawdown_pct" in s


def test_equity_curve_tracks_all_bars():
    candles = _candles(8)
    result = run_options_backtest(_definition(), candles)
    assert len(result.equity_curve) == len(candles)
