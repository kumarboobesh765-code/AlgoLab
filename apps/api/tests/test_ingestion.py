"""Tests for the ingestion pipeline (sync instruments, ingest history, idempotency)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

import app.db.session as session_mod
from app.core.config import get_settings
from app.db.base import Base
from app.marketdata.base import Candle, ProviderError
from app.marketdata.demo import DemoProvider
from app.models import IndexCandle, InstrumentMaster
from app.services.ingest import ingest_history, resolve_instrument, sync_instruments

DAY_START = datetime(2026, 8, 10, 3, 45, tzinfo=UTC)  # 09:15 IST
DAY_END = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)  # 15:30 IST


@pytest_asyncio.fixture(autouse=True)
async def isolated_db(tmp_path, monkeypatch):
    """Service-level tests must not touch the developer's real database file."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'ingest.db'}")
    get_settings.cache_clear()
    session_mod.reset_engine()
    engine = session_mod.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    session_mod.reset_engine()
    get_settings.cache_clear()


async def test_sync_and_resolve(client):
    from app.db.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await sync_instruments(db, DemoProvider())
        assert result["received"] == 5

        nifty = await resolve_instrument(db, "NIFTY")
        assert nifty is not None
        assert nifty.segment == "index"
        assert nifty.security_id == "DEMO-NIFTY"

        missing = await resolve_instrument(db, "NOPE")
        assert missing is None


async def test_ingest_history_idempotent(client):
    from app.db.session import get_session_factory

    provider = DemoProvider()
    session_factory = get_session_factory()
    async with session_factory() as db:
        await sync_instruments(db, provider)

        stats = await ingest_history(
            db, provider, symbol="NIFTY", interval="5m", start=DAY_START, end=DAY_END
        )
        assert stats.fetched == 75  # 375 minutes / 5
        assert stats.inserted_or_updated == 75
        assert stats.issues == []

        count = (
            await db.execute(select(func.count()).select_from(IndexCandle))
        ).scalar_one()
        assert count == 75

        # Re-ingest the same range: upsert must not duplicate rows.
        stats2 = await ingest_history(
            db, provider, symbol="NIFTY", interval="5m", start=DAY_START, end=DAY_END
        )
        assert stats2.fetched == 75
        db.expire_all()
        count2 = (
            await db.execute(select(func.count()).select_from(IndexCandle))
        ).scalar_one()
        assert count2 == 75


async def test_ingest_unknown_symbol(client):
    from app.db.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ProviderError, match="Sync the instrument master"):
            await ingest_history(
                db,
                DemoProvider(),
                symbol="FAKE",
                interval="5m",
                start=DAY_START,
                end=DAY_END,
            )


class _BrokenProvider(DemoProvider):
    """Demo provider that emits one candle violating OHLC rules."""

    async def get_historical_data(self, symbol, interval, start, end):
        candles = await super().get_historical_data(symbol, interval, start, end)
        first = candles[0]
        broken = Candle(
            timestamp=first.timestamp,
            instrument_id=first.instrument_id,
            open=100.0,
            high=90.0,  # high < low -> invalid
            low=95.0,
            close=97.0,
            volume=10,
        )
        return [broken] + candles[1:]


async def test_ingest_surfaces_validation_issues(client):
    from app.db.session import get_session_factory

    provider = _BrokenProvider()
    session_factory = get_session_factory()
    async with session_factory() as db:
        await sync_instruments(db, provider)
        stats = await ingest_history(
            db, provider, symbol="NIFTY", interval="5m", start=DAY_START, end=DAY_END
        )
        types = {i["type"] for i in stats.issues}
        assert "invalid_ohlc" in types


async def test_instrument_upsert_updates_existing(client):
    from app.db.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        await sync_instruments(db, DemoProvider())
        count1 = (await db.execute(select(func.count()).select_from(InstrumentMaster))).scalar_one()

        await sync_instruments(db, DemoProvider())
        count2 = (await db.execute(select(func.count()).select_from(InstrumentMaster))).scalar_one()
        assert count1 == count2 == 5
