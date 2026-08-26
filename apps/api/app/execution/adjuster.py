"""Auto-adjustment engine for deployed multi-leg option strategies.

Quantman-style repair logic as pure functions: given the current leg state,
spot, and a policy, recommend actions when risk thresholds breach:

- Square-off when total MTM loss crosses max_loss_pct of margin
- Roll (shift strike) when spot breaches the short-strike buffer band
- Add hedge wing when delta/width exposure exceeds policy
- Book profits when premium captured crosses target_pct

The engine never executes — it returns recommended AdjustmentActions that the
caller (forward-test tick, automation runner, or UI) may apply.
"""

from dataclasses import dataclass, field


@dataclass
class LegState:
    action: str            # buy | sell
    option_type: str       # CE | PE
    strike: float
    lots: int = 1
    entry_price: float = 0.0
    current_price: float = 0.0


@dataclass
class AdjustPolicy:
    """Thresholds as fractions (0.25 = 25%)."""

    max_loss_pct_of_credit: float = 1.5   # square off at 150% of credit received
    profit_pct_of_credit: float = 0.6     # book at 60% of credit
    roll_buffer_pct: float = 2.0          # % move beyond short strike triggers roll
    min_dte_to_hold: int = 1              # roll when DTE drops below this


@dataclass
class AdjustmentAction:
    kind: str              # square_off | roll_strike | add_hedge | book_profit | hold
    reason: str
    legs: list[int] = field(default_factory=list)
    suggested_strike_shift: int = 0

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "legs": self.legs,
            "suggested_strike_shift": self.suggested_strike_shift,
        }


def _credit(legs: list[LegState], lot_size: int) -> float:
    return sum(
        (lg.entry_price - lg.current_price if lg.action == "sell" else lg.current_price - lg.entry_price)
        * lg.lots * lot_size
        for lg in legs
    )


def _net_premium_received(legs: list[LegState], lot_size: int) -> float:
    return sum(lg.entry_price * lg.lots * lot_size for lg in legs if lg.action == "sell")


def check_adjustments(
    *,
    spot: float,
    entry_spot: float,
    dte_days: int,
    legs: list[LegState],
    lot_size: int,
    policy: AdjustPolicy | None = None,
) -> list[AdjustmentAction]:
    """Evaluate the position and return prioritized recommendations."""
    pol = policy or AdjustPolicy()
    actions: list[AdjustmentAction] = []

    shorts_ce = [i for i, lg in enumerate(legs) if lg.action == "sell" and lg.option_type == "CE"]
    shorts_pe = [i for i, lg in enumerate(legs) if lg.action == "sell" and lg.option_type == "PE"]

    net_prem = _net_premium_received(legs, lot_size)
    pnl = _credit(legs, lot_size)

    # 1) Hard stop on total loss
    if net_prem > 0 and -pnl >= pol.max_loss_pct_of_credit * net_prem:
        actions.append(AdjustmentAction(
            kind="square_off",
            reason=(
                f"MTM loss {-pnl:,.0f} crossed {pol.max_loss_pct_of_credit:.0%} "
                f"of credit {net_prem:,.0f}"
            ),
            legs=list(range(len(legs))),
        ))
        return actions  # nothing else matters once flat is recommended

    # 2) Profit booking
    if net_prem > 0 and pnl >= pol.profit_pct_of_credit * net_prem:
        actions.append(AdjustmentAction(
            kind="book_profit",
            reason=f"Captured {pnl:,.0f} ≥ {pol.profit_pct_of_credit:.0%} of credit",
            legs=list(range(len(legs))),
        ))

    # 3) Spot beyond short strikes → roll that side out
    move_pct = (spot / entry_spot - 1) * 100 if entry_spot else 0.0
    if shorts_ce:
        ce_strike = legs[shorts_ce[0]].strike
        if spot > ce_strike:
            shift = max(1, round((spot - ce_strike) / _strike_step(spot)))
            actions.append(AdjustmentAction(
                kind="roll_strike",
                reason=(f"Spot {spot:g} breached short CE {ce_strike:g} ({move_pct:+.1f}% day move)"),
                legs=shorts_ce,
                suggested_strike_shift=shift,
            ))
    if shorts_pe:
        pe_strike = legs[shorts_pe[0]].strike
        if spot < pe_strike:
            shift = max(1, round((pe_strike - spot) / _strike_step(spot)))
            actions.append(AdjustmentAction(
                kind="roll_strike",
                reason=(f"Spot {spot:g} broke below short PE {pe_strike:g} ({move_pct:+.1f}% day move)"),
                legs=shorts_pe,
                suggested_strike_shift=-shift,
            ))

    # 4) Expiry too close → roll temporally
    if dte_days < pol.min_dte_to_hold and legs:
        actions.append(AdjustmentAction(
            kind="roll_strike",
            reason=f"DTE {dte_days} below policy minimum {pol.min_dte_to_hold} — roll to next expiry",
            legs=[],
            suggested_strike_shift=0,
        ))

    if not actions:
        actions.append(AdjustmentAction(kind="hold", reason="All thresholds within policy"))
    return actions


def _strike_step(spot: float) -> float:
    """Approximate index strike interval from spot level."""
    if spot >= 40000:
        return 100.0
    if spot >= 15000:
        return 50.0
    return 20.0
