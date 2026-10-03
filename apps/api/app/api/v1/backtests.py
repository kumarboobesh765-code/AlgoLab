"""Backtest run endpoints.

Runs execute synchronously and persist to `backtest_runs`. The engine reads
stored candles only — if the requested range has no local history the run is
rejected with a clear message instead of silently fetching provider data.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.backtest import BacktestError
from app.backtest.engine import BacktestConfig
from app.backtest.options_engine import OptionsBacktestError
from app.backtest.validation import (
    ValidationError,
    run_split_backtest,
    to_payload,
)
from app.core.deps import CurrentUser, DbSession
from app.models import BacktestRun, Strategy
from app.quant.schema import StrategyDefinition
from app.schemas.backtest import (
    BacktestRunDetail,
    BacktestRunOut,
    BacktestRunRequest,
    ValidationRequest,
    ValidationResponse,
)
from app.services.backtest_runner import execute_backtest
from app.services.candles import load_candles

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


@router.post("/validate", response_model=ValidationResponse)
async def validate_backtest(
    payload: ValidationRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """In/Out-of-Sample split for a strategy.

    Reports performance on the in-sample segment next to performance on the
    unseen segment, so a user can see whether an edge survives outside the data
    it was built from. Not persisted: it is a read-only analysis of stored
    candles, so it creates no BacktestRun.
    """
    strategy = await _owned_strategy(db, current_user.id, payload.strategy_id)
    if not strategy.definition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Strategy has no definition yet")

    try:
        definition = StrategyDefinition.model_validate(strategy.definition)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Stored definition is invalid: {exc}") from exc

    end_dt = payload.end or date.today(UTC)
    start_dt = payload.start or end_dt - timedelta(days=180)
    if start_dt >= end_dt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "start must be before end")

    start = datetime.combine(start_dt, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(end_dt, datetime.max.time().replace(microsecond=0), tzinfo=UTC)
    candles = await load_candles(
        db, symbol=strategy.underlying, interval=definition.timeframe, start=start, end=end
    )
    if len(candles) < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"No stored {definition.timeframe} candles for {strategy.underlying} in range — "
            "ingest history via Tools → Data Manager first",
        )

    config = BacktestConfig(
        initial_capital=payload.initial_capital,
        costs_pct=payload.costs_pct,
        slippage_pct=payload.slippage_pct,
    )
    try:
        result = run_split_backtest(definition, candles, config, split=payload.split)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except BacktestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    payload_out = to_payload(result)
    payload_out["bars_used"] = len(candles)
    return payload_out


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
