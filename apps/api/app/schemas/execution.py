"""Request/response schemas for the Execution (live trading) endpoints.

Phase 10 exposes a broker-agnostic execution surface. All endpoints are
gated behind risk guards and an audit trail; real fund movement only happens
when a non-demo broker (e.g. Zerodha) is configured.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.execution.algorithms import ExecutionAlgo
from app.execution.gateway import (
    Exchange,
    OrderSide,
    OrderType,
    ProductType,
    Segment,
    Validity,
)


class PlaceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker: str = Field(default="mock", pattern=r"^(mock|zerodha)$")
    symbol: str = Field(min_length=1, max_length=50)
    exchange: Exchange
    segment: Segment
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(ge=1, le=1_000_000)
    product: ProductType = ProductType.MIS
    validity: Validity = Validity.DAY
    price: float = 0.0
    trigger_price: float = 0.0
    disclosed_quantity: int = 0
    tag: str | None = Field(default=None, max_length=40)
    is_amo: bool = False
    strategy_tag: str | None = Field(default=None, max_length=40)


class AlgoOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker: str = Field(default="mock", pattern=r"^(mock|zerodha)$")
    symbol: str = Field(min_length=1, max_length=50)
    exchange: Exchange
    segment: Segment
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(ge=1, le=1_000_000)
    product: ProductType = ProductType.MIS
    validity: Validity = Validity.DAY
    price: float = 0.0
    trigger_price: float = 0.0
    algo: ExecutionAlgo = ExecutionAlgo.TWAP
    start: str = Field(description="ISO datetime for first slice release")
    end: str = Field(description="ISO datetime for last slice release")
    slices: int = Field(default=10, ge=1, le=1000)
    volume_profile: list[float] | None = Field(default=None, max_length=1000)
    jitter_seconds: int = 0
    tag: str | None = Field(default=None, max_length=40)


class OrderOut(BaseModel):
    order_id: str
    broker_order_id: str
    symbol: str
    exchange: str
    segment: str
    side: str
    order_type: str
    product: str
    quantity: int
    price: float
    trigger_price: float
    filled_quantity: int
    pending_quantity: int
    status: str
    average_price: float
    tag: str | None = None
    rejection_reason: str | None = None


class PositionOut(BaseModel):
    symbol: str
    exchange: str
    segment: str
    product: str
    side: str
    quantity: int
    average_price: float
    last_price: float
    unrealized_pnl: float
    realized_pnl: float
    value: float


class FundsOut(BaseModel):
    equity: float
    commodity: float
    used_margin: float
    available_cash: float
    collateral: float


class RiskStatusOut(BaseModel):
    kill_switch: bool
    max_order_notional: float
    max_position_notional: float
    max_orders_per_day: int
    orders_today: int
    daily_pnl: float
    max_daily_loss: float


class AlgoParentOut(BaseModel):
    parent_id: str
    broker: str
    symbol: str
    side: str
    quantity: int
    algo: str
    total_slices: int
    released_slices: int


class AuditOut(BaseModel):
    timestamp: str
    action: str
    detail: str
    broker_order_id: str
    user: str
