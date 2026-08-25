"""Black-Scholes option pricing model with Greeks calculation.

Pure-Python implementation for CE/PE European options with dividend yield support.
All calculations use annualized volatility and time in years.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OptionPrice:
    """Option price with breakdown."""

    price: float
    intrinsic_value: float
    time_value: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_price(
    spot: float,
    strike: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: str = "CE",
) -> float:
    """Calculate Black-Scholes option price.

    Args:
        spot: Current underlying price
        strike: Strike price
        days_to_expiry: Days until expiration
        volatility: Implied volatility (annualized, e.g., 0.20 for 20%)
        rate: Risk-free interest rate (annualized, e.g., 0.06 for 6%)
        dividend_yield: Dividend yield (annualized, for index options)
        option_type: "CE" for call, "PE" for put

    Returns:
        Option price (premium)
    """
    if days_to_expiry <= 0:
        intrinsic = max(spot - strike, 0) if option_type == "CE" else max(strike - spot, 0)
        return intrinsic

    if volatility <= 0:
        return 0.0

    t = days_to_expiry / 365.0
    sqrt_t = math.sqrt(t)

    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility**2) * t) / (
        volatility * sqrt_t
    )
    d2 = d1 - volatility * sqrt_t

    if option_type == "CE":
        price = spot * math.exp(-dividend_yield * t) * _norm_cdf(d1) - strike * math.exp(
            -rate * t
        ) * _norm_cdf(d2)
    else:
        price = strike * math.exp(-rate * t) * _norm_cdf(-d2) - spot * math.exp(
            -dividend_yield * t
        ) * _norm_cdf(-d1)

    return max(price, 0.0)


def calculate_greeks(
    spot: float,
    strike: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: str = "CE",
) -> OptionPrice:
    """Calculate option price and all Greeks.

    Returns:
        OptionPrice with price, intrinsic/time value, and all Greeks
    """
    price = black_scholes_price(spot, strike, days_to_expiry, volatility, rate, dividend_yield, option_type)
    intrinsic = max(spot - strike, 0) if option_type == "CE" else max(strike - spot, 0)
    time_value = price - intrinsic

    if days_to_expiry <= 0:
        return OptionPrice(
            price=intrinsic,
            intrinsic_value=intrinsic,
            time_value=0.0,
            delta=1.0 if option_type == "CE" else -1.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            rho=0.0,
        )

    t = days_to_expiry / 365.0
    sqrt_t = math.sqrt(t)

    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility**2) * t) / (
        volatility * sqrt_t
    )
    d2 = d1 - volatility * sqrt_t

    nd1 = _norm_cdf(d1)
    nd2 = _norm_cdf(d2)
    npd1 = _norm_pdf(d1)

    discount_factor = math.exp(-dividend_yield * t)

    if option_type == "CE":
        delta = discount_factor * nd1
    else:
        delta = discount_factor * (nd1 - 1.0)

    gamma = discount_factor * npd1 / (spot * volatility * sqrt_t)

    theta_annual = (
        -(spot * npd1 * volatility * discount_factor) / (2 * sqrt_t)
        - rate * strike * math.exp(-rate * t) * (nd2 if option_type == "CE" else _norm_cdf(-d2))
        + dividend_yield * spot * discount_factor * (nd1 if option_type == "CE" else _norm_cdf(-d1))
    )
    theta = theta_annual / 365.0

    vega = spot * discount_factor * npd1 * sqrt_t / 100.0

    if option_type == "CE":
        rho = strike * t * math.exp(-rate * t) * nd2 / 100.0
    else:
        rho = -strike * t * math.exp(-rate * t) * _norm_cdf(-d2) / 100.0

    return OptionPrice(
        price=price,
        intrinsic_value=intrinsic,
        time_value=time_value,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
    )


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    days_to_expiry: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: str = "CE",
    max_iterations: int = 100,
    tolerance: float = 0.0001,
) -> float:
    """Calculate implied volatility using Newton-Raphson method.

    Args:
        market_price: Observed market price
        spot: Current underlying price
        strike: Strike price
        days_to_expiry: Days until expiration
        rate: Risk-free interest rate
        dividend_yield: Dividend yield
        option_type: "CE" or "PE"
        max_iterations: Maximum Newton-Raphson iterations
        tolerance: Convergence tolerance

    Returns:
        Implied volatility (annualized)
    """
    if days_to_expiry <= 0:
        return 0.0

    intrinsic = max(spot - strike, 0) if option_type == "CE" else max(strike - spot, 0)
    if market_price <= intrinsic:
        return 0.0

    vol = 0.2
    for _ in range(max_iterations):
        price = black_scholes_price(spot, strike, days_to_expiry, vol, rate, dividend_yield, option_type)
        diff = price - market_price

        if abs(diff) < tolerance:
            return vol

        greeks = calculate_greeks(spot, strike, days_to_expiry, vol, rate, dividend_yield, option_type)
        vega_dollar = greeks.vega * 100.0

        if vega_dollar < 1e-6:
            break

        vol = vol - diff / vega_dollar
        vol = max(0.01, min(vol, 5.0))

    return vol
