"""Tax report endpoints — STCG/LTCG buckets and F&O turnover from paper trades."""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import PaperAccount, PaperPosition, Strategy
from app.services.tax_report import (
    TaxTrade,
    build_summary,
    classify,
    holding_days,
    parse_fy,
    trades_to_csv,
)

router = APIRouter(prefix="/tax", tags=["tax"])


def _fy_dates(fy: str) -> tuple[date, date]:
    try:
        return parse_fy(fy)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


async def _owned_account(db: DbSession, user_id: uuid.UUID, account_id: uuid.UUID) -> None:
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.id == account_id, PaperAccount.user_id == user_id)
    )
    if result.scalars().first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper account not found")


@router.get("/report")
async def tax_report(
    fy: str = Query(default=None, description="Financial year like '2025-26' (Apr 1 – Mar 31). Defaults to current FY."),
    segment: str = Query(default="equity", pattern="^(equity|fno)$"),
    account_id: uuid.UUID | None = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Closed paper trades bucketed for Indian capital-gains / business-income reporting."""
    start, end = _fy_dates(fy or _current_fy())
    if account_id is not None:
        await _owned_account(db, current_user.id, account_id)

    stmt = (
        select(PaperPosition, Strategy.underlying)
        .join(Strategy, PaperPosition.strategy_id == Strategy.id, isouter=True)
        .where(
            PaperPosition.status == "closed",
            PaperPosition.exit_time.is_not(None),
            PaperPosition.exit_time >= datetime(start.year, start.month, start.day, tzinfo=UTC),
            PaperPosition.exit_time < datetime(end.year, end.month, end.day, tzinfo=UTC) + _one_day(),
        )
    )
    # Scope by accounts owned by the user
    owned = select(PaperAccount.id).where(PaperAccount.user_id == current_user.id)
    if account_id is not None:
        owned = owned.where(PaperAccount.id == account_id)
    stmt = stmt.where(PaperPosition.account_id.in_(owned))

    rows = (await db.execute(stmt)).all()

    trades: list[TaxTrade] = []
    for pos, underlying in rows:
        exit_d = pos.exit_time.date() if pos.exit_time.tzinfo is None else pos.exit_time.astimezone(UTC).date()
        entry_d = pos.entry_time.date() if pos.entry_time.tzinfo is None else pos.entry_time.astimezone(UTC).date()
        pnl = float(pos.realized_pnl or 0.0)
        days = holding_days(entry_d, exit_d)
        trades.append(TaxTrade(
            exit_date=exit_d.isoformat(),
            underlying=underlying or "UNKNOWN",
            direction=pos.direction,
            quantity=float(pos.quantity),
            entry_price=float(pos.entry_price),
            exit_price=float(pos.exit_price or 0.0),
            realized_pnl=pnl,
            holding_days=days,
            category=classify(days, segment),
        ))
    trades.sort(key=lambda t: t.exit_date)

    return {
        "fy": fy or _current_fy(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        **build_summary(trades, segment).model_dump(),
        "trades": [t.model_dump() for t in trades],
    }


@router.get("/report/csv")
async def tax_report_csv(
    fy: str = Query(default=None),
    segment: str = Query(default="equity", pattern="^(equity|fno)$"),
    account_id: uuid.UUID | None = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """CSV download of the same report — ITR-prep friendly."""
    start, end = _fy_dates(fy or _current_fy())

    # Reuse the JSON path for correctness, then serialize
    report = await tax_report(fy=fy or _current_fy(), segment=segment, account_id=account_id, db=db, current_user=current_user)
    trades = [TaxTrade.model_validate(t) for t in report["trades"]]
    csv_text = trades_to_csv(trades)
    filename = f"tax_{segment}_{start.year}-{str(start.year + 1)[2:]}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _current_fy() -> str:
    today = datetime.now(UTC).date()
    start_year = today.year if today >= date(today.year, 4, 1) else today.year - 1
    return f"{start_year}-{str(start_year + 1)[2:]}"


def _one_day():
    from datetime import timedelta
    return timedelta(days=1)
