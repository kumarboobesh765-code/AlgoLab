import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BacktestRunRequest(BaseModel):
    strategy_id: uuid.UUID
    start: date | None = None
    end: date | None = None
    initial_capital: float = Field(default=100_000.0, gt=0, le=100_000_000_000)
    costs_pct: float = Field(default=0.03, ge=0, le=5)
    slippage_pct: float = Field(default=0.0, ge=0, le=5)


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    version_number: int
    status: str
    config: dict[str, Any] | None
    result_summary: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class BacktestRunDetail(BacktestRunOut):
    """Full run including trades and equity curve (stored in result_summary)."""


class ValidationRequest(BaseModel):
    """In/Out-of-Sample split request.

    Defaults to 180 days of history: an OOS leg that is too short produces a
    number that looks authoritative and means nothing.
    """

    strategy_id: uuid.UUID
    start: date | None = None
    end: date | None = None
    split: float = Field(default=0.7, ge=0.1, le=0.9)
    initial_capital: float = Field(default=100_000.0, gt=0, le=100_000_000_000)
    costs_pct: float = Field(default=0.03, ge=0, le=5)
    slippage_pct: float = Field(default=0.0, ge=0, le=5)


class ValidationWindow(BaseModel):
    start: str
    end: str
    summary: dict[str, Any]


class ValidationResponse(BaseModel):
    split_index: int
    split_time: str
    warmup_bars: int
    bars_used: int
    windows: dict[str, ValidationWindow]
    degradation: dict[str, Any]
