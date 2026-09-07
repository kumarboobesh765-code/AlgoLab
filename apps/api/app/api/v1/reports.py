"""Reporting endpoints: Monte Carlo drawdown, daily P&L, portfolio summary."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.backtest.drawdown_mc import bootstrap_monte_carlo
from app.core.deps import CurrentUser, DbSession
from app.models import BacktestRun
from app.schemas.report import DailyPnlResponse, DrawdownMCRequest, DrawdownMCResponse

router = APIRouter(prefix="/reports", tags=["reports"])


async def _owned_run(db: DbSession, user_id: uuid.UUID, run_id: uuid.UUID) -> BacktestRun:
    result = await db.execute(
        select(BacktestRun).where(
            BacktestRun.id == run_id, BacktestRun.user_id == user_id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backtest run not found")
    return run


@router.post("/drawdown-mc", response_model=DrawdownMCResponse, status_code=status.HTTP_200_OK)
async def compute_drawdown_mc(
    payload: DrawdownMCRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> DrawdownMCResponse:
    run = await _owned_run(db, current_user.id, payload.run_id)
    if run.status != "completed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Run is not completed")
    if not run.result_summary:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run has no results")

    equity_curve = run.result_summary.get("equity_curve", [])
    if not equity_curve:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run has no equity curve")

    result = bootstrap_monte_carlo(
        equity_curve=equity_curve,
        n_runs=payload.n_runs,
    )
    return DrawdownMCResponse(**result)


@router.get("/daily-pnl", response_model=DailyPnlResponse)
async def get_daily_pnl(
    db: DbSession,
    current_user: CurrentUser,
    strategy_ids: str = Query(default="", description="Comma-separated strategy UUIDs"),
    start: date | None = None,
    end: date | None = None,
) -> DailyPnlResponse:
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.user_id == current_user.id, BacktestRun.status == "completed")
        .where(BacktestRun.result_summary.isnot(None))
    )
    if strategy_ids:
        ids = [uuid.UUID(s.strip()) for s in strategy_ids.split(",") if s.strip()]
        stmt = stmt.where(BacktestRun.strategy_id.in_(ids))

    runs_result = await db.execute(stmt)
    runs = list(runs_result.scalars().all())

    daily_pnl: dict[str, list[float]] = {}
    for run in runs:
        trades = run.result_summary.get("trades", []) if run.result_summary else []
        for trade in trades:
            exit_time_str = trade.get("exit_time")
            if not exit_time_str:
                continue
            try:
                exit_dt = datetime.fromisoformat(exit_time_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                exit_dt = datetime.fromisoformat(exit_time_str)
            day = exit_dt.date()
            if start and day < start:
                continue
            if end and day > end:
                continue
            pnl = trade.get("pnl", 0) or 0
            daily_pnl.setdefault(day.isoformat(), []).append(pnl)

    points = []
    cumulative = 0.0
    total_trades = 0
    winning_days = 0
    losing_days = 0
    for day, pnls in sorted(daily_pnl.items()):
        day_pnl = sum(pnls)
        cumulative += day_pnl
        total_trades += len(pnls)
        points.append({"date": day, "pnl": round(day_pnl, 2), "cumulative": round(cumulative, 2)})
        if day_pnl > 0:
            winning_days += 1
        elif day_pnl < 0:
            losing_days += 1

    return DailyPnlResponse(
        points=points,
        total_pnl=round(cumulative, 2),
        total_trades=total_trades,
        winning_days=winning_days,
        losing_days=losing_days,
    )


@router.get("/portfolio-summary")
async def get_portfolio_summary(
    db: DbSession,
    current_user: CurrentUser,
    strategy_ids: str = Query(default="", description="Comma-separated strategy UUIDs"),
) -> dict:
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.user_id == current_user.id, BacktestRun.status == "completed")
        .where(BacktestRun.result_summary.isnot(None))
    )
    if strategy_ids:
        ids = [uuid.UUID(s.strip()) for s in strategy_ids.split(",") if s.strip()]
        stmt = stmt.where(BacktestRun.strategy_id.in_(ids))

    runs_result = await db.execute(stmt)
    runs = list(runs_result.scalars().all())

    if not runs:
        return {
            "total_strategies": 0,
            "total_runs": 0,
            "total_trades": 0,
            "net_pnl": 0.0,
            "avg_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.0,
        }

    total_trades = 0
    wins = 0
    losses = 0
    net_pnl = 0.0
    max_drawdown = 0.0
    returns: list[float] = []

    for run in runs:
        summary = run.result_summary.get("summary", {}) if run.result_summary else {}
        trades = run.result_summary.get("trades", []) if run.result_summary else []
        total_trades += len(trades)
        wins += sum(1 for t in trades if (t.get("pnl") or 0) > 0)
        losses += sum(1 for t in trades if (t.get("pnl") or 0) <= 0)
        net_pnl += summary.get("net_pnl", 0) or 0
        max_drawdown = max(max_drawdown, summary.get("max_drawdown_pct", 0) or 0)
        if summary.get("return_pct"):
            returns.append(summary["return_pct"])

    return {
        "total_strategies": len({r.strategy_id for r in runs}),
        "total_runs": len(runs),
        "total_trades": total_trades,
        "net_pnl": round(net_pnl, 2),
        "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
        "max_drawdown_pct": round(max_drawdown, 2),
        "sharpe_ratio": round(sum(r.get("sharpe_ratio", 0) or 0 for r in [run.result_summary.get("summary", {}) if run.result_summary else {} for run in runs]) / len(runs), 2) if runs else 0.0,
        "win_rate": round((wins / total_trades) * 100, 2) if total_trades else 0.0,
    }
