"""Paper account endpoints — virtual money only, never real orders."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession
from app.models import ForwardTestRun, PaperAccount, PaperOrder, PaperPosition, Strategy
from app.quant.schema import StrategyDefinition
from app.schemas.paper import PaperAccountCreate, PaperAccountDetail, PaperAccountOut
from app.services.candles import load_candles

router = APIRouter(prefix="/paper/accounts", tags=["paper"])


async def _owned_account(db: DbSession, user_id: uuid.UUID, account_id: uuid.UUID) -> PaperAccount:
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.id == account_id, PaperAccount.user_id == user_id)
    )
    account = result.scalars().first()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper account not found")
    return account


def _position_dict(p: PaperPosition, last_close: float | None) -> dict:
    entry = float(p.entry_price)
    qty = float(p.quantity)
    dir_sign = 1 if p.direction == "long" else -1
    d: dict = {
        "id": str(p.id),
        "strategy_id": str(p.strategy_id) if p.strategy_id else None,
        "direction": p.direction,
        "quantity": qty,
        "entry_price": entry,
        "entry_time": p.entry_time.isoformat() if p.entry_time else None,
        "stop_price": float(p.stop_price) if p.stop_price is not None else None,
        "target_price": float(p.target_price) if p.target_price is not None else None,
        "status": p.status,
    }
    if p.status == "closed":
        d.update(
            exit_price=float(p.exit_price) if p.exit_price is not None else None,
            exit_time=p.exit_time.isoformat() if p.exit_time else None,
            exit_reason=p.exit_reason,
            realized_pnl=float(p.realized_pnl) if p.realized_pnl is not None else None,
        )
    elif last_close is not None:
        d["last_close"] = last_close
        d["unrealized_pnl"] = round((last_close - entry) * qty * dir_sign, 2)
    return d


async def _latest_close_for(
    db: AsyncSession, strategy_cache: dict[uuid.UUID, tuple[str, str] | None], strategy_id: uuid.UUID | None
) -> float | None:
    """Latest stored close for a position's strategy symbol/timeframe."""
    if strategy_id is None:
        return None
    if strategy_id not in strategy_cache:
        strategy = await db.get(Strategy, strategy_id)
        if strategy is None or not strategy.definition:
            strategy_cache[strategy_id] = None
        else:
            tf = StrategyDefinition.model_validate(strategy.definition).timeframe
            strategy_cache[strategy_id] = (strategy.underlying, tf)
    cached = strategy_cache[strategy_id]
    if cached is None:
        return None
    candles = await load_candles(db, symbol=cached[0], interval=cached[1])
    return candles[-1].close if candles else None


async def _account_snapshot(
    db: AsyncSession, account: PaperAccount
) -> tuple[float, list[dict]]:
    """Equity = cash + marked-to-market open positions."""
    positions = (
        (
            await db.execute(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.status == "open",
                )
            )
        )
        .scalars()
        .all()
    )
    cache: dict[uuid.UUID, tuple[str, str] | None] = {}
    equity = float(account.cash_balance)
    open_dicts: list[dict] = []
    for p in positions:
        last_close = await _latest_close_for(db, cache, p.strategy_id)
        open_dicts.append(_position_dict(p, last_close))
        if last_close is not None:
            dir_sign = 1 if p.direction == "long" else -1
            equity += (last_close - float(p.entry_price)) * float(p.quantity) * dir_sign
    return round(equity, 2), open_dicts


@router.post("", response_model=PaperAccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: PaperAccountCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> PaperAccount:
    account = PaperAccount(
        user_id=current_user.id,
        name=payload.name,
        initial_capital=Decimal(str(round(payload.initial_capital, 2))),
        cash_balance=Decimal(str(round(payload.initial_capital, 2))),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.get("", response_model=list[PaperAccountOut])
async def list_accounts(
    db: DbSession,
    current_user: CurrentUser,
) -> list[PaperAccount]:
    result = await db.execute(
        select(PaperAccount)
        .where(PaperAccount.user_id == current_user.id)
        .order_by(PaperAccount.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{account_id}", response_model=PaperAccountDetail)
async def get_account(
    account_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> PaperAccountDetail:
    account = await _owned_account(db, current_user.id, account_id)
    equity, open_positions = await _account_snapshot(db, account)

    orders = (
        (
            await db.execute(
                select(PaperOrder)
                .where(PaperOrder.account_id == account.id)
                .order_by(PaperOrder.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    closed = (
        (
            await db.execute(
                select(PaperPosition)
                .where(PaperPosition.account_id == account.id, PaperPosition.status == "closed")
                .order_by(PaperPosition.exit_time.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )

    return PaperAccountDetail(
        id=account.id,
        name=account.name,
        initial_capital=float(account.initial_capital),
        cash_balance=float(account.cash_balance),
        status=account.status,
        created_at=account.created_at,
        equity=equity,
        unrealized_pnl=round(equity - float(account.cash_balance), 2),
        open_positions=open_positions,
        closed_positions=[_position_dict(p, None) for p in closed],
        recent_orders=[
            {
                "id": str(o.id),
                "side": o.side,
                "quantity": float(o.quantity),
                "filled_price": float(o.filled_price),
                "reason": o.reason,
                "signal_time": o.signal_time.isoformat() if o.signal_time else None,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    account = await _owned_account(db, current_user.id, account_id)
    active = (
        await db.execute(
            select(ForwardTestRun).where(
                ForwardTestRun.account_id == account.id,
                ForwardTestRun.status == "running",
            )
        )
    ).scalars().first()
    if active is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Stop the running forward test before deleting this account",
        )
    await db.delete(account)
    await db.commit()
