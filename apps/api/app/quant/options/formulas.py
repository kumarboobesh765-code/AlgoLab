"""Formula-based strike, expiry, and quantity calculations for options.

Supports dynamic position sizing and strike selection based on:
- ATM (at-the-money)
- Delta targets (e.g., 0.20 delta strangles)
- Percentage from spot (e.g., 5% OTM)
- Greeks-neutral sizing (delta, gamma, vega, theta)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ExpiryType(str, Enum):
    """Expiry selection formulas."""

    THIS_WEEK = "THIS_WEEK"
    NEXT_WEEK = "NEXT_WEEK"
    THIS_MONTH = "THIS_MONTH"
    NEXT_MONTH = "NEXT_MONTH"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


@dataclass(frozen=True)
class StrikeResult:
    """Result of strike formula calculation."""

    strike: float
    strike_offset: int  # Number of strikes from ATM
    formula_used: str


@dataclass(frozen=True)
class LotsResult:
    """Result of lots formula calculation."""

    lots: int
    formula_used: str
    net_delta: float | None = None
    net_gamma: float | None = None
    net_vega: float | None = None
    net_theta: float | None = None


ATM_STRIKE = "ATM"


def calculate_atm_strike(spot: float, strike_interval: float) -> float:
    """Calculate ATM strike rounded to nearest strike interval.

    Args:
        spot: Current underlying price
        strike_interval: Strike step (e.g., 50 for NIFTY, 100 for BANKNIFTY)

    Returns:
        ATM strike price
    """
    return round(spot / strike_interval) * strike_interval


def calculate_strike_by_offset(
    spot: float,
    strike_interval: float,
    offset: int,
    option_type: Literal["CE", "PE"],
) -> StrikeResult:
    """Calculate strike by offset from ATM in points.

    Args:
        spot: Current underlying price
        strike_interval: Strike step
        offset: Number of points from ATM (positive = OTM, negative = ITM)
        option_type: "CE" or "PE"

    Returns:
        StrikeResult with calculated strike
    """
    atm = calculate_atm_strike(spot, strike_interval)
    strike = atm + offset
    strike = round(strike / strike_interval) * strike_interval

    offset_strikes = int((strike - atm) / strike_interval) if option_type == "CE" else int((atm - strike) / strike_interval)

    return StrikeResult(
        strike=strike,
        strike_offset=offset_strikes,
        formula_used=f"ATM{'+' if offset >= 0 else ''}{offset}",
    )


def calculate_strike_by_percent(
    spot: float,
    strike_interval: float,
    percent: float,
    option_type: Literal["CE", "PE"],
) -> StrikeResult:
    """Calculate strike by percentage from spot.

    Args:
        spot: Current underlying price
        strike_interval: Strike step
        percent: Percentage from spot (e.g., 5 for 5% OTM)
        option_type: "CE" or "PE"

    Returns:
        StrikeResult with calculated strike
    """
    if option_type == "CE":
        target = spot * (1 + percent / 100.0)
    else:
        target = spot * (1 - percent / 100.0)

    strike = round(target / strike_interval) * strike_interval
    atm = calculate_atm_strike(spot, strike_interval)
    offset = int((strike - atm) / strike_interval) if option_type == "CE" else int((atm - strike) / strike_interval)

    return StrikeResult(
        strike=strike,
        strike_offset=offset,
        formula_used=f"SPOT{'+' if percent >= 0 else ''}{percent}%",
    )


def calculate_strike_by_delta(
    spot: float,
    strike_interval: float,
    target_delta: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: Literal["CE", "PE"] = "CE",
    max_iterations: int = 50,
) -> StrikeResult:
    """Calculate strike that matches target delta.

    Args:
        spot: Current underlying price
        strike_interval: Strike step
        target_delta: Target delta (absolute value, e.g., 0.20 for 20 delta)
        days_to_expiry: Days to expiry
        volatility: Implied volatility
        rate: Risk-free rate
        dividend_yield: Dividend yield
        option_type: "CE" or "PE"
        max_iterations: Maximum iterations for convergence

    Returns:
        StrikeResult with calculated strike
    """
    from app.quant.options.pricing import calculate_greeks

    target_delta = abs(target_delta)
    if option_type == "PE":
        target_delta = -target_delta

    low_strike = spot * 0.5
    high_strike = spot * 1.5

    for _ in range(max_iterations):
        mid_strike = (low_strike + high_strike) / 2
        mid_strike = round(mid_strike / strike_interval) * strike_interval

        greeks = calculate_greeks(
            spot, mid_strike, days_to_expiry, volatility, rate, dividend_yield, option_type
        )

        current_delta = greeks.delta

        if abs(current_delta - target_delta) < 0.001:
            atm = calculate_atm_strike(spot, strike_interval)
            offset = int((mid_strike - atm) / strike_interval)
            return StrikeResult(
                strike=mid_strike,
                strike_offset=offset,
                formula_used=f"DELTA:{abs(target_delta):.2f}",
            )

        if option_type == "CE":
            if current_delta < target_delta:
                low_strike = mid_strike
            else:
                high_strike = mid_strike
        else:
            if current_delta > target_delta:
                low_strike = mid_strike
            else:
                high_strike = mid_strike

    atm = calculate_atm_strike(spot, strike_interval)
    offset = int((mid_strike - atm) / strike_interval)
    return StrikeResult(
        strike=mid_strike,
        strike_offset=offset,
        formula_used=f"DELTA:{abs(target_delta):.2f}",
    )


def delta_neutral_lots(
    legs: list[dict],
    spot: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    max_lots: int = 100,
) -> LotsResult:
    """Calculate lot sizes to achieve delta neutrality.

    Args:
        legs: List of leg dicts with 'strike', 'option_type', 'action', 'base_lots'
        spot: Current underlying price
        days_to_expiry: Days to expiry
        volatility: Implied volatility
        rate: Risk-free rate
        dividend_yield: Dividend yield
        max_lots: Maximum lots per leg

    Returns:
        LotsResult with calculated lots
    """
    from app.quant.options.pricing import calculate_greeks

    net_delta = 0.0
    leg_deltas = []

    for leg in legs:
        greeks = calculate_greeks(
            spot,
            leg["strike"],
            days_to_expiry,
            volatility,
            rate,
            dividend_yield,
            leg["option_type"],
        )
        delta = greeks.delta
        if leg["action"] == "sell":
            delta = -delta
        leg_deltas.append(delta)
        base_lots = leg.get("base_lots", 1)
        net_delta += delta * base_lots

    if abs(net_delta) < 0.001:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="DELTA_NEUTRAL",
            net_delta=0.0,
        )

    adjustment_leg_idx = 0
    adjustment_delta = leg_deltas[adjustment_leg_idx]
    if abs(adjustment_delta) < 0.001:
        for i, d in enumerate(leg_deltas):
            if abs(d) > 0.001:
                adjustment_leg_idx = i
                adjustment_delta = d
                break

    lots_needed = -net_delta / adjustment_delta
    lots_needed = max(1, min(round(lots_needed), max_lots))

    result_lots = [leg.get("base_lots", 1) for leg in legs]
    result_lots[adjustment_leg_idx] = lots_needed

    final_delta = net_delta + lots_needed * adjustment_delta - result_lots[adjustment_leg_idx] * adjustment_delta

    return LotsResult(
        lots=result_lots,
        formula_used="DELTA_NEUTRAL",
        net_delta=round(final_delta, 4),
    )


def vega_neutral_lots(
    legs: list[dict],
    spot: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> LotsResult:
    """Calculate lot sizes to achieve vega neutrality."""
    from app.quant.options.pricing import calculate_greeks

    net_vega = 0.0
    leg_vegas = []

    for leg in legs:
        greeks = calculate_greeks(
            spot,
            leg["strike"],
            days_to_expiry,
            volatility,
            rate,
            dividend_yield,
            leg["option_type"],
        )
        vega = greeks.vega
        if leg["action"] == "sell":
            vega = -vega
        leg_vegas.append(vega)
        base_lots = leg.get("base_lots", 1)
        net_vega += vega * base_lots

    if abs(net_vega) < 0.01:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="VEGA_NEUTRAL",
            net_vega=0.0,
        )

    adjustment_idx = max(range(len(leg_vegas)), key=lambda i: abs(leg_vegas[i]))
    adjustment_vega = leg_vegas[adjustment_idx]

    if abs(adjustment_vega) < 0.01:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="VEGA_NEUTRAL",
            net_vega=net_vega,
        )

    lots_needed = -net_vega / adjustment_vega
    lots_needed = max(1, round(lots_needed))

    result_lots = [leg.get("base_lots", 1) for leg in legs]
    result_lots[adjustment_idx] = lots_needed

    return LotsResult(
        lots=result_lots,
        formula_used="VEGA_NEUTRAL",
        net_vega=round(net_vega + lots_needed * adjustment_vega, 4),
    )


def gamma_neutral_lots(
    legs: list[dict],
    spot: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> LotsResult:
    """Calculate lot sizes to achieve gamma neutrality."""
    from app.quant.options.pricing import calculate_greeks

    net_gamma = 0.0
    leg_gammas = []

    for leg in legs:
        greeks = calculate_greeks(
            spot,
            leg["strike"],
            days_to_expiry,
            volatility,
            rate,
            dividend_yield,
            leg["option_type"],
        )
        gamma = greeks.gamma
        if leg["action"] == "sell":
            gamma = -gamma
        leg_gammas.append(gamma)
        base_lots = leg.get("base_lots", 1)
        net_gamma += gamma * base_lots

    if abs(net_gamma) < 0.0001:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="GAMMA_NEUTRAL",
            net_gamma=0.0,
        )

    adjustment_idx = max(range(len(leg_gammas)), key=lambda i: abs(leg_gammas[i]))
    adjustment_gamma = leg_gammas[adjustment_idx]

    if abs(adjustment_gamma) < 0.0001:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="GAMMA_NEUTRAL",
            net_gamma=net_gamma,
        )

    lots_needed = -net_gamma / adjustment_gamma
    lots_needed = max(1, round(lots_needed))

    result_lots = [leg.get("base_lots", 1) for leg in legs]
    result_lots[adjustment_idx] = lots_needed

    return LotsResult(
        lots=result_lots,
        formula_used="GAMMA_NEUTRAL",
        net_gamma=round(net_gamma + lots_needed * adjustment_gamma, 6),
    )


def theta_neutral_lots(
    legs: list[dict],
    spot: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> LotsResult:
    """Calculate lot sizes to achieve theta neutrality (rarely used)."""
    from app.quant.options.pricing import calculate_greeks

    net_theta = 0.0
    leg_thetas = []

    for leg in legs:
        greeks = calculate_greeks(
            spot,
            leg["strike"],
            days_to_expiry,
            volatility,
            rate,
            dividend_yield,
            leg["option_type"],
        )
        theta = greeks.theta
        if leg["action"] == "sell":
            theta = -theta
        leg_thetas.append(theta)
        base_lots = leg.get("base_lots", 1)
        net_theta += theta * base_lots

    if abs(net_theta) < 0.01:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="THETA_NEUTRAL",
            net_theta=0.0,
        )

    adjustment_idx = max(range(len(leg_thetas)), key=lambda i: abs(leg_thetas[i]))
    adjustment_theta = leg_thetas[adjustment_idx]

    if abs(adjustment_theta) < 0.01:
        return LotsResult(
            lots=[leg.get("base_lots", 1) for leg in legs],
            formula_used="THETA_NEUTRAL",
            net_theta=net_theta,
        )

    lots_needed = -net_theta / adjustment_theta
    lots_needed = max(1, round(lots_needed))

    result_lots = [leg.get("base_lots", 1) for leg in legs]
    result_lots[adjustment_idx] = lots_needed

    return LotsResult(
        lots=result_lots,
        formula_used="THETA_NEUTRAL",
        net_theta=round(net_theta + lots_needed * adjustment_theta, 4),
    )


def capital_pct_lots(
    capital: float,
    premium_per_lot: float,
    pct: float,
    lot_size: int = 1,
) -> LotsResult:
    """Calculate lots based on percentage of capital.

    Args:
        capital: Total capital available
        premium_per_lot: Option premium per lot
        pct: Percentage of capital to deploy (e.g., 10 for 10%)
        lot_size: Number of units per lot

    Returns:
        LotsResult with calculated lots
    """
    deployable = capital * pct / 100.0
    lots = int(deployable / (premium_per_lot * lot_size))
    lots = max(1, lots)

    return LotsResult(
        lots=lots,
        formula_used=f"CAPITAL_PCT:{pct}",
    )


def parse_strike_formula(
    formula: str,
    spot: float,
    strike_interval: float,
    days_to_expiry: float = 30,
    volatility: float = 0.20,
    option_type: Literal["CE", "PE"] = "CE",
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> StrikeResult:
    """Parse and evaluate a strike formula string.

    Supported formats:
    - "ATM" -> ATM strike
    - "ATM+200" -> 200 points above ATM
    - "ATM-3" -> 3 strikes below ATM
    - "SPOT+5%" -> 5% above spot
    - "DELTA:0.20" -> Strike with 0.20 delta
    - "18000" -> Fixed strike

    Args:
        formula: Formula string
        spot: Current underlying price
        strike_interval: Strike step
        days_to_expiry: Days to expiry (for delta calculation)
        volatility: IV (for delta calculation)
        option_type: "CE" or "PE"
        rate: Risk-free rate
        dividend_yield: Dividend yield

    Returns:
        StrikeResult with calculated strike
    """
    formula = formula.strip().upper()

    if formula == "ATM":
        strike = calculate_atm_strike(spot, strike_interval)
        return StrikeResult(strike=strike, strike_offset=0, formula_used="ATM")

    if formula.startswith("ATM+"):
        offset = int(formula[4:])
        return calculate_strike_by_offset(spot, strike_interval, offset, option_type)

    if formula.startswith("ATM-"):
        offset = int(formula[3:])
        return calculate_strike_by_offset(spot, strike_interval, offset, option_type)

    if formula.startswith("SPOT+"):
        percent = float(formula[5:].rstrip("%"))
        return calculate_strike_by_percent(spot, strike_interval, percent, option_type)

    if formula.startswith("SPOT-"):
        percent = float(formula[4:].rstrip("%"))
        return calculate_strike_by_percent(spot, strike_interval, -percent, option_type)

    if formula.startswith("DELTA:"):
        target_delta = float(formula[6:])
        return calculate_strike_by_delta(
            spot, strike_interval, target_delta, days_to_expiry, volatility, rate, dividend_yield, option_type
        )

    try:
        strike = float(formula)
        atm = calculate_atm_strike(spot, strike_interval)
        offset = int((strike - atm) / strike_interval)
        return StrikeResult(strike=strike, strike_offset=offset, formula_used=f"FIXED:{strike}")
    except ValueError:
        pass

    atm = calculate_atm_strike(spot, strike_interval)
    return StrikeResult(strike=atm, strike_offset=0, formula_used=f"UNKNOWN:{formula}")
