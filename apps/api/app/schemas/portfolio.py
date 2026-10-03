from datetime import date
from typing import Any, Literal

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


class SubsetCandidate(BaseModel):
    rank: int
    run_ids: list[str]
    strategy_names: list[str]
    metrics: dict[str, Any]


class SubsetOptimiseRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=60)
    size: int | None = Field(default=None, ge=1, le=12)
    objective: Literal["sharpe_ratio", "return_pct", "calmar"] = "sharpe_ratio"
    top_n: int = Field(default=5, ge=1, le=20)


class SubsetOptimiseOut(BaseModel):
    objective: str
    exhaustive: bool
    subset_size: int
    candidates_considered: int
    combinations_possible: int = 0
    best: SubsetCandidate | None
    runners_up: list[SubsetCandidate]
    single_best: SubsetCandidate | None
    note: str | None


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
