"""Market-data ingestion pipeline.

Provider → Normalizer → Validator → Database (upsert, idempotent).

Runs synchronously inside the API process for now (guarded by INGEST_MAX_DAYS);
wrapping it in a task queue (Celery/Arq) later only requires calling these
functions from a worker — no signature changes.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketdata.base import MarketDataProvider, ProviderError
from app.models import CANDLE_MODELS_BY_SEGMENT, InstrumentMaster
from app.services.validation import missing_candles_report, validate_candle_series

BATCH_SIZE = 1000


@dataclass
class IngestStats:
    symbol: str
    interval: str
    start: str
    end: str
    fetched: int = 0
    inserted_or_updated: int = 0
    duplicates_in_batch: int = 0
    issues: list[dict] = field(default_factory=list)
    coverage: dict | None = None


async def sync_instruments(db: AsyncSession, provider: MarketDataProvider) -> dict:
    """Refresh instrument_master from the active provider (idempotent upsert)."""
    instruments = await provider.get_instruments()
    if not instruments:
        raise ProviderError(f"Provider '{provider.name}' returned an empty instrument master.")

    for inst in instruments:
        values = {
            "security_id": inst["security_id"],
            "exchange": inst["exchange"],
            "segment": inst["segment"],
            "exchange_segment": inst.get("exchange_segment"),
            "symbol": inst["symbol"],
            "name": inst.get("name"),
            "underlying": inst.get("underlying"),
            "instrument_type": inst.get("instrument_type"),
            "expiry_code": inst.get("expiry_code"),
            "expiry": _as_date(inst.get("expiry")),
            "strike": inst.get("strike"),
            "option_type": inst.get("option_type"),
            "lot_size": int(inst.get("lot_size") or 1),
            "tick_size": float(inst.get("tick_size") or 0.05),
            "status": inst.get("status", "active"),
        }
        stmt = _upsert_stmt(InstrumentMaster, values, ["exchange", "segment", "security_id"])
        await db.execute(stmt)

    await db.commit()
    return {"provider": provider.name, "received": len(instruments), "upserted": len(instruments)}


async def resolve_instrument(db: AsyncSession, symbol: str) -> InstrumentMaster | None:
    result = await db.execute(
        select(InstrumentMaster).where(
            InstrumentMaster.symbol == symbol.upper(),
            InstrumentMaster.status == "active",
        )
    )
    instrument = result.scalars().first()
    if instrument is not None:
        return instrument
    # fall back to security_id match
    result = await db.execute(
        select(InstrumentMaster).where(
            InstrumentMaster.security_id == symbol,
            InstrumentMaster.status == "active",
        )
    )
    return result.scalars().first()


async def ingest_history(
    db: AsyncSession,
    provider: MarketDataProvider,
    *,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> IngestStats:
    """Fetch candles from provider, validate, and upsert into the segment table."""
    instrument = await resolve_instrument(db, symbol)
    if instrument is None:
        raise ProviderError(
            f"Unknown instrument '{symbol}'. Sync the instrument master first "
            "(POST /api/v1/data/instruments/sync)."
        )

    table = CANDLE_MODELS_BY_SEGMENT.get(instrument.segment)
    if table is None:
        raise ProviderError(f"Segment '{instrument.segment}' has no candle table.")

    candles = await provider.get_historical_data(symbol, interval, start, end)

    stats = IngestStats(
        symbol=instrument.symbol,
        interval=interval,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        fetched=len(candles),
    )

    # Normalize: UTC timestamps, finite floats, dedupe within batch (keep last).
    normalized: dict[datetime, dict] = {}
    for c in candles:
        ts = c.timestamp.astimezone(UTC).replace(microsecond=0)
        if any(math.isnan(v) or math.isinf(v) for v in (c.open, c.high, c.low, c.close)):
            continue
        normalized[ts] = {
            "instrument_id": instrument.symbol,
            "interval": interval,
            "time": ts,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": int(c.volume),
            "oi": int(c.oi) if c.oi is not None else None,
        }
    stats.duplicates_in_batch = len(candles) - len(normalized)

    stats.issues = validate_candle_series(candles, interval)

    rows = [normalized[ts] for ts in sorted(normalized)]
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        stmt = _upsert_stmt(
            table,
            chunk,
            ["instrument_id", "interval", "time"],
        )
        await db.execute(stmt)
    stats.inserted_or_updated = len(rows)

    # Coverage is measured over the span actually covered by returned candles
    # (request bounds may extend beyond session hours / into another IST date).
    if candles:
        stats.coverage = missing_candles_report(
            candles, candles[0].timestamp, candles[-1].timestamp, interval
        )

    await db.commit()
    return stats


def _upsert_stmt(table, values: dict | list[dict], conflict_cols: list[str]):
    """Dialect-agnostic upsert (PostgreSQL and SQLite both support ON CONFLICT)."""
    if isinstance(values, dict):
        values = [values]
    from app.db.session import get_engine

    dialect_name = get_engine().dialect.name
    insert_fn = pg_insert if dialect_name == "postgresql" else sqlite_insert
    stmt = insert_fn(table).values(values)
    update_cols = {c.name: stmt.excluded[c.name] for c in table.__table__.columns if c.name not in conflict_cols}
    # 'id' has no default in excluded when absent; guard it
    update_cols.pop("id", None)
    return stmt.on_conflict_do_update(index_elements=conflict_cols, set_=update_cols)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
