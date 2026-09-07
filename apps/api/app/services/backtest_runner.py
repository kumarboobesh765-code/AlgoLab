"""Shared backtest execution helper — used by both the backtests route and portfolio routes."""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest import BacktestConfig, BacktestError, run_backtest
from app.backtest.options_engine import OptionsBacktestError, run_options_backtest
from app.models import BacktestRun, Strategy
from app.quant.schema import StrategyDefinition
from app.services.candles import load_candles


class StrategyNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "Strategy not found")


async def get_owned_strategy(db: AsyncSession, user_id: uuid.UUID, strategy_id: uuid.UUID) -> Strategy:
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user_id)
    )
    strategy = result.scalars().first()
    if strategy is None:
        raise StrategyNotFoundError()
    return strategy


async def execute_backtest(
    db: AsyncSession,
    user_id: uuid.UUID,
    strategy_id: uuid.UUID,
    start_date: date | None,
    end_date: date | None,
    initial_capital: float,
    costs_pct: float,
    slippage_pct: float,
) -> BacktestRun:
    strategy = await get_owned_strategy(db, user_id, strategy_id)
    if not strategy.definition:
        raise ValueError("Strategy has no definition yet — build one before backtesting")
    try:
        definition = StrategyDefinition.model_validate(strategy.definition)
    except Exception as exc:
        raise ValueError(f"Stored definition is invalid: {exc}") from exc

    end_dt = end_date or date.today(UTC)
    start_dt = start_date or end_dt - timedelta(days=30)
    if start_dt >= end_dt:
        raise ValueError("start must be before end")
    start = datetime.combine(start_dt, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(end_dt, datetime.max.time().replace(microsecond=0), tzinfo=UTC)

    candles = await load_candles(
        db, symbol=strategy.underlying, interval=definition.timeframe, start=start, end=end
    )
    if len(candles) < 2:
        raise ValueError(
            f"No stored {definition.timeframe} candles for {strategy.underlying} in range — "
            "ingest history via Tools → Data Manager first"
        )

    run = BacktestRun(
        strategy_id=strategy.id,
        user_id=user_id,
        version_number=strategy.current_version,
        status="running",
        config={
            "symbol": strategy.underlying,
            "timeframe": definition.timeframe,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "initial_capital": initial_capital,
            "costs_pct": costs_pct,
            "slippage_pct": slippage_pct,
            "bars": len(candles),
        },
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    try:
        if definition.builder == "legs" and definition.legs:
            result = run_options_backtest(
                definition,
                candles,
                initial_capital=initial_capital,
                costs_pct=costs_pct,
            )
        else:
            result = run_backtest(
                definition,
                candles,
                BacktestConfig(
                    initial_capital=initial_capital,
                    costs_pct=costs_pct,
                    slippage_pct=slippage_pct,
                ),
            )
    except (BacktestError, OptionsBacktestError) as exc:
        run.status = "failed"
        run.result_summary = {"error": str(exc)}
        run.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(run)
        raise

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
