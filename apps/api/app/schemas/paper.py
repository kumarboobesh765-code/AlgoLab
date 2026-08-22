import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaperAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    initial_capital: float = Field(gt=0, le=1_000_000_000)


class PaperAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    initial_capital: float
    cash_balance: float
    status: str
    created_at: datetime


class PaperAccountDetail(PaperAccountOut):
    equity: float
    unrealized_pnl: float
    open_positions: list[dict[str, Any]]
    closed_positions: list[dict[str, Any]]
    recent_orders: list[dict[str, Any]]


class ForwardTestCreate(BaseModel):
    strategy_id: uuid.UUID
    account_id: uuid.UUID


class ForwardTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    account_id: uuid.UUID
    version_number: int
    status: str
    last_bar_time: datetime | None
    pending_action: str | None
    last_message: str | None
    started_at: datetime
    stopped_at: datetime | None
    created_at: datetime


class TickResult(BaseModel):
    run_id: uuid.UUID
    bars_processed: int
    fills: list[dict[str, Any]]
    open_position: dict[str, Any] | None
    message: str | None
