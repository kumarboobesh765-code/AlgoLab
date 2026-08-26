"""Optimization runs and results (grid search, walk-forward)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class OptimizationRun(Base):
    """A parameter sweep over a strategy definition's configurable values."""

    __tablename__ = "optimization_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Config
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # grid | walk_forward
    param_ranges: Mapped[dict] = mapped_column(JSONType, nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)  # {initial_capital}
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    train_pct: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    target_metric: Mapped[str] = mapped_column(String(30), default="sharpe_ratio", nullable=False)
    costs_pct: Mapped[float] = mapped_column(Float, default=0.03, nullable=False)
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    total_combinations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_combinations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Summary
    best_params: Mapped[dict | None] = mapped_column(JSONType)
    best_metrics: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(String(500))
    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OptimizationResult(Base):
    """One row per parameter combination tested."""

    __tablename__ = "optimization_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("optimization_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    # The parameter combination
    params: Mapped[dict] = mapped_column(JSONType, nullable=False)
    # Backtest metrics
    net_pnl: Mapped[float | None] = mapped_column(Float)
    return_pct: Mapped[float | None] = mapped_column(Float)
    win_rate: Mapped[float | None] = mapped_column(Float)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float)
    total_trades: Mapped[int | None] = mapped_column(Integer)
    # Walk-forward: separate train/test metrics
    train_sharpe: Mapped[float | None] = mapped_column(Float)
    test_sharpe: Mapped[float | None] = mapped_column(Float)
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
