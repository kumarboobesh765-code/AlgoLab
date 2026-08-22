import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OptimizationCreate(BaseModel):
    strategy_id: uuid.UUID
    method: str = Field(pattern="^(grid|walk_forward)$")
    param_ranges: dict[str, list[Any]]
    start: datetime
    end: datetime
    train_pct: float = Field(default=0.7, gt=0.3, lt=0.9)
    target_metric: str = Field(default="sharpe_ratio")
    initial_capital: float = Field(default=100_000, gt=0)
    costs_pct: float = Field(default=0.03, ge=0, le=5)


class OptimizationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    method: str
    param_ranges: dict
    start: datetime
    end: datetime
    train_pct: float
    target_metric: str
    status: str
    total_combinations: int
    completed_combinations: int
    best_params: dict | None
    best_metrics: dict | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class OptimizationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    rank: int | None
    params: dict
    net_pnl: float | None
    return_pct: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    total_trades: int | None
    train_sharpe: float | None
    test_sharpe: float | None
    status: str
    error: str | None
    created_at: datetime
