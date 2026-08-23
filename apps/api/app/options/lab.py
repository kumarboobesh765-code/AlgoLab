"""Options Lab: multi-leg payoff analysis and Monte Carlo simulation.

Legs are expressed relative to ATM (strike offsets in index points) the way
retail F&O platforms present them. Premiums/IVs resolve from the active
provider's option chain, so demo data works out of the box.
"""

import math
import random
from dataclasses import dataclass

from app.options import greeks


class OptionsLabError(ValueError):
    """User-facing validation error (mapped to HTTP 400)."""


@dataclass(frozen=True)
class LegInput:
    action: str  # buy | sell
    option_type: str  # CE | PE
    strike_offset: int  # points from ATM; snapped to nearest chain strike
    lots: int


@dataclass(frozen=True)
class ResolvedLeg(LegInput):
    strike: int
    premium: float  # per unit, entry price paid(+)/received(-) convention applied later
    iv: float  # decimal, e.g. 0.14
    delta: float
    gamma: float
    theta_per_day: float
    vega: float


def _bs_kind(option_type: str) -> str:
    return "call" if option_type == "CE" else "put"


def resolve_leg(
    leg: LegInput,
    spot: float,
    strikes: list[int],
    dte_days: int,
    rate: float,
    iv_override: float | None,
    premiums: dict[int, tuple[float, float]],
    ivs: dict[int, tuple[float, float]],
) -> ResolvedLeg:
    """Snap a leg to the nearest available chain strike and price it."""
    atm = min(strikes, key=lambda k: abs(k - spot))
    target = atm + leg.strike_offset
    strike = min(strikes, key=lambda k: abs(k - target))
    if abs(strike - target) > max(atm * 0.05, 5):
        raise OptionsLabError(
            f"{leg.action.upper()} {leg.option_type} {target:g}: no listed strike near "
            f"ATM{leg.strike_offset:+d} within the provider's chain"
        )
    call_ltp, put_ltp = premiums[strike]
    premium = call_ltp if leg.option_type == "CE" else put_ltp
    iv_pct = ivs[strike][0 if leg.option_type == "CE" else 1]
    if iv_override is not None:
        iv = iv_override / 100.0
    else:
        iv = iv_pct / 100.0 if iv_pct > 0 else 0.15
        if iv <= 0:
            iv = 0.15
    years = dte_days / 365.0
    kind = _bs_kind(leg.option_type)
    return ResolvedLeg(
        **vars(leg),
        strike=strike,
        premium=premium,
        iv=iv,
        delta=greeks.bs_delta(spot, strike, years, iv, kind, rate),
        gamma=greeks.bs_gamma(spot, strike, years, iv, rate),
        theta_per_day=greeks.bs_theta(spot, strike, years, iv, kind, rate),
        vega=greeks.bs_vega(spot, strike, years, iv, rate),
    )


def intrinsic(option_type: str, strike: float, spot_t: float) -> float:
    if option_type == "CE":
        return max(spot_t - strike, 0.0)
    return max(strike - spot_t, 0.0)


def payoff_curve(
    legs: list[ResolvedLeg], lot_size: int, spot: float, points: int = 161
) -> list[tuple[float, float]]:
    """Expiry P&L in currency units across +/-15% of spot.

    Leg strikes are injected into the grid so every payoff kink is evaluated
    exactly (max profit/loss and breakevens stay analytic-grade).
    """
    span = max(spot * 0.15, 1.0)
    lo, hi = spot - span, spot + span
    step = (hi - lo) / (points - 1)
    xs = {lo + i * step for i in range(points)}
    xs.update(min(max(leg.strike, lo), hi) for leg in legs)

    def pnl_at(spot_t: float) -> float:
        pnl = 0.0
        for leg in legs:
            sign = 1.0 if leg.action == "buy" else -1.0
            per_unit = intrinsic(leg.option_type, leg.strike, spot_t) - leg.premium
            pnl += sign * per_unit * leg.lots * lot_size
        return pnl

    return [(x, pnl_at(x)) for x in sorted(xs)]


def has_unlimited_side(legs: list[ResolvedLeg]) -> tuple[bool, bool]:
    """(uncapped_profit, uncapped_loss) structurally.

    Profit is uncapped only with a long call and no short call (any short call
    caps upside profit). Loss is uncapped with any naked side: a short put
    loses unboundedly below (spot floored at zero still means strike-sized
    loss) or a short call loses unboundedly above. Long options bound risk to
    the premium paid.
    """
    bought_calls = any(leg.option_type == "CE" and leg.action == "buy" for leg in legs)
    sold_calls = any(leg.option_type == "CE" and leg.action == "sell" for leg in legs)
    bought_puts = any(leg.option_type == "PE" and leg.action == "buy" for leg in legs)
    sold_puts = any(leg.option_type == "PE" and leg.action == "sell" for leg in legs)
    profit_uncapped = bought_calls and not sold_calls
    loss_uncapped = (sold_puts and not bought_puts) or (sold_calls and not bought_calls)
    return profit_uncapped, loss_uncapped


def payoff_metrics(curve: list[tuple[float, float]], legs: list[ResolvedLeg]):
    """Max profit / loss / breakevens / risk-reward from the expiry curve."""
    unlimited_up, unlimited_down = has_unlimited_side(legs)
    values = [pnl for _, pnl in curve]
    max_profit = None if unlimited_up else max(values)
    max_loss = None if unlimited_down else min(values)

    breakevens: list[float] = []
    for (p0, v0), (p1, v1) in zip(curve, curve[1:]):
        if (v0 < 0 <= v1) or (v1 < 0 <= v0):
            if v1 != v0:
                breakevens.append(round(p0 + (p1 - p0) * (-v0) / (v1 - v0), 2))

    risk_reward = None
    if max_profit is not None and max_loss is not None and max_loss < 0:
        risk_reward = round(max_profit / abs(max_loss), 2)

    return {
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakevens": sorted(breakevens),
        "risk_reward": risk_reward,
    }


def net_greeks(legs: list[ResolvedLeg], lot_size: int) -> dict[str, float]:
    totals = {"delta": 0.0, "gamma": 0.0, "theta_per_day": 0.0, "vega": 0.0}
    for leg in legs:
        sign = 1.0 if leg.action == "buy" else -1.0
        mult = sign * leg.lots * lot_size
        totals["delta"] += leg.delta * mult
        totals["gamma"] += leg.gamma * mult
        totals["theta_per_day"] += leg.theta_per_day * mult
        totals["vega"] += leg.vega * mult
    for k in totals:
        totals[k] = round(totals[k], 4)
    return totals


def net_premium(legs: list[ResolvedLeg], lot_size: int) -> float:
    total = 0.0
    for leg in legs:
        sign = 1.0 if leg.action == "buy" else -1.0
        total += sign * leg.premium * leg.lots * lot_size
    return round(total, 2)


def monte_carlo(
    legs: list[ResolvedLeg],
    spot: float,
    dte_days: int,
    horizon_days: int,
    paths: int,
    rate: float,
    lot_size: int,
    vol_override: float | None = None,
    seed: int = 42,
) -> dict:
    """GBM terminal distribution -> portfolio P&L stats at `horizon_days`.

    Uses antithetic variates; options remaining to expiry are repriced with
    Black-Scholes so pre-expiry horizons capture time value.
    """
    horizon_days = max(1, min(horizon_days, max(dte_days, 1)))
    remaining_years = max(dte_days - horizon_days, 0) / 365.0
    years_h = horizon_days / 365.0
    if vol_override is not None:
        vol = vol_override / 100.0
    else:
        vols = [leg.iv for leg in legs]
        vol = sum(vols) / len(vols) if vols else 0.15
    drift = (rate - 0.5 * vol * vol) * years_h
    diffusion = vol * math.sqrt(years_h)

    rng = random.Random(seed)
    half = max(paths // 2, 1)
    pnls: list[float] = []
    for _ in range(half):
        z = rng.gauss(0.0, 1.0)
        for zz in (z, -z):
            spot_h = spot * math.exp(drift + diffusion * zz)
            value = 0.0
            for leg in legs:
                sign = 1.0 if leg.action == "buy" else -1.0
                kind = _bs_kind(leg.option_type)
                px = greeks.bs_price(spot_h, leg.strike, remaining_years, leg.iv, kind, rate)
                value += sign * (px - leg.premium) * leg.lots * lot_size
            pnls.append(value)

    pnls.sort()
    n = len(pnls)

    def pct(p: float) -> float:
        idx = min(int(p * (n - 1)), n - 1)
        return pnls[idx]

    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / n
    prob_profit = sum(1 for x in pnls if x > 0) / n

    # Histogram over p1..p99 so outliers don't crush bin resolution.
    lo, hi = pct(0.01), pct(0.99)
    bins_n = 40
    width = (hi - lo) / bins_n if hi > lo else 1.0
    counts = [0] * bins_n
    for x in pnls:
        b = int((x - lo) / width)
        if 0 <= b < bins_n:
            counts[b] += 1

    return {
        "stats": {
            "mean": round(mean, 2),
            "std": round(math.sqrt(var), 2),
            "median": round(pct(0.50), 2),
            "p5": round(pct(0.05), 2),
            "p95": round(pct(0.95), 2),
            "worst": round(pnls[0], 2),
            "best": round(pnls[-1], 2),
            "prob_profit": round(prob_profit, 4),
            "var_95": round(pct(0.05), 2),
        },
        "bins": [
            {"lo": round(lo + i * width, 2), "hi": round(lo + (i + 1) * width, 2), "count": c}
            for i, c in enumerate(counts)
        ],
        "paths": n,
        "vol_used_pct": round(vol * 100, 2),
        "horizon_days": horizon_days,
    }
