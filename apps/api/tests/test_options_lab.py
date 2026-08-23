import math

import pytest

from app.options import greeks
from app.options.lab import (
    LegInput,
    OptionsLabError,
    has_unlimited_side,
    monte_carlo,
    net_greeks,
    net_premium,
    payoff_curve,
    payoff_metrics,
    resolve_leg,
)

R = 0.065


def _leg(action, ot, off=0, lots=1):
    return LegInput(action=action, option_type=ot, strike_offset=off, lots=lots)


# ---------------------------------------------------------------- greeks


def test_put_call_parity():
    spot, strike, years, iv = 24_500, 25_000, 0.05, 0.14
    c = greeks.bs_price(spot, strike, years, iv, "call", R)
    p = greeks.bs_price(spot, strike, years, iv, "put", R)
    lhs = c - p
    rhs = spot - strike * math.exp(-R * years)
    assert abs(lhs - rhs) < 1e-6


def test_delta_bounds_and_atm_call():
    assert 0 < greeks.bs_delta(24_500, 24_000, 7 / 365, 0.15, "call", R) <= 1
    assert -1 <= greeks.bs_delta(24_500, 25_000, 7 / 365, 0.15, "put", R) < 0
    atm = greeks.bs_delta(24_500, 24_500, 1 / 365, 0.10, "call", R)
    assert abs(atm - 0.5) < 0.05


def test_second_order_greeks_signs():
    spot, strike, years, iv = 24_500, 24_500, 7 / 365, 0.15
    assert greeks.bs_gamma(spot, strike, years, iv, R) > 0
    assert greeks.bs_vega(spot, strike, years, iv, R) > 0
    assert greeks.bs_theta(spot, strike, years, iv, "call", R) < 0
    assert greeks.bs_theta(spot, strike, years, iv, "put", R) < 0


def test_implied_vol_roundtrip():
    spot, strike, years = 24_500, 25_000, 0.08
    true_iv = 0.17
    price = greeks.bs_price(spot, strike, years, true_iv, "call", R)
    solved = greeks.implied_vol(price, spot, strike, years, "call", R)
    assert solved is not None
    assert abs(solved - true_iv) < 1e-6


def test_degenerate_inputs_collapse_to_intrinsic():
    assert greeks.bs_price(100, 90, 0, 0.2, "call") == 10
    assert greeks.bs_price(100, 110, 0.01, 0.0, "put") == 10
    assert greeks.bs_delta(101, 100, 0, 0.2, "call") == 1.0
    assert greeks.implied_vol(1.0, 100, 50, 0.0, "call") is None


# ---------------------------------------------------------------- payoff


def _chain(spot, step=100, dte=7):
    """Synthetic but realistic chain: Black-Scholes prices with a fixed IV."""
    strikes = [spot - 10 * step + i * step for i in range(21)]
    premiums, ivs = {}, {}
    years = dte / 365.0
    for k in strikes:
        call = greeks.bs_price(spot, k, years, 0.14, "call", R)
        put = greeks.bs_price(spot, k, years, 0.14, "put", R)
        premiums[k] = (round(call, 2), round(put, 2))
        ivs[k] = (13.5, 14.2)
    return strikes, premiums, ivs


SPOT = 24_800


def SPOT_atm():
    return min(_chain(SPOT)[0], key=lambda k: abs(k - SPOT))


def _resolve(legs, dte=7):
    strikes, premiums, ivs = _chain(SPOT, dte=dte)
    return [
        resolve_leg(leg, SPOT, strikes, dte, R, None, premiums, ivs) for leg in legs
    ]


def test_iron_fly_metrics_are_exact():
    legs = _resolve(
        [_leg("sell", "CE"), _leg("sell", "PE"), _leg("buy", "CE", 300), _leg("buy", "PE", -300)]
    )
    curve = payoff_curve(legs, lot_size=25, spot=SPOT)
    m = payoff_metrics(curve, legs)
    # net credit per unit * 25 must equal max profit exactly
    credit_per_unit = sum(
        (leg.premium if leg.action == "sell" else -leg.premium) for leg in legs
    )
    assert m["max_profit"] == pytest.approx(credit_per_unit * 25, abs=1e-6)
    be_lo, be_hi = m["breakevens"]
    atm = SPOT_atm()
    assert be_lo == pytest.approx(atm - credit_per_unit, abs=1e-6)
    assert be_hi == pytest.approx(atm + credit_per_unit, abs=1e-6)
    assert m["risk_reward"] is not None


def test_short_straddle_naked_sides_uncapped_loss():
    legs = _resolve([_leg("sell", "CE"), _leg("sell", "PE")])
    profit_uncapped, loss_uncapped = has_unlimited_side(legs)
    # Short straddle: profit capped at the credit; BOTH naked sides carry
    # uncapped loss (short call above, short put below).
    assert profit_uncapped is False
    assert loss_uncapped is True
    curve = payoff_curve(legs, 25, SPOT)
    m = payoff_metrics(curve, legs)
    credit_per_unit = sum(
        (leg.premium if leg.action == "sell" else -leg.premium) for leg in legs
    )
    assert m["max_profit"] == pytest.approx(credit_per_unit * 25, abs=1e-6)
    assert m["max_loss"] is None


def test_long_call_breakeven_is_strike_plus_premium():
    legs = _resolve([_leg("buy", "CE")])
    leg = legs[0]
    curve = payoff_curve(legs, 1, SPOT)
    m = payoff_metrics(curve, legs)
    assert len(m["breakevens"]) == 1
    assert m["breakevens"][0] == pytest.approx(leg.strike + leg.premium, abs=0.01)
    assert m["max_loss"] == pytest.approx(-leg.premium, abs=1e-6)


def test_strike_offset_snaps_to_grid():
    legs = _resolve([_leg("buy", "CE", 130)])
    # chain step is 100 -> nearest listed to ATM+130 is ATM+100
    assert legs[0].strike == SPOT_atm() + 100


def test_far_offset_raises_optionslab_error():
    with pytest.raises(OptionsLabError):
        _resolve([_leg("buy", "CE", 99_000)])


def test_net_greeks_and_premium_signs():
    legs = _resolve([_leg("sell", "CE", lots=2), _leg("buy", "CE", 200)])
    greeks_sum = net_greeks(legs, 25)
    prem = net_premium(legs, 25)
    expected = (-legs[0].premium * 2 + legs[1].premium) * 25
    assert prem == pytest.approx(expected, abs=0.01)
    # short-dated short strangle-ish book should collect positive theta
    assert greeks_sum["theta_per_day"] != 0


# ---------------------------------------------------------------- monte carlo


def test_monte_carlo_deterministic():
    legs = _resolve([_leg("sell", "CE"), _leg("sell", "PE")])
    a = monte_carlo(legs, SPOT, 7, 7, 2_000, R, 25, seed=7)
    b = monte_carlo(legs, SPOT, 7, 7, 2_000, R, 25, seed=7)
    c = monte_carlo(legs, SPOT, 7, 7, 2_000, R, 25, seed=8)
    assert a["stats"] == b["stats"]
    assert a["stats"]["mean"] != c["stats"]["mean"]


def test_short_straddle_prob_profit_plausible():
    legs = _resolve([_leg("sell", "CE"), _leg("sell", "PE")])
    res = monte_carlo(legs, SPOT, 7, 7, 10_000, R, 25)
    pp = res["stats"]["prob_profit"]
    assert 0.15 < pp < 0.85
    assert res["paths"] == 10_000
    assert len(res["bins"]) == 40
    assert any(b["count"] > 0 for b in res["bins"])


def test_mc_horizon_clamped_to_dte():
    legs = _resolve([_leg("buy", "CE")])
    res = monte_carlo(legs, SPOT, 3, 30, 1_000, R, 25)
    assert res["horizon_days"] == 3


# ---------------------------------------------------------------- API


@pytest.mark.asyncio
async def test_payoff_endpoint(client):
    resp = await client.post(
        "/api/v1/options/payoff",
        json={
            "underlying": "NIFTY",
            "dte_days": 7,
            "lot_size": 25,
            "legs": [
                {"action": "sell", "option_type": "CE", "strike_offset": 0},
                {"action": "sell", "option_type": "PE", "strike_offset": 0},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_demo"] is True
    assert body["atm_strike"] > 0
    assert len(body["curve"]) >= 161
    assert body["metrics"]["net_premium"] < 0  # net credit for shorts
    assert set(body["net_greeks"]) == {"delta", "gamma", "theta_per_day", "vega"}


@pytest.mark.asyncio
async def test_payoff_rejects_bad_leg(client):
    resp = await client.post(
        "/api/v1/options/payoff",
        json={"legs": [{"action": "hodl", "option_type": "CE"}]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_payoff_rejects_unlistable_strike(client):
    resp = await client.post(
        "/api/v1/options/payoff",
        json={"legs": [{"action": "buy", "option_type": "CE", "strike_offset": 50_000}]},
    )
    assert resp.status_code == 400
    assert "no listed strike" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_monte_carlo_endpoint(client):
    resp = await client.post(
        "/api/v1/options/monte-carlo",
        json={
            "underlying": "NIFTY",
            "dte_days": 7,
            "lot_size": 75,
            "paths": 2_000,
            "legs": [{"action": "buy", "option_type": "CE"}, {"action": "buy", "option_type": "PE"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["paths"] == 2_000
    assert 0 <= body["stats"]["prob_profit"] <= 1
    assert len(body["bins"]) == 40
