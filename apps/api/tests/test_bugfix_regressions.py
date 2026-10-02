"""Regression tests for the four defects found in the October 2026 audit.

B1  NEXT_WEEKLY / NEXT_MONTHLY silently resolved to the *current weekly* expiry
B2  sl_mode="delta" was accepted by schema + UI but ignored by the engine
B3  reentry_time_restriction was declared but never read
B4  auto_roll was threaded through the API into a config the engine never saw
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.backtest.options_engine import (
    OptionsBacktestError,
    _bs_delta,
    _compute_sl_target,
    _delta_sl_hit,
    run_options_backtest,
)
from app.quant.options.expiry import parse_expiry_formula
from app.quant.schema import OptionLeg, StrategyDefinition

REF = date(2026, 9, 2)  # a Wednesday


# ---------------------------------------------------------------------------
# B1 - expiry token aliases
# ---------------------------------------------------------------------------

class TestB1ExpiryAliases:
    def test_next_weekly_is_not_the_current_week(self):
        """The core bug: NEXT_WEEKLY used to fall through to the weekly default."""
        current = parse_expiry_formula("WEEKLY", REF)
        nxt = parse_expiry_formula("NEXT_WEEKLY", REF)
        assert nxt != current, "NEXT_WEEKLY must not resolve to the current weekly expiry"
        assert nxt > current
        assert (nxt - current).days == 7

    def test_next_monthly_is_not_the_current_week(self):
        """NEXT_MONTHLY used to resolve to the current *weekly* expiry."""
        current = parse_expiry_formula("WEEKLY", REF)
        nxt = parse_expiry_formula("NEXT_MONTHLY", REF)
        assert nxt != current
        assert nxt > current
        # must land in the following month
        assert (nxt.year, nxt.month) != (REF.year, REF.month)
        assert nxt.month in (REF.month + 1, 1)

    def test_ly_suffixed_aliases_match_canonical_tokens(self):
        for alias, canonical in (
            ("NEXT_WEEKLY", "NEXT_WEEK"),
            ("NEXT_MONTHLY", "NEXT_MONTH"),
            ("CURRENT_WEEK", "THIS_WEEK"),
            ("CURRENT_MONTH", "THIS_MONTH"),
        ):
            assert parse_expiry_formula(alias, REF) == parse_expiry_formula(canonical, REF), alias

    def test_lowercase_input_from_frontend_is_accepted(self):
        """The web builders emit l.expiryType.toUpperCase(), but be tolerant."""
        assert parse_expiry_formula("next_weekly", REF) == parse_expiry_formula("NEXT_WEEK", REF)
        assert parse_expiry_formula("next_monthly", REF) == parse_expiry_formula("NEXT_MONTH", REF)

    def test_explicit_iso_date_still_wins(self):
        assert parse_expiry_formula("2026-12-26", REF) == date(2026, 12, 26)

    def test_unknown_token_warns_and_falls_back(self, caplog):
        """Must not raise (would 400 on legacy saved strategies) but must log."""
        with caplog.at_level("WARNING"):
            got = parse_expiry_formula("GARBAGE_TOKEN", REF)
        assert got == parse_expiry_formula("WEEKLY", REF)
        assert any("GARBAGE_TOKEN" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# B2 - delta stop loss
# ---------------------------------------------------------------------------

def _leg(**kw) -> OptionLeg:
    base = dict(action="buy", option_type="CE", strike=20000.0, lots=1)
    base.update(kw)
    return OptionLeg(**base)


class TestB2DeltaStopLoss:
    def test_delta_sl_produces_no_static_price(self):
        """Delta is a dynamic trigger, so no static level is correct."""
        leg = _leg(sl_mode="delta", sl_value=30.0)
        sl, _ = _compute_sl_target(leg, entry_price=100.0, entry_underlying=20000.0, step=50.0)
        assert sl is None

    def test_delta_sl_triggers_for_long_leg_when_delta_decays(self):
        leg = _leg(action="buy", option_type="CE", sl_mode="delta", sl_value=30.0)
        # Deep ITM call -> |delta| near 1, above threshold -> no exit
        assert _delta_sl_hit(leg, "buy", 26000.0, 20000.0, 0.05, 0.2) is False
        # Far OTM call -> |delta| near 0, at/below threshold -> exit
        assert _delta_sl_hit(leg, "buy", 15000.0, 20000.0, 0.02, 0.2) is True

    def test_delta_sl_triggers_for_short_leg_when_delta_grows(self):
        leg = _leg(action="sell", option_type="CE", sl_mode="delta", sl_value=30.0)
        # sold call, OTM -> small delta -> no exit
        assert _delta_sl_hit(leg, "sell", 15000.0, 20000.0, 0.02, 0.2) is False
        # sold call deep ITM -> |delta| near 1 -> exit
        assert _delta_sl_hit(leg, "sell", 26000.0, 20000.0, 0.05, 0.2) is True

    def test_delta_sl_inert_for_other_modes(self):
        leg = _leg(sl_mode="pts", sl_value=10.0)
        assert _delta_sl_hit(leg, "buy", 15000.0, 20000.0, 0.02, 0.2) is False

    def test_underlying_sl_uses_gamma_not_flat_half(self):
        """Regression: the old code used a flat u_move * 0.5 pass-through."""
        leg = _leg(sl_mode="underlying_pts", sl_value=100.0)
        sl, _ = _compute_sl_target(
            leg, entry_price=100.0, entry_underlying=20000.0, step=50.0, sigma=0.2, T=0.05
        )
        # 100 underlying points should move the premium by far less than 50
        assert sl is not None
        assert sl > 50.0, "gamma-based conversion should shrink the premium move vs 0.5*x"
        assert sl < 100.0

    def test_bs_delta_is_bounded(self):
        for s in (15000.0, 20000.0, 25000.0):
            d = _bs_delta(s, 20000.0, 0.05, 0.2, True)
            assert -1.0 <= d <= 1.0


# ---------------------------------------------------------------------------
# B3 - reentry_time_restriction
# ---------------------------------------------------------------------------

def _zigzag_bars(n: int = 40) -> list:
    """Bars that move enough to repeatedly trigger entry, SL and re-entry."""
    from app.marketdata.base import Candle

    start = datetime(2026, 9, 1, 9, 15, tzinfo=UTC)
    out = []
    price = 20000.0
    for i in range(n):
        price += 120.0 if i % 2 == 0 else -115.0  # guaranteed SL + re-entry cycles
        out.append(
            Candle(
                timestamp=start + timedelta(minutes=5 * i),
                instrument_id="NIFTY",
                open=price - 5,
                high=price + 10,
                low=price - 10,
                close=price,
                volume=1000.0,
            )
        )
    return out


def _reentry_defn(**extra) -> StrategyDefinition:
    """Leg definition wired to re-enter aggressively after an SL."""
    legs = [
        OptionLeg(
            action="buy",
            option_type="CE",
            strike=20000,
            lots=1,
            sl_mode="pts",
            sl_value=25.0,
            reentry_on_sl="asap",
            max_reentries=5,
        )
    ]
    return StrategyDefinition(
        version=1,
        timeframe="5m",
        instrument={"symbol": "NIFTY", "exchange": "NSE", "segment": "options"},
        entry={
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "price", "price": "close"}, "op": "GT",
                 "right": {"kind": "constant", "value": 0}}
            ],
        },
        legs=legs,
        position={
            "direction": "both",
            "quantity_type": "fixed",
            "quantity": 1,
            "capital_pct": None,
        },
        # Bars span 09:15-12:30, so a 14:00 cutoff is never reached.
        time_control={"no_reentry_after": "14:00"},
        **extra,
    )


class TestB3ReentryTimeRestriction:
    @pytest.mark.parametrize("mode", ["none", "before_time"])
    def test_before_modes_permit_reentries_before_cutoff(self, mode):
        result = run_options_backtest(_reentry_defn(reentry_time_restriction=mode), _zigzag_bars())
        # cutoff is 14:00 and all bars are before it -> re-entries are open
        assert len(result.trades) > 1, "re-entry should be permitted before no_reentry_after"

    def test_after_time_blocks_early_reentries(self):
        """With after_time the gate inverts: bars are all before 14:00 -> no re-entries."""
        result = run_options_backtest(_reentry_defn(reentry_time_restriction="after_time"), _zigzag_bars())
        assert len(result.trades) <= 1, "re-entry must be blocked before the cutoff in after_time mode"

    def test_default_is_backward_compatible(self):
        assert _reentry_defn().reentry_time_restriction == "none"

    def test_field_is_accepted_by_schema(self):
        for mode in ("none", "after_time", "before_time"):
            assert _reentry_defn(reentry_time_restriction=mode).reentry_time_restriction == mode


# ---------------------------------------------------------------------------
# B4 - auto_roll removed rather than left dangling
# ---------------------------------------------------------------------------

class TestB4AutoRollRemoved:
    def test_options_config_has_no_auto_roll(self):
        from app.backtest.options_engine import OptionsConfig

        assert not hasattr(OptionsConfig(), "auto_roll")

    def test_request_schema_ignores_legacy_auto_roll(self):
        """Old clients may still send auto_roll; it must be ignored, not fatal."""
        from app.schemas.options import OptionsBacktestRequest

        req = OptionsBacktestRequest(underlying="NIFTY", legs=[{"a": 1}], auto_roll=True)
        assert not hasattr(req, "auto_roll")


def test_engine_still_requires_two_bars():
    with pytest.raises(OptionsBacktestError):
        run_options_backtest(
            StrategyDefinition(
                version=1,
                timeframe="5m",
                instrument={"symbol": "NIFTY", "exchange": "NSE", "segment": "options"},
                entry={
                    "logic": "ALL",
                    "conditions": [
                        {"left": {"kind": "price", "price": "close"}, "op": "GT",
                         "right": {"kind": "constant", "value": 0}}
                    ],
                },
                legs=[OptionLeg(action="buy", option_type="CE", strike=20000, lots=1)],
            ),
            _zigzag_bars(1),
        )

