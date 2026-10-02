"""Candle loading from local storage.

Backtests and future engines read candles from the DB (populated by the
ingestion pipeline) — never directly from a provider — so results are
reproducible against the exact stored series.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketdata.base import Candle
from app.models import CANDLE_MODELS_BY_SEGMENT
from app.models.instrument import InstrumentMaster
from app.services.validation import ensure_utc


async def resolve_instrument(db: AsyncSession, symbol: str) -> InstrumentMaster | None:
    result = await db.execute(
        select(InstrumentMaster).where(InstrumentMaster.symbol == symbol.upper())
    )
    return result.scalars().first()


async def load_candles(
    db: AsyncSession,
    symbol: str,
    interval: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Candle]:
    """Load stored candles for a symbol/interval, oldest first.

    For option instruments the returned candles also carry strike, option type,
    expiry and the underlying's spot for each bar, so Black-Scholes indicators
    can run on stored history instead of only on a live chain snapshot.
    """
    result = await db.execute(
        select(InstrumentMaster).where(InstrumentMaster.symbol == symbol.upper())
    )
    instrument = result.scalars().first()
    if instrument is None:
        return []
    table = CANDLE_MODELS_BY_SEGMENT[instrument.segment]
    stmt = select(table).where(table.instrument_id == instrument.symbol, table.interval == interval)
    if start is not None:
        stmt = stmt.where(table.time >= start)
    if end is not None:
        stmt = stmt.where(table.time <= end)
    stmt = stmt.order_by(table.time.asc())
    rows = (await db.execute(stmt)).scalars().all()

    spot_by_ts = await _underlying_spot_map(db, instrument, interval)

    candles: list[Candle] = []
    for r in rows:
        ts = ensure_utc(r.time)
        is_option = instrument.segment == "options"
        candles.append(
            Candle(
                timestamp=ts,
                instrument_id=r.instrument_id,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=float(r.volume or 0),
                oi=float(r.oi) if r.oi is not None else None,
                strike=instrument.strike if is_option else None,
                option_type=instrument.option_type if is_option else None,
                expiry=instrument.expiry if is_option else None,
                underlying_price=spot_by_ts.get(ts) if is_option else None,
            )
        )
    return candles


async def _underlying_spot_map(
    db: AsyncSession, instrument: InstrumentMaster, interval: str
) -> dict[datetime, float]:
    """Map bar timestamp -> underlying close, for option series.

    Returns an empty map when the option has no underlying recorded or that
    underlying has no stored candles; the Greeks indicators degrade to NaN
    rather than guessing.
    """
    if instrument.segment != "options" or not instrument.underlying:
        return {}
    underlying = instrument.underlying.upper()
    found = await db.execute(
        select(InstrumentMaster).where(InstrumentMaster.symbol == underlying)
    )
    parent = found.scalars().first()
    if parent is None:
        return {}
    table = CANDLE_MODELS_BY_SEGMENT[parent.segment]
    stmt = (
        select(table)
        .where(table.instrument_id == parent.symbol, table.interval == interval)
        .order_by(table.time.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {ensure_utc(r.time): float(r.close) for r in rows}
