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

    broker: str = Field(default="mock", pattern=r"^(mock|zerodha|upstox|angelone|dhan|fyers|icici|5paisa)$")
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

    broker: str = Field(default="mock", pattern=r"^(mock|zerodha|upstox|angelone|dhan|fyers|icici|5paisa)$")
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
    # SEBI retail-algo compliance telemetry
    ops_limit: int = 10
    ops_current: int = 0
    orders_placed: int = 0
    trades_executed: int = 0
    order_to_trade_ratio: float | None = None
    otr_warning: str | None = None


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


class AlgoRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    segment: Segment
    exchange: Exchange
    strategy_id: str | None = Field(default=None, max_length=80)


class AlgoRegisterOut(BaseModel):
    algo_id: str
    name: str
    segment: str
    exchange: str
    strategy_id: str | None = None
    active: bool


class RegisteredAlgoOut(BaseModel):
    algo_id: str
    name: str
    segment: str
    exchange: str
    strategy_id: str | None = None
    active: bool
    registered_at: str


class BracketOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker: str = Field(default="mock", pattern=r"^(mock|zerodha|upstox|angelone|dhan|fyers|icici|5paisa)$")
    symbol: str = Field(min_length=1, max_length=50)
    exchange: Exchange
    segment: Segment
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(ge=1, le=1_000_000)
    product: ProductType = ProductType.MIS
    price: float = 0.0
    trigger_price: float = 0.0
    target_price: float = Field(gt=0)
    stop_loss_price: float = Field(gt=0)
    trailing_stop: float | None = None
    tag: str | None = Field(default=None, max_length=40)
    algo_id: str | None = Field(default=None, max_length=40)


class BracketOut(BaseModel):
    bracket_id: str
    entry_order_id: str
    target_price: float
    stop_loss_price: float
    armed: bool
    done: bool


class TickOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    oi: int = 0
    change: float = 0.0
    change_pct: float = 0.0


class DeployRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1, max_length=80)
    broker: str = Field(default="mock", pattern=r"^(mock|zerodha|upstox|angelone|dhan|fyers|icici|5paisa)$")
    mode: str = Field(pattern=r"^(paper|live)$")
    name: str = Field(min_length=1, max_length=80)
    segment: str = "EQUITY"
    exchange: str = "NSE"


class DeployOut(BaseModel):
    deployment_id: str
    strategy_id: str
    algo_id: str
    broker: str
    mode: str
    name: str
    active: bool


class DeploymentOut(BaseModel):
    deployment_id: str
    strategy_id: str
    algo_id: str
    broker: str
    mode: str
    name: str
    segment: str
    exchange: str
    active: bool
    created_at: str
