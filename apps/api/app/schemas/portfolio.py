from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PortfolioBacktestRequest(BaseModel):
    strategy_ids: list[str]
    start: date
    end: date
    initial_capital: float = Field(default=1_000_000, gt=0)
    costs_pct: float = Field(default=0.05, ge=0, le=5)


class BacktestMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    strategy_id: str
    strategy_name: str
    status: str
    summary: dict[str, Any] | None
    equity_curve: list[dict[str, Any]]


class PortfolioBacktestOut(BaseModel):
    runs: list[BacktestMini]
    combined_equity_curve: list[dict[str, Any]]
    combined_summary: dict[str, Any]
    error: str | None


class CombineRequest(BaseModel):
    run_ids: list[str]


class CombineOut(BaseModel):
    runs: list[BacktestMini]
    combined_equity_curve: list[dict[str, Any]]
    combined_summary: dict[str, Any]
    error: str | None


class DailyPnlRequest(BaseModel):
    strategy_ids: list[str] | None = None
    start: date | None = None
    end: date | None = None


class DailyPnlPoint(BaseModel):
    date: str
    pnl: float
    cumulative: float


class DailyPnlOut(BaseModel):
    points: list[DailyPnlPoint]
    error: str | None
