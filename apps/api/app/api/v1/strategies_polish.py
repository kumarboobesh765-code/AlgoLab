"""Strategy polish endpoints: report, import/export, templates, version comparison."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from starlette.responses import HTMLResponse

from app.core.deps import CurrentUser, DbSession
from app.models import BacktestRun, OptimizationRun, Strategy, StrategyVersion
from app.quant.schema import StrategyDefinition
from app.templates import get_templates

router = APIRouter()


class StrategyExport(BaseModel):
    name: str
    description: str | None = None
    exchange: str
    underlying: str
    instrument: str
    strategy_type: str
    tags: list[str]
    definition: dict | None


class StrategyImport(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    exchange: str = "NSE"
    underlying: str = "NIFTY"
    instrument: str = "options"
    strategy_type: str = "intraday"
    tags: list[str] = Field(default_factory=list)
    definition: dict


class CompareResult(BaseModel):
    v1_version: int
    v2_version: int
    v1_definition: dict | None
    v2_definition: dict | None
    v1_backtest: dict | None
    v2_backtest: dict | None
    v1_created: str
    v2_created: str


async def _owned_strategy(db: DbSession, user_id: uuid.UUID, strategy_id: uuid.UUID) -> Strategy:
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user_id)
    )
    strategy = result.scalars().first()
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    return strategy


@router.get("/templates")
async def list_templates():
    return get_templates()


@router.get("/strategies/{strategy_id}/export", response_model=StrategyExport)
async def export_strategy(
    strategy_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> StrategyExport:
    strategy = await _owned_strategy(db, current_user.id, strategy_id)
    return StrategyExport(
        name=strategy.name,
        description=strategy.description,
        exchange=strategy.exchange,
        underlying=strategy.underlying,
        instrument=strategy.instrument,
        strategy_type=strategy.strategy_type,
        tags=strategy.tags or [],
        definition=strategy.definition,
    )


@router.post("/strategies/import", response_model=StrategyExport, status_code=status.HTTP_201_CREATED)
async def import_strategy(
    payload: StrategyImport,
    db: DbSession,
    current_user: CurrentUser,
) -> StrategyExport:
    if payload.definition is not None:
        try:
            StrategyDefinition.model_validate(payload.definition)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Invalid strategy definition: {exc}",
            ) from exc

    strategy = Strategy(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        exchange=payload.exchange,
        underlying=payload.underlying,
        instrument=payload.instrument,
        strategy_type=payload.strategy_type,
        tags=payload.tags,
        definition=payload.definition,
        status="draft",
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return StrategyExport(
        name=strategy.name,
        description=strategy.description,
        exchange=strategy.exchange,
        underlying=strategy.underlying,
        instrument=strategy.instrument,
        strategy_type=strategy.strategy_type,
        tags=strategy.tags or [],
        definition=strategy.definition,
    )


@router.get("/strategies/{strategy_id}/report")
async def strategy_report(
    strategy_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    strategy = await _owned_strategy(db, current_user.id, strategy_id)

    versions_result = await db.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy.id)
        .order_by(StrategyVersion.version_number.desc())
    )
    versions = versions_result.scalars().all()

    bt_result = await db.execute(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy.id, BacktestRun.status == "completed")
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    latest_backtest = bt_result.scalars().first()

    opt_result = await db.execute(
        select(OptimizationRun)
        .where(OptimizationRun.strategy_id == strategy.id, OptimizationRun.status == "completed")
        .order_by(OptimizationRun.created_at.desc())
        .limit(5)
    )
    optimizations = opt_result.scalars().all()

    bt_count_result = await db.execute(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy.id, BacktestRun.status == "completed")
    )
    total_backtests = len(bt_count_result.scalars().all())

    return {
        "strategy": {
            "id": str(strategy.id),
            "name": strategy.name,
            "status": strategy.status,
            "exchange": strategy.exchange,
            "underlying": strategy.underlying,
            "instrument": strategy.instrument,
            "strategy_type": strategy.strategy_type,
            "tags": strategy.tags or [],
            "current_version": strategy.current_version,
            "has_definition": strategy.definition is not None,
            "created_at": strategy.created_at.isoformat(),
            "updated_at": strategy.updated_at.isoformat(),
        },
        "versions": [
            {
                "version": v.version_number,
                "created_at": v.created_at.isoformat(),
                "changelog": v.changelog,
                "has_definition": v.definition is not None,
            }
            for v in versions
        ],
        "latest_backtest": {
            "id": str(latest_backtest.id),
            "created_at": latest_backtest.created_at.isoformat(),
            "config": latest_backtest.config,
            "summary": latest_backtest.result_summary.get("summary") if latest_backtest.result_summary else None,
            "trades_count": len(latest_backtest.result_summary.get("trades", [])) if latest_backtest.result_summary else 0,
        } if latest_backtest else None,
        "total_backtests": total_backtests,
        "optimizations": [
            {
                "id": str(o.id),
                "method": o.method,
                "target_metric": o.target_metric,
                "total_combinations": o.total_combinations,
                "best_params": o.best_params,
                "best_metrics": o.best_metrics,
                "created_at": o.created_at.isoformat(),
            }
            for o in optimizations
        ],
    }


@router.get("/strategies/{strategy_id}/compare")
async def compare_versions(
    strategy_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    v1: int = Query(..., ge=1),
    v2: int = Query(..., ge=1),
) -> CompareResult:
    strategy = await _owned_strategy(db, current_user.id, strategy_id)

    defn_v1 = await db.execute(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy.id,
            StrategyVersion.version_number == v1,
        )
    )
    version_v1 = defn_v1.scalars().first()

    defn_v2 = await db.execute(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy.id,
            StrategyVersion.version_number == v2,
        )
    )
    version_v2 = defn_v2.scalars().first()

    if version_v1 is None or version_v2 is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

    bt_v1 = await db.execute(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy.id, BacktestRun.version_number == v1, BacktestRun.status == "completed")
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    bt_v2 = await db.execute(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy.id, BacktestRun.version_number == v2, BacktestRun.status == "completed")
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    backtest_v1 = bt_v1.scalars().first()
    backtest_v2 = bt_v2.scalars().first()

    return CompareResult(
        v1_version=v1,
        v2_version=v2,
        v1_definition=version_v1.definition,
        v2_definition=version_v2.definition,
        v1_backtest={
            "summary": backtest_v1.result_summary.get("summary") if backtest_v1 and backtest_v1.result_summary else None,
            "created_at": backtest_v1.created_at.isoformat() if backtest_v1 else None,
        },
        v2_backtest={
            "summary": backtest_v2.result_summary.get("summary") if backtest_v2 and backtest_v2.result_summary else None,
            "created_at": backtest_v2.created_at.isoformat() if backtest_v2 else None,
        },
        v1_created=version_v1.created_at.isoformat(),
        v2_created=version_v2.created_at.isoformat(),
    )


@router.get("/strategies/{strategy_id}/report/pdf")
async def export_strategy_report_pdf(
    strategy_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> HTMLResponse:
    strategy = await _owned_strategy(db, current_user.id, strategy_id)
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy.id)
        .where(BacktestRun.status == "completed")
        .order_by(desc(BacktestRun.finished_at))
        .limit(1)
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    html = build_report_html(strategy, run)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f"attachment; filename=strategy_report_{strategy.name}.html"},
    )


def build_report_html(strategy: Strategy, run: BacktestRun | None) -> str:
    summary = run.result_summary.get("summary", {}) if run and run.result_summary else {}
    net = summary.get("net_pnl", 0) or 0
    ret = summary.get("return_pct", 0) or 0
    wr = summary.get("win_rate", 0) or 0
    tt = summary.get("total_trades", 0) or 0
    pf = summary.get("profit_factor", 0) or 0
    md = summary.get("max_drawdown_pct", 0) or 0
    pos_cls = "positive" if net >= 0 else "negative"
    ret_cls = "positive" if ret >= 0 else "negative"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Strategy Report: {strategy.name}</title>
<style>
  body{{font-family:sans-serif;max-width:800px;margin:0 auto;padding:20px}}
  h1{{color:#1e293b}}h2{{color:#475569;border-bottom:1px solid #e2e8f0;padding-bottom:8px}}
  .metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}}
  .metric{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px}}
  .metric .label{{font-size:11px;color:#64748b;text-transform:uppercase}}
  .metric .value{{font-size:20px;font-weight:700;color:#0f172a}}
  .positive{{color:#059669}}.negative{{color:#dc2626}}
  .footer{{margin-top:40px;font-size:11px;color:#94a3b8;text-align:center}}
</style></head><body>
<h1>{strategy.name}</h1>
<p style="color:#64748b">{strategy.underlying} · {strategy.strategy_type} · v{strategy.current_version}</p>
<h2>Performance Summary</h2>
<div class="metrics">
  <div class="metric"><div class="label">Net P&amp;L</div><div class="value {pos_cls}">{net:,.0f}</div></div>
  <div class="metric"><div class="label">Return %</div><div class="value {ret_cls}">{ret:.2f}%</div></div>
  <div class="metric"><div class="label">Win Rate</div><div class="value">{wr:.1f}%</div></div>
  <div class="metric"><div class="label">Trades</div><div class="value">{tt}</div></div>
  <div class="metric"><div class="label">Profit Factor</div><div class="value">{pf:.2f}</div></div>
  <div class="metric"><div class="label">Max Drawdown</div><div class="value negative">{md:.2f}%</div></div>
</div>
<div class="footer">Generated by StrategyLab · {datetime.now().strftime('%Y-%m-%d %H:%M')} · Backtests are simulations, not financial advice.</div>
</body></html>"""
