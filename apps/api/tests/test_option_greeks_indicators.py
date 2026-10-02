"""Option-context indicators (IV / delta / gamma / theta / vega / price).

These six used to be stubs that returned an all-NaN series. They are now real
Black-Scholes computations driven by option context carried on each `Candle`
(strike, option type, expiry, underlying spot). The tests below pin the
financial behaviour that actually matters:

- a call's delta is in [0, 1] and a put's is in [-1, 0],
- delta is monotonically increasing in spot for a call,
- gamma and vega peak at the money and fall away from it,
- theta accelerates toward expiry,
- IV round-trips: solving IV from a BS price recovers the input sigma,
- non-option candles degrade to NaN instead of raising,
- put-call delta parity holds.
"""

import math
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta

import pytest

from app.marketdata.base import Candle
from app.options.greeks import bs_price
from app.quant.indicators import compute_indicator

EXPIRY = date(2025, 6, 26)
START = datetime(2025, 6, 2, 3, 30, tzinfo=UTC)


def _option_series(
    n: int = 40,
    spot0: float = 22000.0,
    strike: float = 22000.0,
    sigma: float = 0.15,
    kind: str = "CE",
    dte0: int = 20,
    spot_step: float = 40.0,
) -> list[Candle]:
    """A synthetic ATM option priced by Black-Scholes on each bar."""
    out: list[Candle] = []
    expiry = (START + timedelta(days=dte0)).date()
    for i in range(n):
        spot = spot0 + spot_step * i
        dte = max(dte0 - i, 0)
        years = dte / 365.0
        premium = bs_price(spot, strike, years, sigma, "call" if kind == "CE" else "put")
        out.append(
            Candle(
                timestamp=START + timedelta(days=i),
                instrument_id="NIFTY25JUN22200CE",
                open=premium,
                high=premium,
                low=premium,
                close=premium,
                volume=5000,
                oi=100000,
                strike=strike,
                option_type=kind,
                expiry=expiry,
                underlying_price=spot,
                iv=sigma,
            )
        )
    return out


class TestIvRoundTrip:
    @pytest.mark.parametrize("sigma", [0.08, 0.15, 0.3, 0.6])
    def test_iv_recovers_input_volatility(self, sigma):
        candles = _option_series(sigma=sigma)
        out = compute_indicator("IV", candles, {})["iv"]
        # IV is undefined once the option has expired; check the live bars only.
        live = [v for v in out if not math.isnan(v)]
        assert live
        for v in live:
            assert v == pytest.approx(sigma, rel=1e-4)

    def test_iv_solved_from_close_when_not_supplied(self):
        candles = _option_series()
        # drop the stored iv so the solver must work from the close
        stripped = [
            Candle(**{f.name: getattr(c, f.name) for f in fields(c)})
            for c in candles
        ]
        stripped[0].iv = None
        out = compute_indicator("IV", stripped[:5], {})["iv"]
        assert out[0] == pytest.approx(0.15, rel=1e-3)


class TestDelta:
    def test_call_delta_within_zero_one(self):
        out = compute_indicator("OPTION_DELTA", _option_series(), {})["delta"]
        for v in out:
            assert 0.0 <= v <= 1.0

    def test_put_delta_within_minus_one_zero(self):
        out = compute_indicator("OPTION_DELTA", _option_series(kind="PE"), {})["delta"]
        for v in out:
            assert -1.0 <= v <= 0.0

    def test_call_delta_increases_with_spot(self):
        out = compute_indicator("OPTION_DELTA", _option_series(), {})["delta"]
        for a, b in zip(out, out[1:], strict=False):
            assert b >= a - 1e-9

    def test_call_delta_is_half_at_the_money(self):
        out = compute_indicator("OPTION_DELTA", _option_series(spot_step=0.0), {})["delta"]
        assert out[10] == pytest.approx(0.5, abs=0.01)

    def test_delta_put_call_parity(self):
        calls = compute_indicator("OPTION_DELTA", _option_series(), {})["delta"]
        puts = compute_indicator("OPTION_DELTA", _option_series(kind="PE"), {})["delta"]
        for c, p in zip(calls, puts, strict=True):
            if math.isnan(c) or math.isnan(p):
                continue
            assert c - p == pytest.approx(1.0, abs=1e-6)


class TestGamma:
    def test_gamma_positive(self):
        out = compute_indicator("OPTION_GAMMA", _option_series(), {})["gamma"]
        for v in out:
            assert v >= 0.0

    def test_gamma_peaks_at_the_money(self):
        otm = compute_indicator("OPTION_GAMMA", _option_series(strike=26000.0), {})["gamma"]
        atm = compute_indicator("OPTION_GAMMA", _option_series(strike=22000.0), {})["gamma"]
        assert atm[0] > otm[0]

    def test_gamma_same_for_calls_and_puts(self):
        call = compute_indicator("OPTION_GAMMA", _option_series(), {})["gamma"]
        put = compute_indicator("OPTION_GAMMA", _option_series(kind="PE"), {})["gamma"]
        assert call[0] == pytest.approx(put[0], rel=1e-9)


class TestTheta:
    def test_theta_non_positive_for_long_options(self):
        out = compute_indicator("OPTION_THETA", _option_series(), {})["theta"]
        for v in out:
            assert v <= 0.0

    def test_theta_accelerates_toward_expiry(self):
        # same moneyness, fewer days left -> larger |theta|
        far = compute_indicator("OPTION_THETA", _option_series(dte0=60), {})["theta"]
        near = compute_indicator("OPTION_THETA", _option_series(dte0=5), {})["theta"]
        assert abs(near[0]) > abs(far[0])


class TestVega:
    def test_vega_non_negative(self):
        out = compute_indicator("OPTION_VEGA", _option_series(), {})["vega"]
        for v in out:
            assert v >= 0.0

    def test_vega_peaks_at_the_money(self):
        otm = compute_indicator("OPTION_VEGA", _option_series(strike=26000.0), {})["vega"]
        atm = compute_indicator("OPTION_VEGA", _option_series(strike=22000.0), {})["vega"]
        assert atm[0] > otm[0]

    def test_vega_same_for_calls_and_puts(self):
        call = compute_indicator("OPTION_VEGA", _option_series(), {})["vega"]
        put = compute_indicator("OPTION_VEGA", _option_series(kind="PE"), {})["vega"]
        assert call[0] == pytest.approx(put[0], rel=1e-9)


class TestTheoreticalPrice:
    def test_price_matches_black_scholes(self):
        candles = _option_series()
        out = compute_indicator("OPTION_PRICE", candles, {})["price"]
        for i, v in enumerate(out):
            spot = candles[i].underlying_price
            years = (candles[i].expiry - candles[i].timestamp.date()).days / 365.0
            assert v == pytest.approx(bs_price(spot, 22000.0, years, 0.15, "call"), rel=1e-9)


class TestGracefulDegradation:
    def _plain_series(self, n: int = 30) -> list[Candle]:
        return [
            Candle(
                timestamp=START + timedelta(days=i),
                instrument_id="NIFTY",
                open=100, high=101, low=99, close=100.5,
                volume=10, oi=0,
            )
            for i in range(n)
        ]

    @pytest.mark.parametrize(
        "name", ["IV", "OPTION_DELTA", "OPTION_GAMMA", "OPTION_THETA",
                 "OPTION_VEGA", "OPTION_PRICE"],
    )
    def test_non_option_candles_yield_nan_not_crash(self, name):
        result = compute_indicator(name, self._plain_series(), {})
        (series,) = result.values()
        assert len(series) == 30
        assert all(math.isnan(v) for v in series)

    @pytest.mark.parametrize(
        "name", ["IV", "OPTION_DELTA", "OPTION_GAMMA", "OPTION_THETA",
                 "OPTION_VEGA", "OPTION_PRICE"],
    )
    def test_missing_underlying_price_yields_nan(self, name):
        candles = [
            Candle(
                timestamp=START + timedelta(days=i),
                instrument_id="OPT",
                open=50, high=50, low=50, close=50,
                volume=1, oi=1,
                strike=22000.0,
                option_type="CE",
                expiry=EXPIRY,
                underlying_price=None,
            )
            for i in range(10)
        ]
        (series,) = compute_indicator(name, candles, {}).values()
        assert all(math.isnan(v) for v in series)

    def test_expired_option_collapses_to_intrinsic(self):
        # DTE = 0: price is intrinsic, greeks are the step functions
        candles = _option_series(n=1, spot0=22100.0, dte0=0)
        candles[0].expiry = candles[0].timestamp.date()
        price = compute_indicator("OPTION_PRICE", candles, {})["price"][0]
        assert price == pytest.approx(100.0, abs=1e-6)
        delta = compute_indicator("OPTION_DELTA", candles, {})["delta"][0]
        assert delta == pytest.approx(1.0)
        gamma = compute_indicator("OPTION_GAMMA", candles, {})["gamma"][0]
        assert gamma == pytest.approx(0.0)

    def test_unsolvable_iv_is_skipped(self):
        # close pinned at intrinsic -> no implied vol exists
        candles = _option_series(n=3, spot0=22100.0, dte0=10)
        for c in candles:
            c.iv = None
            c.close = 100.0  # intrinsic only
            c.open = c.high = c.low = 100.0
        out = compute_indicator("IV", candles, {})["iv"]
        assert all(math.isnan(v) for v in out)
