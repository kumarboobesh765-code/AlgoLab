"""Request/response schemas for the Options Lab endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class OptionLegInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern=r"^(buy|sell)$")
    option_type: str = Field(pattern=r"^(CE|PE)$")
    strike_offset: int = Field(default=0, ge=-100_000, le=100_000)
    lots: int = Field(default=1, ge=1, le=1000)


class PayoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    underlying: str = Field(default="NIFTY", min_length=1, max_length=50)
    legs: list[OptionLegInput] = Field(min_length=1, max_length=8)
    expiry: str | None = None
    spot_override: float | None = Field(default=None, gt=0)
    dte_days: int = Field(default=7, ge=0, le=365)
    interest_rate: float = Field(default=0.065, ge=0, le=0.5)
    iv_override: float | None = Field(default=None, gt=0, le=500)  # percent
    lot_size: int = Field(default=1, ge=1, le=10_000)


class PayoffLeg(OptionLegInput):
    strike: int
    premium: float
    iv_pct: float
    delta: float
    gamma: float
    theta_per_day: float
    vega: float


class PayoffPoint(BaseModel):
    price: float
    pnl: float


class PayoffMetricsOut(BaseModel):
    net_premium: float
    max_profit: float | None  # None = unlimited
    max_loss: float | None
    breakevens: list[float]
    risk_reward: float | None


class NetGreeks(BaseModel):
    delta: float
    gamma: float
    theta_per_day: float
    vega: float


class PayoffResponse(BaseModel):
    underlying: str
    spot: float
    atm_strike: int
    expiry: str
    dte_days: int
    lot_size: int
    is_demo: bool
    provider: str
    legs: list[PayoffLeg]
    curve: list[PayoffPoint]
    metrics: PayoffMetricsOut
    net_greeks: NetGreeks


class MonteCarloRequest(PayoffRequest):
    paths: int = Field(default=10_000, ge=100, le=20_000)
    horizon_days: int | None = Field(default=None, ge=1, le=365)
    vol_override: float | None = Field(default=None, gt=0, le=500)  # percent


class MonteCarloBin(BaseModel):
    lo: float
    hi: float
    count: int


class MonteCarloStats(BaseModel):
    mean: float
    std: float
    median: float
    p5: float
    p95: float
    worst: float
    best: float
    prob_profit: float
    var_95: float


class MonteCarloResponse(BaseModel):
    stats: MonteCarloStats
    bins: list[MonteCarloBin]
    paths: int
    vol_used_pct: float
    horizon_days: int
