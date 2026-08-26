"""Tests for real-premium integration in the options backtest engine."""

from datetime import UTC, datetime

from app.backtest.options_engine import OptionsConfig, run_options_backtest
from app.marketdata.base import Candle
from app.quant.schema import StrategyDefinition


def _definition() -> StrategyDefinition:
    return StrategyDefinition.model_validate({
        "version": 1,
        "timeframe": "1d",
        "instrument": {"symbol": "NIFTY", "segment": "index"},
        "legs": [
            {"action": "buy", "option_type": "CE", "strike": 24000, "expiry": "2026-09-24", "lots": 1},
            {"action": "sell", "option_type": "CE", "strike": 24200, "expiry": "2026-09-24", "lots": 1},
        ],
        "entry": {"logic": "ALL", "conditions": [
            {"left": {"kind": "constant", "value": 1}, "op": ">", "right": {"kind": "constant", "value": 0}}]},
        "position": {"quantity_type": "fixed", "quantity": 1, "direction": "both"},
    })


def _candles(n: int = 10):
    return [
        Candle(
            timestamp=datetime(2026, 9, 1 + i, tzinfo=UTC), instrument_id="NIFTY",
            open=24000 + i * 10, high=24050 + i * 10, low=23980 + i * 10,
            close=24020 + i * 10, volume=0,
        )
        for i in range(n)
    ]


def test_real_premiums_override_bs_marks():
    candles = _candles()
    defn = _definition()

    bs = run_options_backtest(defn, candles, OptionsConfig(lot_size=65, auto_roll=False))

    # Real premium series: leg0 (buy 24000CE) flat at 200; leg1 (sell 24200CE) flat at 100
    real_lookup = [
        {c.timestamp.date(): 200.0 for c in candles},
        {c.timestamp.date(): 100.0 for c in candles},
    ]
    real = run_options_backtest(
        defn, candles, OptionsConfig(lot_size=65, auto_roll=False),
        leg_premium_lookup=real_lookup,
    )

    # Entry marks must come from the lookup, not Black-Scholes
    assert real.legs[0].entry_price == 200.0
    assert real.legs[1].entry_price == 100.0
    # BS entry differs from the injected values (proving the override engaged)
    assert bs.legs[0].entry_price != 200.0 or bs.legs[1].entry_price != 100.0


def test_missing_dates_fall_back_to_bs():
    candles = _candles(5)
    defn = _definition()
    # Only the first day has a real premium; everything else falls back
    partial = [{candles[0].timestamp.date(): 150.0}, {}]
    res = run_options_backtest(
        defn, candles, OptionsConfig(lot_size=65, auto_roll=False),
        leg_premium_lookup=partial,
    )
    assert res.legs[0].entry_price == 150.0
    assert len(res.daily_values) == 5


def test_stt_uses_current_statutory_rate():
    """Sell-side STT must be 0.15% of premium now (post Budget-2026)."""
    costs = None
    from app.backtest.options_engine import _leg_costs
    costs = _leg_costs(price=100.0, qty=65, is_sell=True)
    assert abs(costs["stt"] - 0.0015 * 100.0 * 65) < 0.01
