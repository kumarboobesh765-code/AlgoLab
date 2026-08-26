"""F&O margin estimator (SPAN + Exposure approximation).

Real SPAN is a portfolio scenario calculation run by the clearing corp.
This module implements the practical rule-of-thumb model Indian brokers
publish, with hedge netting for multi-leg structures:

- Long options: margin = premium paid
- Short options: SPAN ≈ premium + span_pct × underlying notional (+ cushion),
  exposure = expo_pct × notional (index ~3%+1%, stocks roughly double)
- Futures: span_pct + expo_pct of notional
- Hedge relief: each short option paired with a same-type long option gets a
  discount equal to the long leg's protection value (capped at 90% of the
  short block) — the classic vertical-spread credit

Outputs are estimates; the broker's real margin file governs.
"""

from dataclasses import dataclass, field


@dataclass
class MarginLeg:
    action: str            # buy | sell
    option_type: str       # CE | PE | FUT
    strike: float | None = None
    lots: int = 1
    premium: float = 0.0   # per-unit premium (0 for futures)


@dataclass
class LegMargin:
    label: str
    span: float
    exposure: float
    premium_paid: float
    total: float

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "span": round(self.span, 2),
            "exposure": round(self.exposure, 2),
            "premium_paid": round(self.premium_paid, 2),
            "total": round(self.total, 2),
        }


@dataclass
class MarginEstimate:
    lot_size: int
    spot_used: float
    legs: list[LegMargin] = field(default_factory=list)
    hedge_discount: float = 0.0
    total_margin: float = 0.0
    premium_outlay: float = 0.0
    defined_risk: bool = False
    max_loss_theoretical: float | None = None

    def as_dict(self) -> dict:
        return {
            "lot_size": self.lot_size,
            "spot_used": self.spot_used,
            "legs": [lm.as_dict() for lm in self.legs],
            "hedge_discount": round(self.hedge_discount, 2),
            "total_margin": round(self.total_margin, 2),
            "premium_outlay": round(self.premium_outlay, 2),
            "defined_risk": self.defined_risk,
            "max_loss_theoretical": (
                round(self.max_loss_theoretical, 2)
                if self.max_loss_theoretical is not None else None
            ),
        }


INDEX_SPAN_PCT = 0.032       # ~3.2% near-ATM index
INDEX_EXPO_PCT = 0.010       # ~1% exposure add-on
SHORT_PREMIUM_CUSHION = 0.20 # +20% of collected premium

_INDEX_SET = {
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
    "SENSEX", "BANKEX", "SENSEX50",
}


def estimate_margin(
    underlying: str,
    spot: float,
    legs: list[MarginLeg],
    lot_size: int,
    *,
    span_pct: float | None = None,
    expo_pct: float | None = None,
) -> MarginEstimate:
    """Estimate the total margin block for an F&O position."""
    is_idx = underlying.upper() in _INDEX_SET
    sp = span_pct if span_pct is not None else INDEX_SPAN_PCT if is_idx else INDEX_SPAN_PCT * 2
    ep = expo_pct if expo_pct is not None else INDEX_EXPO_PCT if is_idx else INDEX_EXPO_PCT * 2

    shorts_by_type: dict[str, int] = {}
    longs_by_type: dict[str, int] = {}
    for lg in legs:
        if lg.option_type == "FUT":
            continue
        bucket = shorts_by_type if lg.action == "sell" else longs_by_type
        bucket[lg.option_type] = bucket.get(lg.option_type, 0) + 1

    out: list[LegMargin] = []
    available_long_pairs: dict[str, list[MarginLeg]] = {
        t: [x for x in legs if x.action == "buy" and x.option_type == t]
        for t in ("CE", "PE")
    }
    hedge_discount = 0.0
    total = 0.0
    premium_outlay = 0.0
    any_short_unhedged = False

    for leg in legs:
        qty = leg.lots * lot_size
        label = f"{leg.action.upper()} {leg.option_type}"
        if leg.option_type != "FUT" and leg.strike:
            label += f" {leg.strike:g}"

        if leg.option_type == "FUT":
            notional = spot * qty
            span = notional * sp
            expo = notional * ep
            lm = LegMargin(label=label, span=span, exposure=expo, premium_paid=0.0, total=span + expo)
            out.append(lm)
            total += lm.total
            continue

        if leg.action == "buy":
            prem = leg.premium * qty
            out.append(LegMargin(label=label, span=0.0, exposure=0.0, premium_paid=prem, total=prem))
            total += prem
            premium_outlay += prem
            continue

        # Short option
        notional = (leg.strike or spot) * qty
        collected = leg.premium * qty
        span = collected + notional * sp + SHORT_PREMIUM_CUSHION * collected
        expo = notional * ep

        pool = available_long_pairs.get(leg.option_type, [])
        partner = pool.pop() if pool else None  # consume one pair per short

        raw_block = span + expo
        discount = 0.0
        if partner is not None:
            protection = partner.premium * (partner.lots * lot_size)
            discount = min(protection, raw_block * 0.9)
            hedge_discount += discount

        lm = LegMargin(label=f"{label} (short)", span=span, exposure=expo,
                       premium_paid=0.0, total=max(raw_block - discount, 0))
        out.append(lm)
        total += lm.total
        if partner is None:
            any_short_unhedged = True

    defined_risk = not any_short_unhedged and all(x.option_type != "FUT" for x in legs)

    return MarginEstimate(
        lot_size=lot_size,
        spot_used=spot,
        legs=out,
        hedge_discount=hedge_discount,
        total_margin=total,
        premium_outlay=premium_outlay,
        defined_risk=defined_risk,
        max_loss_theoretical=premium_outlay if defined_risk else None,
    )
