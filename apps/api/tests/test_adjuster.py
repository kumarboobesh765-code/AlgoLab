"""Tests for the auto-adjustment engine."""

from app.execution.adjuster import AdjustPolicy, LegState, check_adjustments


def _short_iron_condor(spot: float = 24000.0):
    return [
        LegState("sell", "CE", strike=24100, lots=1, entry_price=120, current_price=100),
        LegState("sell", "PE", strike=23900, lots=1, entry_price=130, current_price=110),
    ]


def test_hold_within_policy():
    actions = check_adjustments(
        spot=24000, entry_spot=24000, dte_days=5,
        legs=_short_iron_condor(), lot_size=65,
    )
    assert actions[0].kind == "hold"


def test_max_loss_triggers_square_off():
    legs = [
        LegState("sell", "CE", strike=24100, lots=1, entry_price=120, current_price=620),
        LegState("sell", "PE", strike=23900, lots=1, entry_price=130, current_price=60),
    ]
    actions = check_adjustments(
        spot=24500, entry_spot=24000, dte_days=3, legs=legs, lot_size=65,
    )
    assert actions[0].kind == "square_off"
    # Square-off short-circuits: no other recommendations
    assert len(actions) == 1


def test_spot_breach_recommends_roll_up():
    actions = check_adjustments(
        spot=24250, entry_spot=24000, dte_days=4,
        legs=_short_iron_condor(), lot_size=65,
    )
    rolls = [a for a in actions if a.kind == "roll_strike"]
    assert any(a.suggested_strike_shift > 0 for a in rolls)


def test_profit_booking():
    legs = [
        LegState("sell", "CE", strike=24100, lots=1, entry_price=200, current_price=40),
        LegState("sell", "PE", strike=23900, lots=1, entry_price=210, current_price=50),
    ]
    actions = check_adjustments(
        spot=24000, entry_spot=24000, dte_days=4, legs=legs, lot_size=65,
    )
    assert any(a.kind == "book_profit" for a in actions)


def test_low_dte_rolls_expiry():
    actions = check_adjustments(
        spot=24000, entry_spot=24000, dte_days=0,
        legs=_short_iron_condor(), lot_size=65,
        policy=AdjustPolicy(min_dte_to_hold=1),
    )
    assert any(
        a.kind == "roll_strike" and "DTE" in a.reason
        for a in actions
    )
