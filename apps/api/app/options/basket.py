"""Options Basket: combined-premium payoff analysis for multi-leg strategies.

Computes the aggregate payoff across all legs, showing both current time-value
and expiry intrinsic value curves.
"""


from app.options.greeks import bs_delta, bs_gamma, bs_price, bs_theta, bs_vega
from app.schemas.basket import (
    BasketPayoffPoint,
    BasketPayoffRequest,
    BasketPayoffResponse,
    ScenarioRequest,
    ScenarioResponse,
    ScenarioResult,
)


def _round_to_nearest(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(value / step) * step


def _find_breakevens(
    payoff: list[BasketPayoffPoint],
) -> list[float]:
    breakevens: list[float] = []
    for i in range(len(payoff) - 1):
        p0 = payoff[i]
        p1 = payoff[i + 1]
        if (p0.expiry_value <= 0 < p1.expiry_value) or (p1.expiry_value <= 0 < p0.expiry_value):
            if p1.expiry_value == p0.expiry_value:
                continue
            t = -p0.expiry_value / (p1.expiry_value - p0.expiry_value)
            be = _round_to_nearest(p0.underlying + t * (p1.underlying - p0.underlying), 0.5)
            breakevens.append(be)
    return sorted(set(breakevens))


def _sum_greeks(
    legs: list[dict],
    greek: str,
    spot: float,
    T: float,
    sigma: float,
    r: float,
) -> float:
    total = 0.0
    for leg in legs:
        K = leg["strike"]
        qty = leg.get("quantity", 1)
        sign = 1.0 if leg["action"] == "buy" else -1.0
        otype = leg["option_type"]

        if greek == "delta":
            val = bs_delta(spot, K, T, sigma, otype.lower(), r)
        elif greek == "gamma":
            val = bs_gamma(spot, K, T, sigma, r)
        elif greek == "theta":
            val = bs_theta(spot, K, T, sigma, otype.lower(), r)
        elif greek == "vega":
            val = bs_vega(spot, K, T, sigma, r)
        else:
            val = 0.0

        total += sign * val * qty

    return total


def compute_basket_payoff(request: BasketPayoffRequest) -> BasketPayoffResponse:
    spot = request.spot
    legs = [leg.model_dump() for leg in request.legs]
    days_to_expiry = request.days_to_expiry
    volatility_pct = request.volatility

    T = days_to_expiry / 365.0
    sigma = volatility_pct / 100.0
    r = 0.06

    underlying_range: list[float] = []
    step_pct = 0.0025
    for i in range(-50, 51):
        U = spot * (1.0 + i * step_pct)
        underlying_range.append(round(U, 2))

    payoff: list[BasketPayoffPoint] = []
    for U in underlying_range:
        current_value = 0.0
        for leg in legs:
            K = leg["strike"]
            qty = leg.get("quantity", 1)
            sign = 1.0 if leg["action"] == "buy" else -1.0

            if leg["option_type"] == "CE":
                price = bs_price(U, K, T, sigma, "call", r)
            else:
                price = bs_price(U, K, T, sigma, "put", r)

            current_value += sign * price * qty

        expiry_value = 0.0
        for leg in legs:
            K = leg["strike"]
            qty = leg.get("quantity", 1)
            sign = 1.0 if leg["action"] == "buy" else -1.0

            if leg["option_type"] == "CE":
                intrinsic = max(0.0, U - K)
            else:
                intrinsic = max(0.0, K - U)

            expiry_value += sign * intrinsic * qty

        payoff.append(
            BasketPayoffPoint(
                underlying=round(U, 2),
                current_value=round(current_value, 2),
                expiry_value=round(expiry_value, 2),
                combined_premium=round(current_value, 2),
            )
        )

    net_premium = -sum(
        (1.0 if leg["action"] == "buy" else -1.0) * leg.get("premium", 0) * leg.get("quantity", 1)
        for leg in legs
    )

    breakeven_points = _find_breakevens(payoff)

    expiry_values = [p.expiry_value for p in payoff]

    if expiry_values:
        max_profit_val = max(expiry_values)
        max_loss_val = min(expiry_values)

        bought_calls = any(
            leg["option_type"] == "CE" and leg["action"] == "buy" for leg in legs
        )
        sold_calls = any(
            leg["option_type"] == "CE" and leg["action"] == "sell" for leg in legs
        )
        bought_puts = any(
            leg["option_type"] == "PE" and leg["action"] == "buy" for leg in legs
        )
        sold_puts = any(
            leg["option_type"] == "PE" and leg["action"] == "sell" for leg in legs
        )

        profit_uncapped = bought_calls and not sold_calls
        loss_uncapped = (sold_puts and not bought_puts) or (sold_calls and not bought_calls)

        max_profit: float | None = None if profit_uncapped else max_profit_val
        max_loss: float | None = None if loss_uncapped else max_loss_val
    else:
        max_profit = None
        max_loss = None

    combined_delta = _sum_greeks(legs, "delta", spot, T, sigma, r)
    combined_gamma = _sum_greeks(legs, "gamma", spot, T, sigma, r)
    combined_theta = _sum_greeks(legs, "theta", spot, T, sigma, r)
    combined_vega = _sum_greeks(legs, "vega", spot, T, sigma, r)

    return BasketPayoffResponse(
        spot=spot,
        days_to_expiry=days_to_expiry,
        payoff=payoff,
        breakeven_points=breakeven_points,
        max_profit=max_profit,
        max_loss=max_loss,
        net_premium=round(net_premium, 2),
        combined_delta=round(combined_delta, 4),
        combined_gamma=round(combined_gamma, 4),
        combined_theta=round(combined_theta, 4),
        combined_vega=round(combined_vega, 4),
    )


# ---------------------------------------------------------------------------
# Scenario Analysis
# ---------------------------------------------------------------------------

def _to_scenario_result(name: str, request: BasketPayoffRequest) -> ScenarioResult:
    resp = compute_basket_payoff(request)
    return ScenarioResult(
        name=name,
        spot=resp.spot,
        days_to_expiry=resp.days_to_expiry,
        volatility=request.volatility,
        net_premium=resp.net_premium,
        combined_delta=resp.combined_delta,
        combined_gamma=resp.combined_gamma,
        combined_theta=resp.combined_theta,
        combined_vega=resp.combined_vega,
        breakeven_points=resp.breakeven_points,
        max_profit=resp.max_profit,
        max_loss=resp.max_loss,
        payoff=resp.payoff,
    )


def compute_scenarios(request: ScenarioRequest) -> ScenarioResponse:
    """Reprice the basket under the base inputs and each what-if scenario.

    Each scenario nudges Spot (pct), IV (points) and/or DTE (days) relative to
    the base, so a trader can compare e.g. "down 5%", "IV +10", "expiry in 2
    days" side by side. Inputs are clamped to sane ranges after applying offsets.
    """
    base_req = BasketPayoffRequest(
        spot=request.spot,
        legs=request.legs,
        days_to_expiry=request.days_to_expiry,
        volatility=request.volatility,
    )
    base = _to_scenario_result("Base", base_req)

    results: list[ScenarioResult] = []
    for sc in request.scenarios:
        spot = round(request.spot * (1.0 + sc.spot_offset_pct / 100.0), 2)
        iv = round(max(0.1, request.volatility + sc.iv_offset_pts), 2)
        dte = max(0, request.days_to_expiry + sc.dte_offset_days)
        sub = BasketPayoffRequest(
            spot=spot,
            legs=request.legs,
            days_to_expiry=dte,
            volatility=iv,
        )
        results.append(_to_scenario_result(sc.name, sub))

    return ScenarioResponse(base=base, scenarios=results)
