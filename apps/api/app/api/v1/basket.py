"""Basket payoff API endpoints."""

from fastapi import APIRouter

from app.options.basket import compute_basket_payoff
from app.schemas.basket import BasketPayoffRequest, BasketPayoffResponse

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
