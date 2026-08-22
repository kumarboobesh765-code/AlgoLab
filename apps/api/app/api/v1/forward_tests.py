"""Forward test lifecycle: run a strategy against a paper account.

Ticks process newly completed stored candles (ingested via the Data Manager)
and apply virtual fills. Semantics match the backtest engine exactly —
next-bar-open fills, carried pending actions, intrabar risk exits — so a
forward test is the live continuation of the same simulation model.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import ForwardTestRun, PaperAccount, PaperOrder, PaperPosition, Strategy
from app.paper import required_warmup, step_paper
from app.quant.schema import StrategyDefinition
from app.schemas.paper import ForwardTestCreate, ForwardTestOut, TickResult
from app.services.candles import load_candles
from app.services.validation import ensure_utc

# Paper fills mirror the backtest default cost model (% of traded value per side).
PAPER_COSTS_PCT = 0.03

router = APIRouter(prefix="/forward-tests", tags=["forward-tests"])


async def _owned_run(db: DbSession, user_id: uuid.UUID, run_id: uuid.UUID) -> ForwardTestRun:
    result = await db.execute(
        select(ForwardTestRun).where(
            ForwardTestRun.id == run_id, ForwardTestRun.user_id == user_id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Forward test not found")
    return run


async def _run_context(db: DbSession, run: ForwardTestRun):
    strategy = await db.get(Strategy, run.strategy_id)
    account = await db.get(PaperAccount, run.account_id)
    if strategy is None or account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run references missing strategy/account")
    if not strategy.definition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Strategy has no definition")
    definition = StrategyDefinition.model_validate(strategy.definition)
    return strategy, account, definition


def _open_position_state(p: PaperPosition) -> dict:
    return {
        "id": str(p.id),
        "direction": p.direction,
        "quantity": float(p.quantity),
        "entry_price": float(p.entry_price),
        "entry_time": p.entry_time.isoformat(),
        "stop_price": float(p.stop_price) if p.stop_price is not None else None,
        "target_price": float(p.target_price) if p.target_price is not None else None,
        "trail_pct": float(p.trail_pct) if p.trail_pct is not None else None,
        "trailed": bool(p.trailed),
        "extreme": float(p.extreme) if p.extreme is not None else None,
    }


def _dec(value: float | None, places: int = 4) -> Decimal | None:
    return Decimal(str(round(value, places))) if value is not None else None


async def _apply_fills(
    db: DbSession, run: ForwardTestRun, strategy: Strategy, account: PaperAccount, step
) -> None:
    """Persist engine fills as positions + immutable order records."""
    for fill in step.actions:
        if fill.reason == "entry" and fill.position_state is not None:
            st = fill.position_state
            pos = PaperPosition(
                account_id=account.id,
                strategy_id=strategy.id,
                direction=st["direction"],
                quantity=_dec(st["quantity"]),
                entry_price=_dec(st["entry_price"]),
                entry_time=datetime.fromisoformat(st["entry_time"]),
                stop_price=_dec(st.get("stop_price")),
                target_price=_dec(st.get("target_price")),
                trail_pct=_dec(st.get("trail_pct") * 100 if st.get("trail_pct") is not None else None, 3),
                extreme=_dec(st.get("extreme")),
                status="open",
            )
            db.add(pos)
            await db.flush()
            db.add(
                PaperOrder(
                    account_id=account.id,
                    strategy_id=strategy.id,
                    position_id=pos.id,
                    side=fill.side,
                    quantity=pos.quantity,
                    filled_price=pos.entry_price,
                    reason="entry",
                    signal_time=fill.time,
                )
            )
        elif fill.pnl is not None:
            # Closing fill: close this strategy's open position on the account.
            open_pos = (
                await db.execute(
                    select(PaperPosition).where(
                        PaperPosition.account_id == account.id,
                        PaperPosition.strategy_id == strategy.id,
                        PaperPosition.status == "open",
                    )
                )
            ).scalars().first()
            if open_pos is None:
                continue
            open_pos.status = "closed"
            open_pos.exit_price = _dec(fill.price)
            open_pos.exit_time = fill.time
            open_pos.exit_reason = fill.reason
            open_pos.realized_pnl = _dec(fill.pnl, 2)
            db.add(
                PaperOrder(
                    account_id=account.id,
                    strategy_id=strategy.id,
                    position_id=open_pos.id,
                    side=fill.side,
                    quantity=open_pos.quantity,
                    filled_price=open_pos.exit_price,
                    reason=fill.reason,
                    signal_time=fill.time,
                )
            )
            account.cash_balance += Decimal(str(fill.pnl))


@router.post("", response_model=ForwardTestOut, status_code=status.HTTP_201_CREATED)
async def create_forward_test(
    payload: ForwardTestCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ForwardTestRun:
    strategy = (
        (
            await db.execute(
                select(Strategy).where(
                    Strategy.id == payload.strategy_id, Strategy.user_id == current_user.id
                )
            )
        )
        .scalars()
        .first()
    )
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    if not strategy.definition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Strategy has no definition")

    account = (
        (
            await db.execute(
                select(PaperAccount).where(
                    PaperAccount.id == payload.account_id,
                    PaperAccount.user_id == current_user.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper account not found")
    if account.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Paper account is not active")

    existing = (
        (
            await db.execute(
                select(ForwardTestRun).where(
                    ForwardTestRun.strategy_id == strategy.id,
                    ForwardTestRun.status == "running",
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This strategy already has a running forward test",
        )

    run = ForwardTestRun(
        user_id=current_user.id,
        strategy_id=strategy.id,
        account_id=account.id,
        version_number=strategy.current_version,
        status="running",
        last_message="started",
    )
    strategy.status = "running"
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@router.get("", response_model=list[ForwardTestOut])
async def list_forward_tests(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: str | None = None,
) -> list[ForwardTestRun]:
    stmt = select(ForwardTestRun).where(ForwardTestRun.user_id == current_user.id)
    if status_filter:
        stmt = stmt.where(ForwardTestRun.status == status_filter)
    stmt = stmt.order_by(ForwardTestRun.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{run_id}", response_model=ForwardTestOut)
async def get_forward_test(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ForwardTestRun:
    return await _owned_run(db, current_user.id, run_id)


@router.post("/{run_id}/tick", response_model=TickResult)
async def tick_forward_test(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> TickResult:
    run = await _owned_run(db, current_user.id, run_id)
    if run.status != "running":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Run is {run.status}, not running")

    strategy, account, definition = await _run_context(db, run)

    open_pos = (
        (
            await db.execute(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.strategy_id == strategy.id,
                    PaperPosition.status == "open",
                )
            )
        )
        .scalars()
        .first()
    )

    all_candles = await load_candles(
        db, symbol=strategy.underlying, interval=definition.timeframe
    )
    if run.last_bar_time is None:
        # First tick: anchor to the latest stored bar without acting — forward
        # tests start from "now", they do not replay old history.
        if not all_candles:
            return TickResult(
                run_id=run.id,
                bars_processed=0,
                fills=[],
                open_position=None,
                message="no stored candles — ingest history first",
            )
        run.last_bar_time = all_candles[-1].timestamp
        run.last_message = f"initialized at latest bar {run.last_bar_time.isoformat()}"
        await db.commit()
        return TickResult(
            run_id=run.id,
            bars_processed=0,
            fills=[],
            open_position=None,
            message=run.last_message,
        )

    # Ensure timezone-aware comparison — SQLite may return naive datetimes.
    anchor = ensure_utc(run.last_bar_time)
    new_candles = [c for c in all_candles if c.timestamp > anchor]
    if not new_candles:
        return TickResult(
            run_id=run.id,
            bars_processed=0,
            fills=[],
            open_position=_open_position_state(open_pos) if open_pos else None,
            message="no new candles — ingest history first",
        )
    warmup = required_warmup(definition)
    prior = [c for c in all_candles if c.timestamp <= anchor]
    history = prior[-(warmup + 1) :] if warmup else prior[-1:]

    step = step_paper(
        definition,
        history,
        new_candles,
        _open_position_state(open_pos) if open_pos else None,
        run.pending_action,
        cash=float(account.cash_balance),
        costs_pct=PAPER_COSTS_PCT,
    )
    await _apply_fills(db, run, strategy, account, step)

    run.last_bar_time = step.last_bar_time or run.last_bar_time
    run.pending_action = step.pending_action
    msgs = [
        f"{a.reason} {a.side} {round(a.quantity, 2)} @ {round(a.price, 2)}" for a in step.actions
    ]
    run.last_message = (
        "; ".join(msgs)[:500] if msgs else f"processed {len(new_candles)} bars, no action"
    )
    await db.commit()

    now_open = (
        (
            await db.execute(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.strategy_id == strategy.id,
                    PaperPosition.status == "open",
                )
            )
        )
        .scalars()
        .first()
    )

    return TickResult(
        run_id=run.id,
        bars_processed=len(new_candles),
        fills=[
            {
                "side": a.side,
                "quantity": round(a.quantity, 4),
                "price": round(a.price, 4),
                "reason": a.reason,
                "time": a.time.isoformat(),
                "pnl": round(a.pnl, 2) if a.pnl is not None else None,
            }
            for a in step.actions
        ],
        open_position=_open_position_state(now_open) if now_open else None,
        message=run.last_message,
    )


async def _set_status(db: DbSession, run: ForwardTestRun, new_status: str) -> ForwardTestRun:
    run.status = new_status
    strategy = await db.get(Strategy, run.strategy_id)
    if strategy is not None:
        strategy.status = new_status
    if new_status == "stopped":
        run.stopped_at = datetime.now(UTC)
        run.pending_action = None
        # Force-close any open position at the latest stored close.
        if strategy is not None and strategy.definition:
            definition = StrategyDefinition.model_validate(strategy.definition)
            open_pos = (
                (
                    await db.execute(
                        select(PaperPosition).where(
                            PaperPosition.account_id == run.account_id,
                            PaperPosition.strategy_id == run.strategy_id,
                            PaperPosition.status == "open",
                        )
                    )
                )
                .scalars()
                .first()
            )
            if open_pos is not None:
                candles = await load_candles(
                    db, symbol=strategy.underlying, interval=definition.timeframe
                )
                if candles:
                    last = candles[-1]
                    dir_sign = 1 if open_pos.direction == "long" else -1
                    gross = (
                        (last.close - float(open_pos.entry_price))
                        * float(open_pos.quantity)
                        * dir_sign
                    )
                    cost = last.close * float(open_pos.quantity) * PAPER_COSTS_PCT / 100.0
                    pnl = round(gross - cost, 2)
                    open_pos.status = "closed"
                    open_pos.exit_price = _dec(last.close)
                    open_pos.exit_time = last.timestamp
                    open_pos.exit_reason = "end"
                    open_pos.realized_pnl = _dec(pnl, 2)
                    account = await db.get(PaperAccount, run.account_id)
                    if account is not None:
                        account.cash_balance += Decimal(str(pnl))
                    db.add(
                        PaperOrder(
                            account_id=run.account_id,
                            strategy_id=run.strategy_id,
                            position_id=open_pos.id,
                            side="SELL" if dir_sign == 1 else "BUY",
                            quantity=open_pos.quantity,
                            filled_price=open_pos.exit_price,
                            reason="end",
                            signal_time=last.timestamp,
                        )
                    )
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/{run_id}/pause", response_model=ForwardTestOut)
async def pause_forward_test(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ForwardTestRun:
    run = await _owned_run(db, current_user.id, run_id)
    if run.status != "running":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only running tests can be paused")
    return await _set_status(db, run, "paused")


@router.post("/{run_id}/resume", response_model=ForwardTestOut)
async def resume_forward_test(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ForwardTestRun:
    run = await _owned_run(db, current_user.id, run_id)
    if run.status != "paused":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only paused tests can be resumed")
    return await _set_status(db, run, "running")


@router.post("/{run_id}/stop", response_model=ForwardTestOut)
async def stop_forward_test(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ForwardTestRun:
    run = await _owned_run(db, current_user.id, run_id)
    if run.status == "stopped":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already stopped")
    return await _set_status(db, run, "stopped")
