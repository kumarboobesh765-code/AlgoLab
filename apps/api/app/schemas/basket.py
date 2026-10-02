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


# ---------------------------------------------------------------------------
# Scenario Analysis (AlgoTest parity): what-if on Spot / IV / DTE
# ---------------------------------------------------------------------------

class ScenarioInput(BaseModel):
    """A single what-if adjustment applied to the base inputs."""

    name: str = Field(min_length=1, max_length=80)
    spot_offset_pct: float = Field(default=0.0, ge=-50.0, le=50.0)
    iv_offset_pts: float = Field(default=0.0, ge=-100.0, le=100.0)
    dte_offset_days: int = Field(default=0, ge=-365, le=365)


class ScenarioRequest(BaseModel):
    spot: float = Field(gt=0)
    legs: list[BasketLegInput] = Field(min_length=1, max_length=12)
    days_to_expiry: int = Field(default=7, ge=0, le=365)
    volatility: float = Field(default=16.0, ge=0.1, le=500)
    scenarios: list[ScenarioInput] = Field(default_factory=list, max_length=8)


class ScenarioResult(BaseModel):
    name: str
    spot: float
    days_to_expiry: int
    volatility: float
    net_premium: float
    combined_delta: float
    combined_gamma: float
    combined_theta: float
    combined_vega: float
    breakeven_points: list[float]
    max_profit: float | None
    max_loss: float | None
    payoff: list[BasketPayoffPoint]


class ScenarioResponse(BaseModel):
    base: ScenarioResult
    scenarios: list[ScenarioResult]
