from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, ProviderDep
from app.models import CANDLE_MODELS_BY_SEGMENT, InstrumentMaster
from app.schemas.data import IngestRequest, InstrumentOut
from app.services.ingest import ingest_history, sync_instruments
from app.services.validation import missing_candles_report, validate_candle_series

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/instruments/sync")
async def sync_instruments_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    provider: ProviderDep,
) -> dict:
    """Refresh the local instrument master from the active provider."""
    return await sync_instruments(db, provider)


@router.get("/instruments", response_model=list[InstrumentOut])
async def list_instruments(
    db: DbSession,
    current_user: CurrentUser,
    q: str | None = None,
    segment: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[InstrumentMaster]:
    stmt = select(InstrumentMaster).order_by(InstrumentMaster.symbol)
    if q:
        like = f"%{q.upper()}%"
        stmt = stmt.where(func.upper(InstrumentMaster.symbol).like(like))
    if segment:
        stmt = stmt.where(InstrumentMaster.segment == segment)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/history/ingest")
async def ingest_history_endpoint(
    payload: IngestRequest,
    db: DbSession,
    current_user: CurrentUser,
    provider: ProviderDep,
) -> dict:
    settings = get_settings()
    start_dt = datetime.combine(payload.start, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(payload.end, datetime.max.time().replace(microsecond=0), tzinfo=UTC)
    days = (payload.end - payload.start).days + 1
    if days <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end must be after start")
    if days > settings.INGEST_MAX_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Range too large ({days} days). Max {settings.INGEST_MAX_DAYS} days per request.",
        )
    try:
        stats = await ingest_history(
            db, provider, symbol=payload.symbol, interval=payload.interval, start=start_dt, end=end_dt
        )
    except Exception as exc:
        if not isinstance(exc, HTTPException):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        raise
    return {
        "symbol": stats.symbol,
        "interval": stats.interval,
        "start": stats.start,
        "end": stats.end,
        "fetched": stats.fetched,
        "inserted_or_updated": stats.inserted_or_updated,
        "duplicates_in_batch": stats.duplicates_in_batch,
        "issues": stats.issues,
        "coverage": stats.coverage,
    }


@router.get("/quality/{symbol}")
async def quality_report(
    symbol: str,
    db: DbSession,
    current_user: CurrentUser,
    interval: str = Query(default="5m"),
    days: int = Query(default=7, ge=1, le=365),
) -> dict:
    from app.services.ingest import resolve_instrument

    instrument = await resolve_instrument(db, symbol)
    if instrument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown instrument '{symbol}'")
    table = CANDLE_MODELS_BY_SEGMENT[instrument.segment]

    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    result = await db.execute(
        select(table)
        .where(table.instrument_id == instrument.symbol, table.interval == interval)
        .order_by(table.time.asc())
    )
    rows = result.scalars().all()
    candles = [
        type("Row", (), {
            "timestamp": r.time if r.time.tzinfo else r.time.replace(tzinfo=UTC),
            "instrument_id": r.instrument_id,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "oi": r.oi,
        })()
        for r in rows
    ]
    issues = validate_candle_series(candles, interval)
    coverage = missing_candles_report(candles, start, end, interval)
    return {
        "symbol": instrument.symbol,
        "interval": interval,
        "candles_checked": len(candles),
        "first": rows[0].time.isoformat() if rows else None,
        "last": rows[-1].time.isoformat() if rows else None,
        "issues": issues,
        "coverage": coverage,
    }


@router.get("/status")
async def data_status(db: DbSession, current_user: CurrentUser) -> dict:
    counts = {}
    latest = {}
    for segment, table in CANDLE_MODELS_BY_SEGMENT.items():
        total = (await db.execute(select(func.count()).select_from(table))).scalar_one()
        last_time = (await db.execute(select(func.max(table.time)))).scalar_one()
        counts[segment] = total
        latest[segment] = last_time.isoformat() if last_time else None
    instruments_total = (
        await db.execute(select(func.count()).select_from(InstrumentMaster))
    ).scalar_one()
    return {"instruments": instruments_total, "candle_counts": counts, "latest_candle_utc": latest}
