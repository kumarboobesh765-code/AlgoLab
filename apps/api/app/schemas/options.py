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
    strike_step: int | None = None
    expiries: list[str] | None = None


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


class AnalyticsRequest(BaseModel):
    underlying: str = Field(default="NIFTY", min_length=1, max_length=50)
    expiry: str | None = None


class PCRResponse(BaseModel):
    pcr_oi: float
    pcr_volume: float
    total_call_oi: int
    total_put_oi: int
    total_call_volume: int
    total_put_volume: int
    strike_pcr: dict[str, float]


class MaxPainResponse(BaseModel):
    max_pain_strike: float
    min_pain: float
    support_resistance: dict


class IVSurfaceResponse(BaseModel):
    atm_iv: float
    skew: float
    kurtosis: float


class GreeksHeatmapResponse(BaseModel):
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    strike_greeks: dict[str, dict[str, float]]


class OptionChainAnalyticsResponse(BaseModel):
    underlying: str
    spot: float
    expiry: str
    pcr: PCRResponse
    max_pain: MaxPainResponse
    iv_surface: IVSurfaceResponse
    greeks_heatmap: GreeksHeatmapResponse


class OptionsBacktestRequest(BaseModel):
    underlying: str = Field(default="NIFTY", min_length=1, max_length=50)
    legs: list[dict] = Field(min_length=1, max_length=12)
    dte_days: int = Field(default=7, ge=0, le=365)
    volatility: float = Field(default=0.20, gt=0, le=5)
    lot_size: int = Field(default=50, ge=1, le=10000)
    initial_capital: float = Field(default=100000, gt=0)
    auto_roll: bool = Field(default=True)


class OptionsLegPnLOut(BaseModel):
    leg_index: int
    action: str
    option_type: str
    strike: float
    expiry: str
    lots: int
    entry_price: float
    entry_date: str
    current_price: float
    current_date: str
    days_held: int
    gross_pnl: float
    costs: dict[str, float]
    net_pnl: float
    exit_reason: str | None = None


class OptionsBacktestResponse(BaseModel):
    legs: list[OptionsLegPnLOut]
    daily_values: list[dict]
    summary: dict
    cost_breakdown: dict[str, float]
