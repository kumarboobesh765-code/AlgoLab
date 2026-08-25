"""Black-Scholes pricing and Greeks.

Pure functions, no I/O. Conventions:
- `years` = time to expiry in calendar years (days / 365)
- `iv` and `rate` are annual decimals (0.15 = 15%)
- `kind` is "call" or "put"
- theta is returned per calendar day, vega per 1-point IV move (i.e. 1 vol pt
  = 0.01), matching how Indian F&O traders read Greeks.
Degenerate inputs (years <= 0 or iv <= 0) collapse to intrinsic value with
zero time-value greeks.
"""

import math

SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _d1_d2(
    spot: float, strike: float, years: float, iv: float, rate: float
) -> tuple[float, float]:
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * years) / (iv * sqrt_t)
    return d1, d1 - iv * sqrt_t


def bs_price(
    spot: float,
    strike: float,
    years: float,
    iv: float,
    kind: str,
    rate: float = 0.0,
) -> float:
    """European option price under Black-Scholes."""
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    if years <= 0 or iv <= 0:
        intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
        return intrinsic
    d1, d2 = _d1_d2(spot, strike, years, iv, rate)
    disc = math.exp(-rate * years)
    if kind == "call":
        return spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2)
    return strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def bs_delta(
    spot: float, strike: float, years: float, iv: float, kind: str, rate: float = 0.0
) -> float:
    """Share-price delta: call in (0, 1), put in (-1, 0)."""
    if years <= 0 or iv <= 0:
        if kind == "call":
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0
    d1, _ = _d1_d2(spot, strike, years, iv, rate)
    if kind == "call":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


def bs_gamma(
    spot: float, strike: float, years: float, iv: float, rate: float = 0.0
) -> float:
    if years <= 0 or iv <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, years, iv, rate)
    return _norm_pdf(d1) / (spot * iv * math.sqrt(years))


def bs_theta(
    spot: float, strike: float, years: float, iv: float, kind: str, rate: float = 0.0
) -> float:
    """Theta per calendar day (negative for long options)."""
    if years <= 0 or iv <= 0:
        return 0.0
    d1, d2 = _d1_d2(spot, strike, years, iv, rate)
    sqrt_t = math.sqrt(years)
    disc = math.exp(-rate * years)
    common = -(spot * _norm_pdf(d1) * iv) / (2.0 * sqrt_t)
    if kind == "call":
        per_year = common - rate * strike * disc * _norm_cdf(d2)
    else:
        per_year = common + rate * strike * disc * _norm_cdf(-d2)
    return per_year / 365.0


def bs_vega(
    spot: float, strike: float, years: float, iv: float, rate: float = 0.0
) -> float:
    """Vega per 1 vol point (price change for IV moving 0.01)."""
    if years <= 0 or iv <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, years, iv, rate)
    per_unit_iv = spot * _norm_pdf(d1) * math.sqrt(years)
    return per_unit_iv * 0.01


def implied_vol(
    price: float,
    spot: float,
    strike: float,
    years: float,
    kind: str,
    rate: float = 0.0,
) -> float | None:
    """Implied volatility via bisection. Returns None when no solution exists."""
    if years <= 0 or price <= 0:
        return None
    intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
    if price <= intrinsic + 1e-9:
        return None
    lo, hi = 1e-4, 5.0
    if bs_price(spot, strike, years, hi, kind, rate) < price:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if bs_price(spot, strike, years, mid, kind, rate) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0
