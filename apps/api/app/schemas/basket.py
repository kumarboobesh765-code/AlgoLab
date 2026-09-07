"""Request/response schemas for the Options Basket combined-premium analysis."""

from pydantic import BaseModel, Field


class BasketLegInput(BaseModel):
    action: str = Field(pattern=r"^(buy|sell)$")
    option_type: str = Field(pattern=r"^(CE|PE)$")
    strike: float = Field(gt=0)
    premium: float = Field(ge=0)
    quantity: int = Field(default=1, ge=1, le=1000)


class BasketPayoffRequest(BaseModel):
    spot: float = Field(gt=0, description="Current underlying price")
    legs: list[BasketLegInput] = Field(min_length=1, max_length=12)
    days_to_expiry: int = Field(default=7, ge=0, le=365)
    volatility: float = Field(default=16.0, ge=0.1, le=500, description="Annualized IV in percent")


class BasketPayoffPoint(BaseModel):
    underlying: float
    current_value: float
    expiry_value: float
    combined_premium: float


class BasketPayoffResponse(BaseModel):
    spot: float
    days_to_expiry: int
    payoff: list[BasketPayoffPoint]
    breakeven_points: list[float]
    max_profit: float | None
    max_loss: float | None
    net_premium: float
    combined_delta: float
    combined_gamma: float
    combined_theta: float
    combined_vega: float
