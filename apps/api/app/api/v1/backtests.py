"""Backtest run endpoints.

Runs execute synchronously and persist to `backtest_runs`. The engine reads
stored candles only — if the requested range has no local history the run is
rejected with a clear message instead of silently fetching provider data.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.backtest import BacktestError
from app.backtest.options_engine import OptionsBacktestError
from app.core.deps import CurrentUser, DbSession
from app.models import BacktestRun, Strategy
from app.schemas.backtest import BacktestRunDetail, BacktestRunOut, BacktestRunRequest
from app.services.backtest_runner import execute_backtest

router = APIRouter(prefix="/backtests", tags=["backtests"])


async def _owned_strategy(db: DbSession, user_id: uuid.UUID, strategy_id: uuid.UUID) -> Strategy:
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user_id)
    )
    strategy = result.scalars().first()
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    return strategy


@router.post("", response_model=BacktestRunDetail, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    payload: BacktestRunRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> BacktestRun:
    try:
        return await execute_backtest(
            db,
            current_user.id,
            payload.strategy_id,
            payload.start,
            payload.end,
            payload.initial_capital,
            payload.costs_pct,
            payload.slippage_pct,
        )
    except (BacktestError, OptionsBacktestError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Backtest engine failed"
        ) from exc


@router.get("", response_model=list[BacktestRunOut])
async def list_backtests(
    db: DbSession,
    current_user: CurrentUser,
    strategy_id: uuid.UUID | None = None,
    limit: int = Query(default=50, le=200),
) -> list[BacktestRun]:
    stmt = select(BacktestRun).where(BacktestRun.user_id == current_user.id)
    if strategy_id is not None:
        stmt = stmt.where(BacktestRun.strategy_id == strategy_id)
    stmt = stmt.order_by(BacktestRun.created_at.desc()).limit(limit)
    runs = (await db.execute(stmt)).scalars().all()
    return list(runs)


@router.get("/{run_id}/candles")
async def get_backtest_candles(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[dict]:
    """Stored candles exactly as the engine consumed them (for trade replay)."""
    from datetime import UTC, date, datetime

    result = await db.execute(
        select(BacktestRun).where(
            BacktestRun.id == run_id, BacktestRun.user_id == current_user.id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backtest run not found")
    cfg = run.config or {}
    try:
        start = datetime.combine(date.fromisoformat(str(cfg["start"])), datetime.min.time(), tzinfo=UTC)
        end_dt = datetime.combine(
            date.fromisoformat(str(cfg["end"])), datetime.max.time().replace(microsecond=0), tzinfo=UTC
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Run has no valid candle range in config"
        ) from exc
    from app.services.candles import load_candles

    candles = await load_candles(
        db,
        symbol=str(cfg["symbol"]),
        interval=str(cfg["timeframe"]),
        start=start,
        end=end_dt,
    )
    return [
        {
            "timestamp": c.timestamp.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]


@router.get("/{run_id}", response_model=BacktestRunDetail)
async def get_backtest(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> BacktestRun:
    result = await db.execute(
        select(BacktestRun).where(
            BacktestRun.id == run_id, BacktestRun.user_id == current_user.id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backtest run not found")
    return run


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backtest(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    result = await db.execute(
        select(BacktestRun).where(
            BacktestRun.id == run_id, BacktestRun.user_id == current_user.id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backtest run not found")
    if run.status == "running":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot delete a run that is still executing"
        )
    await db.delete(run)
    await db.commit()
