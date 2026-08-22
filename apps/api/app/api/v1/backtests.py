"""Backtest run endpoints.

Runs execute synchronously and persist to `backtest_runs`. The engine reads
stored candles only — if the requested range has no local history the run is
rejected with a clear message instead of silently fetching provider data.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.backtest import BacktestConfig, BacktestError, run_backtest
from app.core.deps import CurrentUser, DbSession
from app.models import BacktestRun, Strategy
from app.quant.schema import StrategyDefinition
from app.schemas.backtest import BacktestRunDetail, BacktestRunOut, BacktestRunRequest
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
    strategy = await _owned_strategy(db, current_user.id, payload.strategy_id)
    if not strategy.definition:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Strategy has no definition yet — build one before backtesting",
        )
    try:
        definition = StrategyDefinition.model_validate(strategy.definition)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Stored definition is invalid: {exc}"
        ) from exc

    end_dt = payload.end or date.today(UTC)
    start_dt = payload.start or end_dt - timedelta(days=30)
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

    run = BacktestRun(
        strategy_id=strategy.id,
        user_id=current_user.id,
        version_number=strategy.current_version,
        status="running",
        config={
            "symbol": strategy.underlying,
            "timeframe": definition.timeframe,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "initial_capital": payload.initial_capital,
            "costs_pct": payload.costs_pct,
            "bars": len(candles),
        },
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    try:
        result = run_backtest(
            definition,
            candles,
            BacktestConfig(initial_capital=payload.initial_capital, costs_pct=payload.costs_pct),
        )
    except BacktestError as exc:
        run.status = "failed"
        run.result_summary = {"error": str(exc)}
        run.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(run)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        run.status = "failed"
        run.result_summary = {"error": f"engine failure: {exc}"}
        run.finished_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Backtest engine failed"
        ) from exc

    run.status = "completed"
    run.result_summary = {
        "summary": result.summary,
        "equity_curve": result.equity_curve,
        "trades": [t.as_dict() for t in result.trades],
    }
    run.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(run)
    return run


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
