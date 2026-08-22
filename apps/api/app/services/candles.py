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
    """Load stored candles for a symbol/interval, oldest first."""
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
    return [
        Candle(
            timestamp=ensure_utc(r.time),
            instrument_id=r.instrument_id,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=float(r.volume or 0),
            oi=float(r.oi) if r.oi is not None else None,
        )
        for r in rows
    ]
