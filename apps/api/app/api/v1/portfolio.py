"""Portfolio backtest endpoints (Milestone C).

Combines multiple per-strategy backtests into a single equity curve + summary,
and exposes daily P&L aggregation across completed runs.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.backtest import BacktestResult, Trade
from app.backtest.portfolio_engine import PortfolioInput, combine
from app.core.deps import CurrentUser, DbSession
from app.models import BacktestRun, Strategy
from app.schemas.portfolio import (
    BacktestMini,
    CombineOut,
    DailyPnlOut,
    DailyPnlPoint,
    PortfolioBacktestOut,
    PortfolioBacktestRequest,
)
from app.services.backtest_runner import execute_backtest

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _require_whitelisted_ip(request: Request) -> None:
    """Reuse execution IP guard for portfolio composition endpoints."""
    from app.api.v1.execution import _require_whitelisted_ip as guard

    guard(request)


def _summary_payload(run: BacktestRun) -> dict | None:
    if not run.result_summary:
        return None
    return run.result_summary.get("summary")


def _equity_curve_payload(run: BacktestRun) -> list[dict]:
    if not run.result_summary:
        return []
    return list(run.result_summary.get("equity_curve", []))


def _trades_payload(run: BacktestRun) -> list[dict]:
    if not run.result_summary:
        return []
    return list(run.result_summary.get("trades", []))


def _to_mini(run: BacktestRun, strategy_name: str) -> BacktestMini:
    return BacktestMini(
        run_id=str(run.id),
        strategy_id=str(run.strategy_id),
        strategy_name=strategy_name,
        status=run.status,
        summary=_summary_payload(run),
        equity_curve=_equity_curve_payload(run),
    )


def _run_to_backtest_result(run: BacktestRun) -> BacktestResult:
    """Hydrate a BacktestResult from a persisted BacktestRun row."""
    trades: list[Trade] = []
    for t in _trades_payload(run):
        trades.append(
            Trade(
                direction=t.get("direction", "long"),
                quantity=float(t.get("quantity", 0)),
                entry_time=t.get("entry_time"),
                entry_price=float(t.get("entry_price", 0)),
                exit_time=t.get("exit_time"),
                exit_price=float(t.get("exit_price", 0)),
                exit_reason=t.get("exit_reason", "signal"),
                pnl=float(t.get("pnl", 0)),
                pnl_pct=float(t.get("pnl_pct", 0)),
                bars_held=int(t.get("bars_held", 0)),
            )
        )
    return BacktestResult(
        trades=trades,
        equity_curve=_equity_curve_payload(run),
        summary=_summary_payload(run) or {},
    )


async def _resolve_strategies(
    db: DbSession, user_id: uuid.UUID, strategy_ids: Iterable[str]
) -> list[Strategy]:
    parsed: list[uuid.UUID] = []
    for sid in strategy_ids:
        try:
            parsed.append(uuid.UUID(sid))
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Invalid strategy_id: {sid}"
            ) from exc
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == user_id, Strategy.id.in_(parsed))
    )
    found = {s.id: s for s in result.scalars().all()}
    missing = [str(sid) for sid in parsed if sid not in found]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Strategies not found: {', '.join(missing)}"
        )
    return [found[sid] for sid in parsed]


@router.post("/backtest", response_model=PortfolioBacktestOut)
async def run_portfolio_backtest(
    payload: PortfolioBacktestRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> PortfolioBacktestOut:
    _require_whitelisted_ip(request)
    if not payload.strategy_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "strategy_ids cannot be empty")

    strategies = _resolve_strategies(db, current_user.id, payload.strategy_ids)

    minis: list[BacktestMini] = []
    inputs: list[PortfolioInput] = []
    error: str | None = None

    for strat in strategies:
        try:
            run = await execute_backtest(
                db,
                current_user.id,
                strat.id,
                payload.start,
                payload.end,
                payload.initial_capital,
                payload.costs_pct,
                0.0,
            )
        except Exception as exc:
            error = f"{strat.name}: {exc}"
            minis.append(
                BacktestMini(
                    run_id="",
                    strategy_id=str(strat.id),
                    strategy_name=strat.name,
                    status="failed",
                    summary=None,
                    equity_curve=[],
                )
            )
            continue

        cfg = run.config or {}
        init_cap = float(cfg.get("initial_capital", payload.initial_capital))
        minis.append(_to_mini(run, strat.name))
        if run.status == "completed":
            inputs.append(
                PortfolioInput(
                    strategy_id=str(strat.id),
                    strategy_name=strat.name,
                    initial_capital=init_cap,
                    result=_run_to_backtest_result(run),
                )
            )

    combined_curve, combined_summary = combine(inputs)
    return PortfolioBacktestOut(
        runs=minis,
        combined_equity_curve=combined_curve,
        combined_summary=combined_summary,
        error=error,
    )


@router.get("/combine", response_model=CombineOut)
async def combine_runs(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    run_ids: str = Query(..., description="Comma-separated list of run IDs"),
) -> CombineOut:
    _require_whitelisted_ip(request)
    parsed: list[uuid.UUID] = []
    for rid in run_ids.split(","):
        rid = rid.strip()
        if not rid:
            continue
        try:
            parsed.append(uuid.UUID(rid))
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Invalid run_id: {rid}"
            ) from exc
    if not parsed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "run_ids cannot be empty")

    result = await db.execute(
        select(BacktestRun, Strategy.name)
        .join(Strategy, Strategy.id == BacktestRun.strategy_id)
        .where(BacktestRun.id.in_(parsed), BacktestRun.user_id == current_user.id)
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No matching runs found")

    minis: list[BacktestMini] = []
    inputs: list[PortfolioInput] = []
    for run, strat_name in rows:
        minis.append(_to_mini(run, strat_name))
        if run.status == "completed":
            cfg = run.config or {}
            init_cap = float(cfg.get("initial_capital", 0.0))
            inputs.append(
                PortfolioInput(
                    strategy_id=str(run.strategy_id),
                    strategy_name=strat_name,
                    initial_capital=init_cap,
                    result=_run_to_backtest_result(run),
                )
            )

    combined_curve, combined_summary = combine(inputs)
    return CombineOut(
        runs=minis,
        combined_equity_curve=combined_curve,
        combined_summary=combined_summary,
        error=None,
    )


@router.get("/daily-pnl", response_model=DailyPnlOut)
async def daily_pnl(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    strategy_ids: str | None = Query(default=None, description="Comma-separated strategy IDs"),
    start: date | None = None,
    end: date | None = None,
) -> DailyPnlOut:
    _require_whitelisted_ip(request)
    stmt = select(BacktestRun).where(
        BacktestRun.user_id == current_user.id, BacktestRun.status == "completed"
    )
    if strategy_ids:
        try:
            parsed = [uuid.UUID(s.strip()) for s in strategy_ids.split(",") if s.strip()]
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Invalid strategy_ids: {strategy_ids}"
            ) from exc
        if parsed:
            stmt = stmt.where(BacktestRun.strategy_id.in_(parsed))
    runs = (await db.execute(stmt)).scalars().all()

    buckets: dict[str, float] = defaultdict(float)
    for run in runs:
        cfg = run.config or {}
        run_start = cfg.get("start")
        run_end = cfg.get("end")
        for t in _trades_payload(run):
            exit_time = t.get("exit_time")
            if not exit_time:
                continue
            try:
                dt = datetime.fromisoformat(str(exit_time).replace("Z", "+00:00"))
            except ValueError:
                continue
            d = dt.date()
            if start and d < start:
                continue
            if end and d > end:
                continue
            if run_start:
                try:
                    rs = date.fromisoformat(str(run_start))
                    if d < rs:
                        continue
                except ValueError:
                    pass
            if run_end:
                try:
                    re_ = date.fromisoformat(str(run_end))
                    if d > re_:
                        continue
                except ValueError:
                    pass
            buckets[d.isoformat()] += float(t.get("pnl", 0))

    points: list[DailyPnlPoint] = []
    cumulative = 0.0
    for d in sorted(buckets.keys()):
        cumulative += buckets[d]
        points.append(DailyPnlPoint(date=d, pnl=round(buckets[d], 2), cumulative=round(cumulative, 2)))

    return DailyPnlOut(points=points, error=None)
