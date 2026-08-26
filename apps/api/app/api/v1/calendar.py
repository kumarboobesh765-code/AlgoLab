"""Market calendar + Indian transaction cost + expiry/lot-size endpoints."""

from datetime import date
from datetime import datetime as _dt

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.market_calendar import (
    FREEZE_QTY,
    LOT_SIZES,
    WEEKLY_EXPIRY_INDICES,
    holidays_in_range,
    total_trade_cost,
    upcoming_expiries,
    validate_order_quantity,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


class HolidayOut(BaseModel):
    date: str
    weekday: str


class HolidaysResponse(BaseModel):
    holidays: list[HolidayOut]
    count: int


class CostRequest(BaseModel):
    buy_value: float = Field(gt=0, description="Buy-side traded value in INR")
    sell_value: float = Field(gt=0, description="Sell-side traded value in INR")
    brokerage_per_order: float = Field(default=20.0, ge=0)
    segment: str = Field(default="equity", pattern="^(equity|futures|options)$")
    product: str = Field(default="delivery", pattern="^(delivery|intraday|futures|options)$")


class CostResponse(BaseModel):
    breakdown: dict[str, float]
    total: float
    cost_pct_of_turnover: float


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@router.get("/holidays", response_model=HolidaysResponse)
async def list_holidays(
    year: int | None = None,
    start: str | None = None,
    end: str | None = None,
    user: CurrentUser = None,
) -> HolidaysResponse:
    """List NSE trading holidays, optionally filtered by year or date range."""
    if start and end:
        s = _dt.strptime(start, "%Y-%m-%d").date()
        e = _dt.strptime(end, "%Y-%m-%d").date()
        days = holidays_in_range(s, e)
    elif year:
        s = date(year, 1, 1)
        e = date(year, 12, 31)
        days = holidays_in_range(s, e)
    else:
        s = date(date.today().year, 1, 1)
        e = date(date.today().year + 1, 12, 31)
        days = holidays_in_range(s, e)

    return HolidaysResponse(
        holidays=[HolidayOut(date=d.isoformat(), weekday=WEEKDAYS[d.weekday()]) for d in days],
        count=len(days),
    )


@router.post("/costs", response_model=CostResponse)
async def calc_costs(payload: CostRequest, user: CurrentUser = None) -> CostResponse:
    """Compute a full Indian-market transaction cost breakdown."""
    b = total_trade_cost(
        buy_value=payload.buy_value,
        sell_value=payload.sell_value,
        brokerage_per_order=payload.brokerage_per_order,
        segment=payload.segment,
        product=payload.product,
    )
    turnover = payload.buy_value + payload.sell_value
    return CostResponse(
        breakdown=b,
        total=b["total"],
        cost_pct_of_turnover=round(b["total"] / turnover * 100, 4) if turnover else 0.0,
    )


class ExpiryOut(BaseModel):
    symbol: str
    expiries: list[str]
    weekly: bool
    lot_size: int
    freeze_qty: int | None


@router.get("/expiries", response_model=ExpiryOut)
async def get_expiries(
    symbol: str = "NIFTY",
    count: int = Query(default=4, ge=1, le=12),
    user: CurrentUser = None,
) -> ExpiryOut:
    """Upcoming F&O expiry dates for an index (holiday-adjusted)."""
    sym = symbol.upper()
    days = upcoming_expiries(sym, date.today(), count)
    return ExpiryOut(
        symbol=sym,
        expiries=[d.isoformat() for d in days],
        weekly=sym in WEEKLY_EXPIRY_INDICES,
        lot_size=LOT_SIZES.get(sym, 1),
        freeze_qty=FREEZE_QTY.get(sym),
    )


class QuantityCheckRequest(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)


class QuantityCheckResponse(BaseModel):
    valid: bool
    issues: list[str]


@router.post("/validate-quantity", response_model=QuantityCheckResponse)
async def check_quantity(payload: QuantityCheckRequest, user: CurrentUser = None) -> QuantityCheckResponse:
    """Validate an order quantity against lot size and freeze limits."""
    issues = validate_order_quantity(payload.symbol, payload.quantity)
    return QuantityCheckResponse(valid=not issues, issues=issues)
