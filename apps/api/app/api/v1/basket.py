"""Basket payoff and scenario-analysis API endpoints."""

from fastapi import APIRouter

from app.options.basket import compute_basket_payoff, compute_scenarios
from app.schemas.basket import (
    BasketPayoffRequest,
    BasketPayoffResponse,
    ScenarioRequest,
    ScenarioResponse,
)

router = APIRouter(prefix="/basket", tags=["basket"])


@router.post("/payoff", response_model=BasketPayoffResponse)
async def basket_payoff(request: BasketPayoffRequest) -> BasketPayoffResponse:
    """Compute combined-premium payoff for a multi-leg options basket.

    Returns:
    - payoff curve: current time-value and expiry intrinsic value across -25% to +25% of spot
    - breakeven points: underlying prices where expiry P&L = 0
    - max_profit / max_loss: capped values (None = unlimited)
    - combined Greeks: delta, gamma, theta, vega summed across all legs
    """
    return compute_basket_payoff(request)


@router.post("/scenario", response_model=ScenarioResponse)
async def basket_scenario(request: ScenarioRequest) -> ScenarioResponse:
    """What-if analysis: reprice the basket under Spot / IV / DTE offsets.

    Mirrors AlgoTest's Scenario Analysis. The base inputs are always repriced
    first, then each scenario nudges spot_pct, iv_points and/or dte_days so a
    trader can compare, for example, "down 5%", "IV +8", "2 days to expiry"
    side by side.
    """
    return compute_scenarios(request)
