"""`GET /quant/series` — the charting overlay endpoint.

Covers the spec-token parser (bare, positional, explicit, bad input) and the
endpoint contract that the chart terminal depends on: index alignment between
candles and indicator series, null (not NaN) for warm-up gaps, per-token error
isolation, and that multi-output indicators come back whole.
"""

import math

import pytest

from app.api.v1.quant import _jsonable, _parse_indicator_token, _split_indicator_tokens
from app.quant.indicators import IndicatorError

PARAMS = {
    "user": {"id": "u", "email": "a@b.c", "is_active": True},
    "auth_headers": {},
}


class TestTokenParser:
    def test_bare_type_uses_defaults(self):
        assert _parse_indicator_token("SMA") == ("SMA", {})

    def test_type_is_uppercased(self):
        assert _parse_indicator_token("sma")[0] == "SMA"

    def test_explicit_params(self):
        assert _parse_indicator_token("SMA:length=50") == ("SMA", {"length": 50})

    def test_multiple_explicit_params(self):
        typ, params = _parse_indicator_token("KAMA:length=10,fast=2,slow=30")
        assert typ == "KAMA"
        assert params == {"length": 10, "fast": 2, "slow": 30}

    def test_float_param(self):
        _, params = _parse_indicator_token("BBANDS:length=20,stddev=2.5")
        assert params == {"length": 20, "stddev": 2.5}

    def test_positional_shorthand(self):
        assert _parse_indicator_token("RSI:21") == ("RSI", {"length": 21})

    def test_string_param_value(self):
        _, params = _parse_indicator_token("SMA:source=hlc3")
        assert params == {"source": "hlc3"}

    def test_whitespace_tolerated(self):
        assert _parse_indicator_token("  SMA : length = 30 ") == ("SMA", {"length": 30})

    def test_unknown_indicator_rejected(self):
        with pytest.raises(IndicatorError, match="Unknown indicator"):
            _parse_indicator_token("NOT_REAL")

    def test_unknown_param_rejected(self):
        with pytest.raises(IndicatorError, match="unknown parameter"):
            _parse_indicator_token("SMA:bogus=3")

    def test_non_numeric_for_int_param_rejected(self):
        with pytest.raises(IndicatorError):
            _parse_indicator_token("SMA:length=abc")

    def test_empty_token_rejected(self):
        with pytest.raises(IndicatorError):
            _parse_indicator_token("   ")

    def test_paramless_indicator_with_value_rejected(self):
        # OBV takes no params, so a positional token is meaningless
        with pytest.raises(IndicatorError):
            _parse_indicator_token("OBV:5")


class TestTokenSplitting:
    """The comma is overloaded: it separates tokens AND separates parameters.

    ``BBANDS:length=20,stddev=2`` is one token with two params, while
    ``SMA:20,RSI:14`` is two tokens. Splitting naively on "," silently broke
    every multi-parameter indicator, including in /quant/series.
    """

    def test_multi_param_token_stays_one_token(self):
        assert _split_indicator_tokens("BBANDS:length=20,stddev=2") == [
            "BBANDS:length=20,stddev=2"
        ]

    def test_three_params_plus_next_indicator(self):
        assert _split_indicator_tokens("KAMA:length=10,fast=2,slow=30,RSI:14") == [
            "KAMA:length=10,fast=2,slow=30",
            "RSI:14",
        ]

    def test_simple_list_unchanged(self):
        assert _split_indicator_tokens("SMA:length=10,RSI:14") == [
            "SMA:length=10",
            "RSI:14",
        ]

    def test_unknown_indicator_is_its_own_token(self):
        """An unrecognised name must surface as its own error rather than
        being absorbed into a neighbour's parameter list."""
        assert _split_indicator_tokens("SMA:20,NOT_REAL,RSI:14") == [
            "SMA:20",
            "NOT_REAL",
            "RSI:14",
        ]

    def test_stddev_param_not_confused_with_stddev_indicator(self):
        """STDDEV is both a real indicator and a parameter of BBANDS."""
        assert _split_indicator_tokens("STDDEV:20,BBANDS:length=20,stddev=2") == [
            "STDDEV:20",
            "BBANDS:length=20,stddev=2",
        ]

    def test_bare_then_positional_then_keyed(self):
        assert _split_indicator_tokens("SMA,SMA:14,SMA:length=9") == [
            "SMA",
            "SMA:14",
            "SMA:length=9",
        ]

    def test_empty_and_whitespace(self):
        assert _split_indicator_tokens("") == []
        assert _split_indicator_tokens(" , ") == []

    def test_split_token_reaches_parser_intact(self):
        (ind_type, params) = _parse_indicator_token("BBANDS:length=20,stddev=2")
        assert ind_type == "BBANDS"
        assert params == {"length": 20, "stddev": 2.0}


class TestJsonable:
    def test_nan_becomes_none(self):
        assert _jsonable([1.0, math.nan, 3.0]) == [1.0, None, 3.0]

    def test_finite_values_untouched(self):
        assert _jsonable([1.5, -2.5]) == [1.5, -2.5]

    def test_all_nan(self):
        assert _jsonable([math.nan, math.nan]) == [None, None]


class TestSeriesEndpoint:
    async def test_returns_candles_and_no_series_by_default(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m", headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "NIFTY"
        assert body["timeframe"] == "5m"
        assert body["bars"] == len(body["candles"])
        assert body["series"] == {}
        assert body["errors"] == {}

    async def test_candle_shape_is_lightweight_charts_compatible(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&bars=60", headers=auth_headers
        )
        assert r.status_code == 200
        candles = r.json()["candles"]
        assert len(candles) == 60
        for c in candles:
            assert set(c) >= {"time", "open", "high", "low", "close", "volume"}
            assert isinstance(c["time"], int)
            assert c["low"] <= c["open"] <= c["high"]
            assert c["low"] <= c["close"] <= c["high"]

    async def test_candles_are_time_ordered_and_unique(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&bars=100", headers=auth_headers
        )
        times = [c["time"] for c in r.json()["candles"]]
        assert times == sorted(times)
        assert len(times) == len(set(times))

    async def test_single_indicator_series_is_aligned_to_candles(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&indicators=SMA:length=10&bars=80",
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        bars = len(body["candles"])
        (only,) = body["series"].values()
        (values,) = only.values()
        assert len(values) == bars

    async def test_warmup_is_null_not_nan(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&indicators=SMA:length=20&bars=80",
            headers=auth_headers,
        )
        (only,) = r.json()["series"].values()
        (values,) = only.values()
        assert values[0] is None
        assert any(v is not None for v in values)
        assert not any(isinstance(v, float) and math.isnan(v) for v in values)

    async def test_multi_output_indicator_returns_every_output(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&indicators=BBANDS&bars=60",
            headers=auth_headers,
        )
        (only,) = r.json()["series"].values()
        assert set(only) == {"upper", "middle", "lower"}

    async def test_multiple_indicators_each_get_a_key(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m"
            "&indicators=SMA:length=10,EMA:length=20,RSI:14&bars=80",
            headers=auth_headers,
        )
        series = r.json()["series"]
        assert set(series) == {"SMA:length=10", "EMA:length=20", "RSI:14"}

    async def test_bad_token_is_isolated_not_fatal(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m"
            "&indicators=SMA:length=10,NOPE_XYZ,RSI:14&bars=60",
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        # the good ones still render
        assert "SMA:length=10" in body["series"]
        assert "RSI:14" in body["series"]
        # the bad one is reported rather than killing the chart
        assert "NOPE_XYZ" in body["errors"]

    async def test_invalid_param_value_is_reported(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&indicators=SMA:length=99999&bars=60",
            headers=auth_headers,
        )
        body = r.json()
        assert body["series"] == {}
        assert "SMA:length=99999" in body["errors"]

    async def test_all_new_indicators_are_reachable(self, client, auth_headers):
        """Every registered indicator must be expressible as a chart overlay."""
        from app.quant.indicators import INDICATORS

        bad = []
        for name in INDICATORS:
            try:
                _parse_indicator_token(name)
            except IndicatorError as exc:
                bad.append((name, str(exc)))
        assert not bad, f"not expressible as overlays: {bad}"

    async def test_requires_auth(self, client):
        r = await client.get("/api/v1/quant/series?symbol=NIFTY&interval=5m")
        assert r.status_code in (401, 403)

    async def test_bars_bound_is_enforced(self, client, auth_headers):
        r = await client.get(
            "/api/v1/quant/series?symbol=NIFTY&interval=5m&bars=99999", headers=auth_headers
        )
        assert r.status_code == 422
