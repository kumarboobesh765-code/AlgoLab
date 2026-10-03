"""Payoff/basket engine: P&L must be net of premium.

These are regression tests for a shipped bug. max_profit, max_loss and the
breakevens were all computed from gross expiry value, ignoring net_premium, so
a long straddle paying 600 reported max_loss = 0 and a single break-even at the
strike. Every assertion below is stated in P&L space and checked against
closed-form expectations, not against the engine's own output.
"""

import pytest

from app.options.basket import compute_basket_payoff
from app.schemas.basket import BasketPayoffRequest


def payoff(legs, spot=22000.0, dte=7, vol=16.0):
    req = BasketPayoffRequest.model_validate(
        {"spot": spot, "days_to_expiry": dte, "volatility": vol, "legs": legs}
    )
    return compute_basket_payoff(req)


def leg(action, option_type, strike, premium, quantity=1):
    return {
        "action": action,
        "option_type": option_type,
        "strike": strike,
        "premium": premium,
        "quantity": quantity,
    }


LONG_STRADDLE = [leg("buy", "CE", 22000, 300), leg("buy", "PE", 22000, 300)]


# --- max loss / max profit -------------------------------------------------


def test_long_straddle_max_loss_equals_debit():
    """The defining property: a long straddle's worst case is exactly the debit."""
    r = payoff(LONG_STRADDLE)
    assert r.net_premium == pytest.approx(-600.0)
    assert r.max_loss == pytest.approx(-600.0)


def test_long_straddle_profit_is_uncapped():
    r = payoff(LONG_STRADDLE)
    assert r.max_profit is None, "long call leg makes upside unlimited"


def test_long_call_max_loss_is_premium():
    r = payoff([leg("buy", "CE", 22000, 300)])
    assert r.max_loss == pytest.approx(-300.0)
    assert r.max_profit is None


def test_short_straddle_max_profit_is_credit():
    r = payoff([leg("sell", "CE", 22000, 300), leg("sell", "PE", 22000, 300)])
    assert r.max_profit == pytest.approx(600.0)
    assert r.max_loss is None, "short call leg makes downside unlimited"


def test_vertical_spread_max_profit_and_loss_are_bounded():
    """500-wide spread bought for 200: risk 200, reward 300."""
    r = payoff([leg("buy", "CE", 22000, 300), leg("sell", "CE", 22500, 100)])
    assert r.net_premium == pytest.approx(-200.0)
    assert r.max_loss == pytest.approx(-200.0)
    assert r.max_profit == pytest.approx(300.0)


def test_max_profit_loss_are_consistent_with_the_curve():
    """The reported extremes must actually occur on the returned payoff curve."""
    r = payoff(LONG_STRADDLE)
    pnls = [p.expiry_pnl for p in r.payoff]
    assert r.max_loss == pytest.approx(min(pnls))
    assert r.max_profit is None or r.max_profit == pytest.approx(max(pnls))


def test_scaling_by_quantity_scales_pnl():
    one = payoff([leg("buy", "CE", 22000, 300, quantity=1)])
    three = payoff([leg("buy", "CE", 22000, 300, quantity=3)])
    assert three.max_loss == pytest.approx(one.max_loss * 3)


# --- breakevens ------------------------------------------------------------


def test_long_straddle_breakevens_are_outside_the_strike():
    """ATM straddle paying 600 breaks even ~600 either side of the strike,
    not at the strike where it simply expires worthless."""
    r = payoff(LONG_STRADDLE)
    assert r.breakeven_points == pytest.approx([21400.0, 22600.0], abs=60)


def test_long_call_breakeven_is_strike_plus_premium():
    r = payoff([leg("buy", "CE", 22000, 300)])
    assert len(r.breakeven_points) == 1
    assert r.breakeven_points[0] == pytest.approx(22300, abs=1)


def test_spread_breakeven_is_strike_plus_debit():
    r = payoff([leg("buy", "CE", 22000, 300), leg("sell", "CE", 22500, 100)])
    assert r.breakeven_points[0] == pytest.approx(22200, abs=1)


def test_breakeven_points_are_actual_roots_of_the_pnl_curve():
    """Interpolate the curve at each reported breakeven: P&L must be ~0 there."""
    for legs in (
        LONG_STRADDLE,
        [leg("buy", "CE", 22000, 300)],
        [leg("sell", "CE", 22000, 300), leg("sell", "PE", 22000, 300)],
        [leg("buy", "CE", 22000, 300), leg("sell", "CE", 22500, 100)],
    ):
        r = payoff(legs)
        pts = sorted(r.payoff, key=lambda p: p.underlying)
        for be in r.breakeven_points:
            lo = max((p for p in pts if p.underlying <= be), key=lambda p: p.underlying, default=None)
            hi = min((p for p in pts if p.underlying >= be), key=lambda p: p.underlying, default=None)
            assert lo is not None and hi is not None
            span = hi.underlying - lo.underlying
            t = 0.0 if span == 0 else (be - lo.underlying) / span
            assert lo.expiry_pnl + t * (hi.expiry_pnl - lo.expiry_pnl) == pytest.approx(0.0, abs=1.0)


def test_credit_spread_has_no_breakeven_above_spot():
    r = payoff([leg("sell", "CE", 22000, 300), leg("buy", "CE", 22500, 100)])
    for be in r.breakeven_points:
        assert be < 22500


# --- point-level consistency ----------------------------------------------


def test_expiry_pnl_is_expiry_value_plus_net_premium():
    r = payoff(LONG_STRADDLE)
    for p in r.payoff:
        assert p.expiry_pnl == pytest.approx(p.expiry_value + r.net_premium, abs=0.02)


def test_combined_premium_is_todays_pnl():
    r = payoff(LONG_STRADDLE)
    for p in r.payoff:
        assert p.combined_premium == pytest.approx(p.current_value + r.net_premium, abs=0.02)


def test_combined_premium_is_not_a_duplicate_of_current_value():
    """Regression guard: combined_premium used to be assigned current_value."""
    r = payoff(LONG_STRADDLE)
    assert any(p.combined_premium != p.current_value for p in r.payoff)


def test_atm_expiry_pnl_equals_minus_premium():
    r = payoff(LONG_STRADDLE)
    atm = [p for p in r.payoff if abs(p.underlying - 22000) < 1]
    assert atm, "grid must contain the strike"
    assert atm[0].expiry_value == pytest.approx(0.0, abs=0.01)
    assert atm[0].expiry_pnl == pytest.approx(-600.0, abs=0.02)


def test_expiry_pnl_is_piecewise_linear_for_a_single_long_call():
    """A long call's expiry P&L is 0 below strike, then rises 1:1."""
    r = payoff([leg("buy", "CE", 22000, 300)])
    pts = sorted(r.payoff, key=lambda p: p.underlying)
    below = [p for p in pts if p.underlying < 22000]
    for p in below:
        assert p.expiry_pnl == pytest.approx(-300.0, abs=0.02)
    above = [p for p in pts if p.underlying > 22000]
    assert above[-1].expiry_pnl == pytest.approx(above[-1].underlying - 22000 - 300, abs=0.02)


# --- zero-premium edge case -----------------------------------------------


def test_zero_premium_straddle_breaks_even_at_strike():
    r = payoff([leg("buy", "CE", 22000, 0), leg("buy", "PE", 22000, 0)])
    assert r.net_premium == pytest.approx(0.0)
    assert r.max_loss == pytest.approx(0.0)
    assert r.breakeven_points == pytest.approx([22000.0], abs=1)


def test_grid_is_monotonic_in_underlying():
    r = payoff(LONG_STRADDLE)
    pts = sorted(r.payoff, key=lambda p: p.underlying)
    for a, b in zip(pts, pts[1:], strict=False):
        assert b.underlying > a.underlying
