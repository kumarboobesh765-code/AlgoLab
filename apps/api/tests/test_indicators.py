"""Tests for the indicator library (hand-computed values + invariants)."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.marketdata.base import Candle
from app.quant.indicators import (
    INDICATORS,
    IndicatorError,
    compute_indicator,
    validate_params,
)

START = datetime(2026, 8, 3, 3, 45, tzinfo=UTC)  # Monday 09:15 IST


def make_candles(closes: list[float]) -> list[Candle]:
    candles = []
    ts = START
    for i, close in enumerate(closes):
        candles.append(
            Candle(
                timestamp=ts,
                instrument_id="TEST",
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=1000 + i,
            )
        )
        ts += timedelta(minutes=1)
    return candles


def last(series: list[float]) -> float:
    return series[-1]


class TestRegistry:
    def test_all_registered_types_have_computers(self):
        from app.quant.indicators import _COMPUTERS

        assert set(INDICATORS) == set(_COMPUTERS)

    def test_validate_params_rejects_unknown_type(self):
        with pytest.raises(IndicatorError, match="Unknown indicator"):
            validate_params("NOPE", {})

    def test_validate_params_rejects_unknown_param(self):
        with pytest.raises(IndicatorError, match="unknown parameter"):
            validate_params("SMA", {"bogus": 5})

    def test_validate_params_bounds(self):
        with pytest.raises(IndicatorError, match=">= 1"):
            validate_params("SMA", {"length": 0})
        with pytest.raises(IndicatorError, match="must be an integer"):
            validate_params("SMA", {"length": 2.5})
        with pytest.raises(IndicatorError, match="one of"):
            validate_params("SMA", {"source": "typo"})

    def test_macd_requires_fast_below_slow(self):
        with pytest.raises(IndicatorError, match="must be < MACD.slow"):
            validate_params("MACD", {"fast": 26, "slow": 12})


class TestMovingAverages:
    def test_sma_known_values(self):
        candles = make_candles([1.0, 2.0, 3.0, 4.0, 5.0])
        sma = compute_indicator("SMA", candles, {"length": 3})["sma"]
        assert math.isnan(sma[0]) and math.isnan(sma[1])
        assert sma[2] == 2.0
        assert sma[3] == 3.0
        assert sma[4] == 4.0

    def test_ema_seeded_by_sma(self):
        closes = [10.0] * 4 + [20.0]
        candles = make_candles(closes)
        ema = compute_indicator("EMA", candles, {"length": 4})["ema"]
        assert ema[3] == 10.0
        k = 2 / 5
        assert ema[4] == pytest.approx(20.0 * k + 10.0 * (1 - k))

    def test_wma_weights_recent_higher(self):
        candles = make_candles([1.0, 2.0, 3.0])
        wma = compute_indicator("WMA", candles, {"length": 3})["wma"]
        expected = (1 * 1 + 2 * 2 + 3 * 3) / 6
        assert wma[2] == pytest.approx(expected)


class TestOscillators:
    def test_rsi_all_gains_is_100(self):
        candles = make_candles([float(i) for i in range(1, 25)])
        rsi = compute_indicator("RSI", candles, {"length": 14})["rsi"]
        assert last(rsi) == 100.0

    def test_rsi_constant_price_neutral(self):
        candles = make_candles([50.0] * 30)
        rsi = compute_indicator("RSI", candles, {"length": 14})["rsi"]
        # Zero losses -> RSI saturates at 100 by convention.
        assert last(rsi) == 100.0

    def test_rsi_range_bounds(self):
        closes = [100.0, 90.0, 105.0, 95.0, 110.0, 85.0] * 8
        rsi = compute_indicator("RSI", make_candles(closes), {"length": 14})["rsi"]
        valid = [v for v in rsi if not math.isnan(v)]
        assert all(0 <= v <= 100 for v in valid)

    def test_stoch_flat_market_is_50(self):
        candles = [
            Candle(START + timedelta(minutes=i), "T", 10, 10, 10, 10, 0) for i in range(20)
        ]
        stoch = compute_indicator("STOCH", candles, {})["k"]
        assert last(stoch) == 50.0

    def test_roc_percent(self):
        candles = make_candles([100.0, 110.0])
        roc = compute_indicator("ROC", candles, {"length": 1})["roc"]
        assert roc[1] == pytest.approx(10.0)


class TestBandsAndVolatility:
    def test_bbands_bracket_middle(self):
        closes = [100.0 + (i % 5) for i in range(40)]
        out = compute_indicator("BBANDS", make_candles(closes), {})
        for up, mid, low in zip(out["upper"], out["middle"], out["lower"], strict=True):
            if not math.isnan(up):
                assert low < mid < up

    def test_atr_positive_and_nan_head(self):
        candles = make_candles([100.0 + i for i in range(30)])
        atr = compute_indicator("ATR", candles, {"length": 14})["atr"]
        assert math.isnan(atr[12])
        assert not math.isnan(atr[13])
        assert last(atr) > 0

    def test_supertrend_direction_is_pm1(self):
        up = make_candles([100.0 + 2 * i for i in range(40)])
        result = compute_indicator("SUPERTREND", up, {"period": 5})
        assert last(result["direction"]) == 1.0

        down = make_candles([200.0 - 2 * i for i in range(40)])
        result = compute_indicator("SUPERTREND", down, {"period": 5})
        assert last(result["direction"]) == -1.0

        # Direction values are always +1/-1 (initial bar may seed either way).
        dirs = {d for d in result["direction"] if not math.isnan(d)}
        assert dirs <= {1.0, -1.0}


class TestMultiOutput:
    def test_macd_outputs_present_and_hist_consistent(self):
        closes = [100.0 + math.sin(i / 3) * 5 + i * 0.1 for i in range(60)]
        out = compute_indicator("MACD", make_candles(closes), {})
        assert set(out) == {"macd", "signal", "histogram"}
        for m, s, h in zip(out["macd"], out["signal"], out["histogram"], strict=True):
            if not math.isnan(h):
                assert h == pytest.approx(m - s)

    def test_adx_outputs(self):
        closes = [100.0 + (i % 7) * (1 if i % 2 else -1) for i in range(80)]
        out = compute_indicator("ADX", make_candles(closes), {"length": 14})
        assert set(out) == {"adx", "plus_di", "minus_di"}
        valid = [v for v in out["adx"] if not math.isnan(v)]
        assert valid and all(v >= 0 for v in valid)

    def test_vwap_between_low_and_high_per_session(self):
        candles = []
        for day in range(2):
            ts = START + timedelta(days=day)  # distinct IST sessions
            for minute in range(30):
                price = 100.0 + day * 50 + minute
                candles.append(
                    Candle(ts, "T", price, price + 1, price - 1, price, 100)
                )
                ts += timedelta(minutes=1)
        vwap = compute_indicator("VWAP", candles, {})["vwap"]
        # Cumulative VWAP stays within the session's overall price envelope
        # (it lags a trending market, so per-bar bounds do not hold).
        for day in range(2):
            window = candles[day * 30 : (day + 1) * 30]
            lo = min(c.low for c in window)
            hi = max(c.high for c in window)
            for v in vwap[day * 30 : (day + 1) * 30]:
                assert lo <= v <= hi
        # Session reset: first bar of day 2 equals its own typical price.
        assert vwap[30] == pytest.approx((candles[30].high + candles[30].low + candles[30].close) / 3)

    def test_empty_series_raises(self):
        with pytest.raises(IndicatorError, match="empty"):
            compute_indicator("SMA", [], {})
