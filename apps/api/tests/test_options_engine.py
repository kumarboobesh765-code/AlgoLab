"""Tests for options backtest engine and API endpoints."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.backtest.options_engine import OptionsBacktestError, OptionsConfig, run_options_backtest_quick
from app.marketdata.base import Candle
from app.quant.options import (
    black_scholes_price,
    calculate_atm_strike,
    calculate_greeks,
    calculate_greeks_heatmap,
    calculate_iv_rank_percentile,
    calculate_max_pain,
    calculate_pcr,
    capital_pct_lots,
    delta_neutral_lots,
    gamma_neutral_lots,
    get_option_chain_analytics,
    get_weekly_expiry,
    implied_volatility,
    parse_expiry_formula,
    parse_strike_formula,
    vega_neutral_lots,
)
from app.quant.options.analytics import OptionChainSnapshot

T0 = datetime(2026, 6, 1, 9, 15, tzinfo=UTC)


def make_option_candles(closes: list[float], spot_start: float = 20000.0) -> list[Candle]:
    """Build candles from a close series; open = prev close."""
    candles = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev if i > 0 else c
        hi = max(o, c)
        lo = min(o, c)
        candles.append(
            Candle(
                timestamp=T0 + timedelta(minutes=5 * i),
                instrument_id="NIFTY",
                open=o,
                high=hi,
                low=lo,
                close=c,
                volume=1000,
                oi=5000,
            )
        )
        prev = c
    return candles


class TestBlackScholesPricing:
    def test_call_itm(self):
        price = black_scholes_price(spot=21000, strike=20000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert price > 0
        assert price > 21000 - 20000  # Should be above intrinsic

    def test_put_itm(self):
        price = black_scholes_price(spot=20000, strike=21000, days_to_expiry=30, volatility=0.20, option_type="PE")
        assert price > 0
        assert price > 21000 - 20000

    def test_call_atm(self):
        price = black_scholes_price(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert price > 0

    def test_put_atm(self):
        price = black_scholes_price(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="PE")
        assert price > 0

    def test_at_expiry_intrinsic(self):
        call_price = black_scholes_price(spot=21000, strike=20000, days_to_expiry=0, volatility=0.20, option_type="CE")
        assert call_price == 1000.0
        put_price = black_scholes_price(spot=21000, strike=22000, days_to_expiry=0, volatility=0.20, option_type="PE")
        assert put_price == 1000.0

    def test_otm_option_has_time_value(self):
        price = black_scholes_price(spot=22000, strike=21000, days_to_expiry=30, volatility=0.20, option_type="CE")
        intrinsic = max(22000 - 21000, 0)
        assert price >= intrinsic

    def test_zero_volatility_returns_zero(self):
        price = black_scholes_price(spot=22000, strike=22000, days_to_expiry=30, volatility=0.0, option_type="CE")
        assert price == 0.0

    def test_negative_days_returns_intrinsic(self):
        price = black_scholes_price(spot=21000, strike=20000, days_to_expiry=-5, volatility=0.20, option_type="CE")
        assert price == 1000.0


class TestGreeksCalculation:
    def test_call_delta_between_zero_and_one(self):
        greeks = calculate_greeks(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert 0 < greeks.delta < 1

    def test_put_delta_between_minus_one_and_zero(self):
        greeks = calculate_greeks(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="PE")
        assert -1 < greeks.delta < 0

    def test_itm_call_delta_near_one(self):
        greeks = calculate_greeks(spot=23000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert greeks.delta > 0.7

    def test_otm_call_delta_near_zero(self):
        greeks = calculate_greeks(spot=21000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert greeks.delta < 0.3

    def test_gamma_positive(self):
        greeks = calculate_greeks(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert greeks.gamma > 0

    def test_theta_negative_long(self):
        greeks = calculate_greeks(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert greeks.theta < 0  # Long options lose time value

    def test_vega_positive(self):
        greeks = calculate_greeks(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert greeks.vega > 0

    def test_atm_gamma_highest(self):
        atm = calculate_greeks(spot=22000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        itm = calculate_greeks(spot=23000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        otm = calculate_greeks(spot=21000, strike=22000, days_to_expiry=30, volatility=0.20, option_type="CE")
        assert atm.gamma > itm.gamma
        assert atm.gamma > otm.gamma


class TestImpliedVolatility:
    def test_roundtrip_accuracy(self):
        spot, strike, dte, vol = 22000, 22000, 30, 0.25
        price = black_scholes_price(spot, strike, dte, vol, option_type="CE")
        iv = implied_volatility(price, spot, strike, dte, option_type="CE")
        assert abs(iv - vol) < 0.001

    def test_itm_roundtrip(self):
        spot, strike, dte, vol = 23000, 22000, 30, 0.20
        price = black_scholes_price(spot, strike, dte, vol, option_type="CE")
        iv = implied_volatility(price, spot, strike, dte, option_type="CE")
        assert abs(iv - vol) < 0.01

    def test_otm_roundtrip(self):
        spot, strike, dte, vol = 21000, 22000, 30, 0.20
        price = black_scholes_price(spot, strike, dte, vol, option_type="CE")
        iv = implied_volatility(price, spot, strike, dte, option_type="CE")
        assert abs(iv - vol) < 0.01

    def test_zero_iv_for_intrinsic(self):
        iv = implied_volatility(1000, 22000, 21000, 0, option_type="CE")
        assert iv == 0.0


class TestStrikeFormulas:
    def test_atm_strike_rounds_to_interval(self):
        assert calculate_atm_strike(22015, 50) == 22000
        assert calculate_atm_strike(22035, 50) == 22050

    def test_parse_atm(self):
        result = parse_strike_formula("ATM", 22000, 50)
        assert result.strike == 22000
        assert result.formula_used == "ATM"

    def test_parse_offset(self):
        result = parse_strike_formula("ATM+200", 22000, 50)
        assert result.strike == 22200

    def test_parse_negative_offset(self):
        result = parse_strike_formula("ATM-100", 22000, 50)
        assert result.strike == 21900

    def test_parse_percent(self):
        result = parse_strike_formula("SPOT+5%", 20000, 50)
        assert result.strike == 21000

    def test_parse_fixed_strike(self):
        result = parse_strike_formula("22500", 22000, 50)
        assert result.strike == 22500


class TestExpiryFormulas:
    def test_parse_this_week(self):
        result = parse_expiry_formula("THIS_WEEK")
        assert result.weekday() == 3  # Thursday

    def test_parse_next_week(self):
        this_week = get_weekly_expiry(date.today())
        result = parse_expiry_formula("NEXT_WEEK")
        assert (result - this_week).days >= 7

    def test_parse_this_month(self):
        result = parse_expiry_formula("THIS_MONTH")
        assert result.weekday() == 3  # Thursday

    def test_parse_fixed_date(self):
        result = parse_expiry_formula("2025-12-25")
        assert result == date(2025, 12, 25)


class TestGreeksNeutralSizing:
    def test_delta_neutral_single_leg(self):
        legs = [{"strike": 22000, "option_type": "CE", "action": "buy", "base_lots": 1}]
        result = delta_neutral_lots(legs, 22000, 30, 0.20)
        assert result.formula_used == "DELTA_NEUTRAL"

    def test_vega_neutral(self):
        legs = [
            {"strike": 22000, "option_type": "CE", "action": "buy", "base_lots": 1},
            {"strike": 22000, "option_type": "PE", "action": "sell", "base_lots": 1},
        ]
        result = vega_neutral_lots(legs, 22000, 30, 0.20)
        assert result.formula_used == "VEGA_NEUTRAL"

    def test_gamma_neutral(self):
        legs = [
            {"strike": 22000, "option_type": "CE", "action": "buy", "base_lots": 1},
            {"strike": 22000, "option_type": "PE", "action": "sell", "base_lots": 1},
        ]
        result = gamma_neutral_lots(legs, 22000, 30, 0.20)
        assert result.formula_used == "GAMMA_NEUTRAL"


class TestCapitalPctSizing:
    def test_capital_pct_lots(self):
        result = capital_pct_lots(capital=100000, premium_per_lot=5000, pct=10, lot_size=50)
        assert result.lots >= 1
        assert "CAPITAL_PCT" in result.formula_used


class TestOptionChainAnalytics:
    def test_pcr_calculation(self):
        chain = OptionChainSnapshot(
            underlying="NIFTY",
            expiry=date.today(),
            spot=22000,
            strikes=[21500, 22000, 22500],
            call_oi={21500: 1000, 22000: 5000, 22500: 2000},
            call_volume={21500: 100, 22000: 500, 22500: 200},
            call_ltp={21500: 50, 22000: 200, 22500: 10},
            call_bid={21500: 49, 22000: 199, 22500: 9},
            call_ask={21500: 51, 22000: 201, 22500: 11},
            put_oi={21500: 500, 22000: 3000, 22500: 4000},
            put_volume={21500: 50, 22000: 300, 22500: 400},
            put_ltp={21500: 10, 22000: 180, 22500: 400},
            put_bid={21500: 9, 22000: 179, 22500: 399},
            put_ask={21500: 11, 22000: 181, 22500: 401},
        )
        pcr = calculate_pcr(chain)
        assert pcr.pcr_oi > 0
        assert pcr.total_call_oi == 8000
        assert pcr.total_put_oi == 7500

    def test_max_pain_calculation(self):
        chain = OptionChainSnapshot(
            underlying="NIFTY",
            expiry=date.today(),
            spot=22000,
            strikes=[21000, 21500, 22000, 22500, 23000],
            call_oi={21000: 100, 21500: 200, 22000: 5000, 22500: 300, 23000: 100},
            call_volume={s: 10 for s in [21000, 21500, 22000, 22500, 23000]},
            call_ltp={s: 10 for s in [21000, 21500, 22000, 22500, 23000]},
            call_bid={s: 9 for s in [21000, 21500, 22000, 22500, 23000]},
            call_ask={s: 11 for s in [21000, 21500, 22000, 22500, 23000]},
            put_oi={21000: 5000, 21500: 3000, 22000: 2000, 22500: 500, 23000: 100},
            put_volume={s: 10 for s in [21000, 21500, 22000, 22500, 23000]},
            put_ltp={s: 10 for s in [21000, 21500, 22000, 22500, 23000]},
            put_bid={s: 9 for s in [21000, 21500, 22000, 22500, 23000]},
            put_ask={s: 11 for s in [21000, 21500, 22000, 22500, 23000]},
        )
        max_pain = calculate_max_pain(chain)
        assert max_pain.max_pain_strike == 22000.0

    def test_greeks_heatmap(self):
        chain = OptionChainSnapshot(
            underlying="NIFTY",
            expiry=date.today(),
            spot=22000,
            strikes=[21800, 21900, 22000, 22100, 22200],
            call_oi={s: 1000 for s in [21800, 21900, 22000, 22100, 22200]},
            call_volume={s: 100 for s in [21800, 21900, 22000, 22100, 22200]},
            call_ltp={s: 300 for s in [21800, 21900, 22000, 22100, 22200]},
            call_bid={s: 299 for s in [21800, 21900, 22000, 22100, 22200]},
            call_ask={s: 301 for s in [21800, 21900, 22000, 22100, 22200]},
            put_oi={s: 1000 for s in [21800, 21900, 22000, 22100, 22200]},
            put_volume={s: 100 for s in [21800, 21900, 22000, 22100, 22200]},
            put_ltp={s: 100 for s in [21800, 21900, 22000, 22100, 22200]},
            put_bid={s: 99 for s in [21800, 21900, 22000, 22100, 22200]},
            put_ask={s: 101 for s in [21800, 21900, 22000, 22100, 22200]},
        )
        heatmap = calculate_greeks_heatmap(chain)
        assert heatmap.underlying == "NIFTY"
        assert len(heatmap.strike_greeks) > 0

    def test_iv_rank_percentile(self):
        result = calculate_iv_rank_percentile(0.20, [0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.30])
        assert result.current_iv == 0.20
        assert result.iv_rank == 50.0

    def test_get_option_chain_analytics(self):
        chain = OptionChainSnapshot(
            underlying="NIFTY",
            expiry=date.today(),
            spot=22000,
            strikes=[21800, 22000, 22200],
            call_oi={21800: 1000, 22000: 5000, 22200: 2000},
            call_volume={21800: 100, 22000: 500, 22200: 200},
            call_ltp={21800: 400, 22000: 200, 22200: 10},
            call_bid={21800: 399, 22000: 199, 22200: 9},
            call_ask={21800: 401, 22000: 201, 22200: 11},
            put_oi={21800: 500, 22000: 3000, 22200: 4000},
            put_volume={21800: 50, 22000: 300, 22200: 400},
            put_ltp={21800: 10, 22000: 180, 22200: 400},
            put_bid={21800: 9, 22000: 179, 22200: 399},
            put_ask={21800: 11, 22000: 181, 22200: 401},
        )
        analytics = get_option_chain_analytics([chain])
        assert "pcr" in analytics
        assert "max_pain" in analytics
        assert "greeks_heatmap" in analytics


class TestOptionsBacktestEngine:
    def test_basic_long_call(self):
        candles = make_option_candles([22000, 22100, 22200, 22300, 22400, 22500, 22600])
        legs = [{"action": "buy", "option_type": "CE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"}]
        result = run_options_backtest_quick(legs, candles, OptionsConfig(initial_capital=100000))
        assert len(result.legs) > 0
        assert "initial_capital" in result.summary

    def test_straddle_strategy(self):
        candles = make_option_candles([22000, 22050, 22000, 21950, 22000, 22050, 22000])
        legs = [
            {"action": "buy", "option_type": "CE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"},
            {"action": "buy", "option_type": "PE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"},
        ]
        result = run_options_backtest_quick(legs, candles, OptionsConfig(initial_capital=100000))
        assert len(result.legs) == 2

    def test_short_straddle(self):
        candles = make_option_candles([22000, 22050, 22000, 21950, 22000, 22050, 22000])
        legs = [
            {"action": "sell", "option_type": "CE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"},
            {"action": "sell", "option_type": "PE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"},
        ]
        result = run_options_backtest_quick(legs, candles, OptionsConfig(initial_capital=100000))
        assert len(result.legs) == 2

    def test_iron_condor(self):
        candles = make_option_candles([22000] * 10)
        legs = [
            {"action": "sell", "option_type": "CE", "strike_formula": "ATM+200", "lots": 1, "expiry_formula": "THIS_WEEK"},
            {"action": "buy", "option_type": "CE", "strike_formula": "ATM+400", "lots": 1, "expiry_formula": "THIS_WEEK"},
            {"action": "sell", "option_type": "PE", "strike_formula": "ATM-200", "lots": 1, "expiry_formula": "THIS_WEEK"},
            {"action": "buy", "option_type": "PE", "strike_formula": "ATM-400", "lots": 1, "expiry_formula": "THIS_WEEK"},
        ]
        result = run_options_backtest_quick(legs, candles, OptionsConfig(initial_capital=100000))
        assert len(result.legs) == 4

    def test_requires_at_least_one_leg(self):
        with pytest.raises(OptionsBacktestError, match="at least one leg"):
            run_options_backtest_quick([], make_option_candles([22000] * 10))

    def test_daily_values_tracked(self):
        candles = make_option_candles([22000, 22100, 22200, 22300, 22400])
        legs = [{"action": "buy", "option_type": "CE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"}]
        result = run_options_backtest_quick(legs, candles, OptionsConfig(initial_capital=100000))
        assert len(result.daily_values) == len(candles)

    def test_cost_breakdown_present(self):
        candles = make_option_candles([22000, 22100, 22200])
        legs = [{"action": "buy", "option_type": "CE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"}]
        result = run_options_backtest_quick(legs, candles, OptionsConfig(initial_capital=100000))
        assert "stt" in result.cost_breakdown
        assert "brokerage" in result.cost_breakdown


class TestOptionsAPIEndpoints:
    @pytest.mark.asyncio
    async def test_options_analytics_endpoint(self, client, auth_headers):
        from app.core.deps import get_provider_instance
        from app.main import app
        from app.marketdata.demo import DemoProvider
        app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()

        resp = await client.post(
            "/api/v1/options/analytics",
            json={"underlying": "NIFTY", "expiry": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "pcr" in body
        assert "max_pain" in body
        assert "iv_surface" in body
        assert "greeks_heatmap" in body

    @pytest.mark.asyncio
    async def test_options_backtest_endpoint(self, client, auth_headers):
        from app.core.deps import get_provider_instance
        from app.main import app
        from app.marketdata.demo import DemoProvider
        app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()

        resp = await client.post(
            "/api/v1/options/backtest",
            json={
                "underlying": "NIFTY",
                "legs": [
                    {"action": "buy", "option_type": "CE", "strike_formula": "ATM", "lots": 1, "expiry_formula": "THIS_WEEK"}
                ],
                "dte_days": 7,
                "volatility": 0.20,
                "lot_size": 50,
                "initial_capital": 100000,
                "auto_roll": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "legs" in body
        assert "summary" in body
        assert "cost_breakdown" in body
