"""Regression tests for the extended indicator library (indicators_ext).

Every kernel is exercised for three properties:
  1. it computes without raising on a realistic series,
  2. it returns exactly the output names declared in its spec, each aligned to
     the input length,
  3. its warm-up region is NaN-padded and it produces finite values later.

Numeric correctness is spot-checked for the families where an independent
reference value is easy to derive (SMA/RSI/OBV/STDDEV/linear regression).
"""

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
from app.quant.indicators_ext import EXTENDED_SPECS

NEW_INDICATORS = [
    "SMMA", "DEMA", "TEMA", "ZEMA", "HMA", "VWMA", "ALMA", "KAMA", "T3",
    "MOM", "CCI", "WILLR", "MFI", "TRIX", "TSI", "ULTOSC", "CMO", "PPO",
    "AO", "AROON", "DPO", "STOCHRSI",
    "NATR", "STDDEV", "DONCHIAN", "KC", "HV",
    "OBV", "AD", "PVT", "CMF", "EOM", "EFI", "NVI",
    "LINEARREG",
]


def _candles(n: int = 220) -> list[Candle]:
    """Deterministic pseudo-random OHLCV walk with a mild upward drift."""
    out: list[Candle] = []
    price = 1000.0
    ts = datetime(2024, 1, 1, 3, 30, tzinfo=UTC)
    for i in range(n):
        # deterministic LCG so tests never flake
        wiggle = math.sin(i * 0.7) * 6 + math.cos(i * 0.23) * 4
        drift = i * 0.15
        close = price + wiggle + drift
        open_ = price
        high = max(open_, close) + 2 + abs(wiggle) * 0.3
        low = min(open_, close) - 2 - abs(wiggle) * 0.3
        volume = 1000 + (i * 37) % 900 + abs(wiggle) * 40
        out.append(
            Candle(
                timestamp=ts + timedelta(minutes=i),
                instrument_id="TEST",
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                oi=10000 + i,
            )
        )
        price = close
    return out


CANDLES = _candles()


class TestRegistry:
    def test_extended_specs_registered(self):
        for name in NEW_INDICATORS:
            assert name in INDICATORS, f"{name} missing from INDICATORS"
            assert name in EXTENDED_SPECS

    def test_registry_grew_to_53(self):
        assert len(INDICATORS) == 53

    def test_no_extended_name_collides_with_core(self):
        core_only = {"SMA", "EMA", "WMA", "RSI", "MACD", "BBANDS", "ATR",
                     "SUPERTREND", "STOCH", "ADX", "VWAP", "ROC", "IV",
                     "OPTION_DELTA", "OPTION_GAMMA", "OPTION_THETA",
                     "OPTION_VEGA", "OPTION_PRICE"}
        assert not (set(NEW_INDICATORS) & core_only)

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_every_extended_indicator_has_a_kernel(self, name):
        # must not raise "No implementation registered"
        result = compute_indicator(name, CANDLES, {})
        assert result


class TestOutputContract:
    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_outputs_match_spec_and_length(self, name):
        spec = INDICATORS[name]
        result = compute_indicator(name, CANDLES, {})
        assert tuple(result.keys()) == spec.outputs, f"{name} output mismatch"
        for series in result.values():
            assert len(series) == len(CANDLES), f"{name} length mismatch"

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_produces_finite_values_after_warmup(self, name):
        result = compute_indicator(name, CANDLES, {})
        for series in result.values():
            finite = [v for v in series if not math.isnan(v)]
            assert finite, f"{name} produced no finite values"
            assert all(math.isfinite(v) for v in finite), f"{name} produced inf"

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_leading_region_is_nan_padded(self, name):
        # Cumulative studies legitimately start at 0 rather than NaN.
        if name in {"OBV", "AD", "PVT"}:
            pytest.skip(f"{name} is cumulative; starts at zero by definition")
        result = compute_indicator(name, CANDLES, {})
        # every series must start with at least one NaN (warm-up)
        for series in result.values():
            assert math.isnan(series[0]), f"{name} should NaN-pad index 0"

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_does_not_mutate_input(self, name):
        snapshot = [(c.open, c.high, c.low, c.close, c.volume) for c in CANDLES]
        compute_indicator(name, CANDLES, {})
        after = [(c.open, c.high, c.low, c.close, c.volume) for c in CANDLES]
        assert snapshot == after


class TestParamValidation:
    def test_unknown_indicator_rejected(self):
        with pytest.raises(IndicatorError):
            compute_indicator("NOT_AN_INDICATOR", CANDLES, {})

    def test_unknown_param_rejected(self):
        with pytest.raises(IndicatorError, match="unknown parameter"):
            validate_params("MOM", {"bogus": 1})

    def test_length_bounds_enforced(self):
        with pytest.raises(IndicatorError):
            validate_params("MOM", {"length": 0})

    def test_source_choices_enforced(self):
        with pytest.raises(IndicatorError):
            validate_params("MOM", {"source": "not_a_source"})

    def test_defaults_are_used(self):
        resolved = validate_params("CCI", {})
        assert resolved["length"] == 20
        assert resolved["source"] == "hlc3"

    def test_alma_zero_offset_rejected_at_compute(self):
        with pytest.raises(IndicatorError):
            compute_indicator("ALMA", CANDLES, {"offset": 0.0})


class TestNumericCorrectness:
    def test_sma_matches_manual_mean(self):
        out = compute_indicator("SMA", CANDLES, {"length": 5})["sma"]
        closes = [c.close for c in CANDLES]
        expected = sum(closes[10:15]) / 5
        assert out[14] == pytest.approx(expected)

    def test_rsi_stays_in_0_100(self):
        out = compute_indicator("RSI", CANDLES, {"length": 14})["rsi"]
        for v in out:
            if not math.isnan(v):
                assert 0.0 <= v <= 100.0

    def test_stoch_k_stays_in_0_100(self):
        k = compute_indicator("STOCH", CANDLES, {"k_length": 14})["k"]
        for v in k:
            if not math.isnan(v):
                assert 0.0 <= v <= 100.0

    def test_willr_stays_in_minus100_0(self):
        out = compute_indicator("WILLR", CANDLES, {"length": 14})["willr"]
        for v in out:
            if not math.isnan(v):
                assert -100.0 <= v <= 0.0

    def test_obv_accumulates_signed_volume(self):
        out = compute_indicator("OBV", CANDLES)["obv"]
        # manually recompute the first few steps
        expected = 0.0
        for i in range(1, 8):
            if CANDLES[i].close > CANDLES[i - 1].close:
                expected += CANDLES[i].volume
            elif CANDLES[i].close < CANDLES[i - 1].close:
                expected -= CANDLES[i].volume
            assert out[i] == pytest.approx(expected)

    def test_stddev_matches_population_formula(self):
        out = compute_indicator("STDDEV", CANDLES, {"length": 20})["stddev"]
        closes = [c.close for c in CANDLES]
        window = closes[100:120]
        mean = sum(window) / 20
        expected = math.sqrt(sum((v - mean) ** 2 for v in window) / 20)
        assert out[119] == pytest.approx(expected)

    def test_stddev_of_constant_window_is_zero(self):
        flat = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                instrument_id="T",
                open=10, high=10, low=10, close=10,
                volume=100, oi=0,
            )
            for i in range(60)
        ]
        out = compute_indicator("STDDEV", flat, {"length": 10})["stddev"]
        assert out[59] == pytest.approx(0.0)

    def test_linearreg_perfectly_linear_series(self):
        # close = 2*i + 1. The fit is window-relative (x = 0..length-1), so the
        # slope is a constant 2, the intercept tracks the window origin, and the
        # value at the right edge reproduces the actual close exactly.
        n = 60
        length = 10
        lin = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                instrument_id="T",
                open=2 * i + 1, high=2 * i + 1, low=2 * i + 1,
                close=2 * i + 1, volume=100, oi=0,
            )
            for i in range(n)
        ]
        res = compute_indicator("LINEARREG", lin, {"length": length})
        i = n - 1
        assert res["slope"][i] == pytest.approx(2.0, rel=1e-9)
        assert res["intercept"][i] == pytest.approx(2 * (i - length + 1) + 1, rel=1e-9)
        assert res["value"][i] == pytest.approx(2 * i + 1, rel=1e-9)

    def test_donchian_bounds_bracket_price(self):
        res = compute_indicator("DONCHIAN", CANDLES, {"length": 20})
        for i, c in enumerate(CANDLES):
            if math.isnan(res["upper"][i]):
                continue
            window = CANDLES[i - 19 : i + 1]
            assert res["upper"][i] == pytest.approx(max(w.high for w in window))
            assert res["lower"][i] == pytest.approx(min(w.low for w in window))
            assert res["lower"][i] <= c.close <= res["upper"][i]

    def test_keltner_upper_above_lower(self):
        res = compute_indicator("KC", CANDLES, {"length": 20, "multiplier": 2.0})
        for u, lo in zip(res["upper"], res["lower"], strict=True):
            if math.isnan(u):
                continue
            assert u > lo

    def test_bbands_upper_above_lower(self):
        res = compute_indicator("BBANDS", CANDLES, {"length": 20})
        for u, m, lo in zip(res["upper"], res["middle"], res["lower"], strict=True):
            if math.isnan(u):
                continue
            assert u > m > lo

    def test_mfi_stays_in_0_100(self):
        out = compute_indicator("MFI", CANDLES, {"length": 14})["mfi"]
        for v in out:
            if not math.isnan(v):
                assert 0.0 <= v <= 100.0

    def test_aroon_stays_in_0_100(self):
        res = compute_indicator("AROON", CANDLES, {"length": 14})
        for key in ("up", "down"):
            for v in res[key]:
                if not math.isnan(v):
                    assert 0.0 <= v <= 100.0

    def test_cci_can_exceed_100_but_is_finite(self):
        out = compute_indicator("CCI", CANDLES, {"length": 20})["cci"]
        finite = [v for v in out if not math.isnan(v)]
        assert finite
        assert all(math.isfinite(v) for v in finite)

    def test_cmo_stays_in_minus100_100(self):
        out = compute_indicator("CMO", CANDLES, {"length": 14})["cmo"]
        for v in out:
            if not math.isnan(v):
                assert -100.0 <= v <= 100.0

    def test_hv_is_non_negative(self):
        out = compute_indicator("HV", CANDLES, {"length": 20})["hv"]
        for v in out:
            if not math.isnan(v):
                assert v >= 0.0

    def test_natr_non_negative(self):
        out = compute_indicator("NATR", CANDLES, {"length": 14})["natr"]
        for v in out:
            if not math.isnan(v):
                assert v >= 0.0

    def test_zema_equals_2ema_minus_ema2(self):
        from app.quant.indicators import _ema
        from app.quant.indicators_ext import _ema_over

        closes = [c.close for c in CANDLES]
        e1 = _ema(closes, 20)
        e2 = _ema_over(e1, 20)
        expected = [2 * a - b for a, b in zip(e1, e2, strict=True)]
        out = compute_indicator("ZEMA", CANDLES, {"length": 20})["zema"]
        for got, exp in zip(out, expected, strict=True):
            if math.isnan(exp):
                assert math.isnan(got)
            else:
                assert got == pytest.approx(exp)

    def test_dema_equals_2ema_minus_ema_of_ema(self):
        from app.quant.indicators import _ema
        from app.quant.indicators_ext import _ema_over

        closes = [c.close for c in CANDLES]
        e1 = _ema(closes, 20)
        e2 = _ema_over(e1, 20)
        expected = [2 * a - b for a, b in zip(e1, e2, strict=True)]
        out = compute_indicator("DEMA", CANDLES, {"length": 20})["dema"]
        assert out[-1] == pytest.approx(expected[-1])

    def test_t3_has_unity_gain(self):
        # a flat input must pass through unchanged (coefficients sum to 1)
        n = 200
        level = 137.0
        flat = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                instrument_id="T",
                open=level, high=level, low=level, close=level,
                volume=500, oi=0,
            )
            for i in range(n)
        ]
        out = compute_indicator("T3", flat, {"length": 5, "vfactor": 0.7})["t3"]
        finite = [v for v in out if not math.isnan(v)]
        assert finite
        for v in finite:
            assert v == pytest.approx(level, rel=1e-9)

    def test_vwma_equals_volume_weighted_mean(self):
        length = 10
        out = compute_indicator("VWMA", CANDLES, {"length": length})["vwma"]
        i = 50
        window = CANDLES[i - length + 1 : i + 1]
        pv = sum(c.close * c.volume for c in window)
        vv = sum(c.volume for c in window)
        assert out[i] == pytest.approx(pv / vv)

    def test_ema_of_flat_series_is_flat(self):
        flat = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                instrument_id="T",
                open=50, high=50, low=50, close=50,
                volume=10, oi=0,
            )
            for i in range(80)
        ]
        for name in ("DEMA", "TEMA", "ZEMA", "HMA", "SMMA", "T3", "VWMA", "KAMA"):
            spec = INDICATORS[name]
            res = compute_indicator(name, flat, {})
            for key in spec.outputs:
                vals = [v for v in res[key] if not math.isnan(v)]
                if vals:
                    assert vals[-1] == pytest.approx(50.0, rel=1e-3), f"{name}.{key}"


class TestEdgeCases:
    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_short_series_does_not_crash(self, name):
        # fewer bars than most warm-up windows; must not raise
        compute_indicator(name, CANDLES[:5], {})

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_single_candle_does_not_crash(self, name):
        compute_indicator(name, CANDLES[:1], {})

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_zero_volume_series_does_not_crash(self, name):
        flat = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                instrument_id="T",
                open=10, high=11, low=9, close=10.5,
                volume=0, oi=0,
            )
            for i in range(60)
        ]
        compute_indicator(name, flat, {})

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_flat_prices_do_not_divide_by_zero(self, name):
        flat = [
            Candle(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                instrument_id="T",
                open=25, high=25, low=25, close=25,
                volume=100, oi=0,
            )
            for i in range(60)
        ]
        res = compute_indicator(name, flat, {})
        for series in res.values():
            for v in series:
                assert not math.isinf(v), f"{name} produced infinity"

    @pytest.mark.parametrize("name", NEW_INDICATORS)
    def test_empty_series_raises(self, name):
        with pytest.raises(IndicatorError):
            compute_indicator(name, [], {})
