from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.deps import ProviderDep
from app.schemas.market import CandleOut, InstrumentOut, OptionChainOut

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/instruments", response_model=list[InstrumentOut])
async def instruments(provider: ProviderDep) -> list[dict]:
    return await provider.get_instruments()


@router.get("/candles", response_model=list[CandleOut])
async def candles(
    provider: ProviderDep,
    symbol: str = Query(default="NIFTY"),
    interval: str = Query(default="5m"),
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[CandleOut]:
    now = datetime.now(UTC)
    start = start or (now - timedelta(days=1))
    end = end or now
    try:
        data = await provider.get_historical_data(symbol, interval, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [
        CandleOut(
            timestamp=c.timestamp,
            instrument_id=c.instrument_id,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            oi=c.oi,
        )
        for c in data
    ]


@router.get("/option-chain", response_model=OptionChainOut)
async def option_chain(
    provider: ProviderDep,
    underlying: str = Query(default="NIFTY"),
    expiry: str | None = None,
) -> dict:
    settings = get_settings()
    cache = get_cache()
    key = f"oc:{provider.name}:{underlying.upper()}:{expiry or 'nearest'}"

    cached = await cache.get_json(key)
    if cached is not None:
        return cached

    try:
        chain = await provider.get_option_chain(underlying, expiry)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await cache.set_json(key, chain, ttl=settings.OPTION_CHAIN_CACHE_TTL)
    return chain
