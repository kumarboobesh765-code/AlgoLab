import uuid

from pydantic import BaseModel, Field


class DrawdownMCRequest(BaseModel):
    run_id: uuid.UUID
    n_runs: int = Field(default=1000, ge=100, le=10000)


class DrawdownMCResponse(BaseModel):
    equity_curve: list[dict]
    drawdown_curve: list[dict]
    peak_equity: float
    trough_equity: float
    max_drawdown_pct: float
    mc_runs: int
    mc_stats: dict


class DailyPnlResponse(BaseModel):
    points: list[dict]
    total_pnl: float
    total_trades: int
    winning_days: int
    losing_days: int
