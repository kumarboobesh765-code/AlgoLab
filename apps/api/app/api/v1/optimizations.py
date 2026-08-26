"""Optimization endpoints — grid search and walk-forward analysis.

POST /optimizations runs synchronously by default (fine at research scale).
Pass ?background=true to get an immediate 202 with the queued run; poll
GET /optimizations/{id} until status leaves 'running'.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import OptimizationResult, OptimizationRun, Strategy
from app.optimizer import OptConfig, generate_param_grid, run_grid_search, run_heatmap, run_walk_forward
from app.quant.schema import StrategyDefinition
from app.schemas.optimization import (
    HeatmapCell,
    HeatmapCreate,
    HeatmapResponse,
    OptimizationCreate,
    OptimizationResultOut,
    OptimizationRunOut,
)
from app.services.candles import load_candles

router = APIRouter(prefix="/optimizations", tags=["optimizations"])


async def _execute_run(run_id: uuid.UUID, session_factory=None) -> None:
    """Background executor: loads its own session, computes, persists results.

    `session_factory` is injectable for tests; production uses the app engine.
    """
    from app.db.session import get_session_factory

    factory = session_factory or get_session_factory()
    async with factory() as db:
        result = await db.execute(select(OptimizationRun).where(OptimizationRun.id == run_id))
        run = result.scalars().first()
        if run is None or run.status not in ("queued", "running"):
            return

        strategy_result = await db.execute(select(Strategy).where(Strategy.id == run.strategy_id))
        strategy = strategy_result.scalars().first()
        try:
            if strategy is None or not strategy.definition:
                raise RuntimeError("Strategy missing or has no definition")
            definition = StrategyDefinition.model_validate(strategy.definition)
            candles = await load_candles(
                db, symbol=strategy.underlying, interval=definition.timeframe,
                start=run.start, end=run.end,
            )
            if len(candles) < 20:
                raise RuntimeError(f"Not enough candles ({len(candles)})")

            cfg = OptConfig(
                initial_capital=float((run.config or {}).get("initial_capital", 100_000)),
                costs_pct=run.costs_pct,
                target_metric=run.target_metric,
                train_pct=run.train_pct,
            )
            if run.method == "grid":
                results = run_grid_search(definition, candles, run.param_ranges, cfg)
            else:
                results = run_walk_forward(definition, candles, run.param_ranges, cfg)

            run.completed_combinations = len(results)
            run.status = "completed"
            run.finished_at = datetime.now(UTC)

            best = None
            for i, r in enumerate(results):
                db.add(OptimizationResult(
                    run_id=run.id,
                    rank=i + 1,
                    params=r.params,
                    net_pnl=r.net_pnl,
                    return_pct=r.return_pct,
                    win_rate=r.win_rate,
                    profit_factor=r.profit_factor,
                    max_drawdown_pct=r.max_drawdown_pct,
                    sharpe_ratio=r.sharpe_ratio,
                    total_trades=r.total_trades,
                    train_sharpe=r.train_sharpe,
                    test_sharpe=r.test_sharpe,
                    status=r.status,
                    error=r.error,
                ))
                if i == 0 and r.status == "completed":
                    best = r
            if best is not None:
                run.best_params = best.params
                run.best_metrics = best.as_dict()

        except Exception as exc:
            await db.rollback()
            await db.refresh(run)
            run.status = "failed"
            run.error = str(exc)[:500]
            run.finished_at = datetime.now(UTC)

        await db.commit()


async def _owned_strategy(db: DbSession, user_id: uuid.UUID, strategy_id: uuid.UUID) -> Strategy:
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user_id)
    )
    strategy = result.scalars().first()
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    if not strategy.definition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Strategy has no definition")
    return strategy


@router.post("", response_model=OptimizationRunOut, status_code=status.HTTP_201_CREATED)
async def create_optimization(
    payload: OptimizationCreate,
    background: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    run_in_background: bool = Query(default=False, alias="background"),
):
    strategy = await _owned_strategy(db, current_user.id, payload.strategy_id)
    definition = StrategyDefinition.model_validate(strategy.definition)

    grid = generate_param_grid(payload.param_ranges)
    if len(grid) > 500:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Too many combinations ({len(grid)}). Max 500. Reduce ranges.",
        )

    candles = await load_candles(
        db, symbol=strategy.underlying, interval=definition.timeframe,
        start=payload.start, end=payload.end,
    )
    if len(candles) < 20:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Not enough candles ({len(candles)}) for optimization. Ingest more data.",
        )

    run = OptimizationRun(
        user_id=current_user.id,
        strategy_id=strategy.id,
        method=payload.method,
        param_ranges=payload.param_ranges,
        config={"initial_capital": payload.initial_capital},
        start=payload.start,
        end=payload.end,
        train_pct=payload.train_pct,
        target_metric=payload.target_metric,
        costs_pct=payload.costs_pct,
        status="running" if not run_in_background else "queued",
        total_combinations=len(grid),
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if run_in_background:
        background.add_task(_execute_run, run.id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=OptimizationRunOut.model_validate(run).model_dump(mode="json"),
        )

    # Run synchronously (up to 500 combos — fast enough at research scale).
    try:
        cfg = OptConfig(
            initial_capital=payload.initial_capital,
            costs_pct=payload.costs_pct,
            target_metric=payload.target_metric,
            train_pct=payload.train_pct,
        )
        if payload.method == "grid":
            results = run_grid_search(definition, candles, payload.param_ranges, cfg)
        else:
            results = run_walk_forward(definition, candles, payload.param_ranges, cfg)

        run.completed_combinations = len(results)
        run.status = "completed"
        run.finished_at = datetime.now(UTC)

        best = None
        for i, r in enumerate(results):
            db.add(OptimizationResult(
                run_id=run.id,
                rank=i + 1,
                params=r.params,
                net_pnl=r.net_pnl,
                return_pct=r.return_pct,
                win_rate=r.win_rate,
                profit_factor=r.profit_factor,
                max_drawdown_pct=r.max_drawdown_pct,
                sharpe_ratio=r.sharpe_ratio,
                total_trades=r.total_trades,
                train_sharpe=r.train_sharpe,
                test_sharpe=r.test_sharpe,
                status=r.status,
                error=r.error,
            ))
            if i == 0 and r.status == "completed":
                best = r

        if best is not None:
            run.best_params = best.params
            run.best_metrics = best.as_dict()

    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:500]
        run.finished_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(run)
    return run


@router.post("/heatmap", response_model=HeatmapResponse)
async def create_heatmap(
    payload: HeatmapCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> HeatmapResponse:
    """2D parameter sensitivity surface — ephemeral, not persisted."""
    strategy = await _owned_strategy(db, current_user.id, payload.strategy_id)
    definition = StrategyDefinition.model_validate(strategy.definition)

    if len(payload.x_values) * len(payload.y_values) > 625:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Heatmap too large: max 25x25 combinations",
        )

    candles = await load_candles(
        db, symbol=strategy.underlying, interval=definition.timeframe,
        start=payload.start, end=payload.end,
    )
    if len(candles) < 20:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Not enough candles ({len(candles)}). Ingest more data first.",
        )

    cfg = OptConfig(
        initial_capital=payload.initial_capital,
        costs_pct=payload.costs_pct,
        target_metric=payload.metric,
    )
    try:
        points = run_heatmap(
            definition, candles,
            x_key=payload.x_key, x_values=payload.x_values,
            y_key=payload.y_key, y_values=payload.y_values,
            metric=payload.metric, config=cfg,
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    cells = [HeatmapCell(x=p.x, y=p.y, value=p.value, trades=p.trades) for p in points]
    valid = [c for c in cells if c.value is not None]
    best = max(valid, key=lambda c: c.value) if valid else None
    worst = min(valid, key=lambda c: c.value) if valid else None

    return HeatmapResponse(
        x_key=payload.x_key,
        y_key=payload.y_key,
        x_values=sorted(set(payload.x_values)),
        y_values=sorted(set(payload.y_values)),
        metric=payload.metric,
        cells=cells,
        best=best,
        worst=worst,
    )


@router.get("", response_model=list[OptimizationRunOut])
async def list_optimizations(
    db: DbSession,
    current_user: CurrentUser,
    strategy_id: uuid.UUID | None = None,
) -> list[OptimizationRun]:
    stmt = select(OptimizationRun).where(OptimizationRun.user_id == current_user.id)
    if strategy_id is not None:
        stmt = stmt.where(OptimizationRun.strategy_id == strategy_id)
    stmt = stmt.order_by(OptimizationRun.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{run_id}", response_model=OptimizationRunOut)
async def get_optimization(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> OptimizationRun:
    result = await db.execute(
        select(OptimizationRun).where(
            OptimizationRun.id == run_id, OptimizationRun.user_id == current_user.id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Optimization run not found")
    return run


@router.get("/{run_id}/results", response_model=list[OptimizationResultOut])
async def get_optimization_results(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[OptimizationResult]:
    run_result = await db.execute(
        select(OptimizationRun).where(
            OptimizationRun.id == run_id, OptimizationRun.user_id == current_user.id
        )
    )
    run = run_result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Optimization run not found")

    results = await db.execute(
        select(OptimizationResult)
        .where(OptimizationResult.run_id == run_id)
        .order_by(OptimizationResult.rank.asc())
    )
    return list(results.scalars().all())
