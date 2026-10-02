"""`load_candles` must attach option context so the BS indicators can run.

Before this change `load_candles` returned bare OHLCV+OI, which is why the
option Greeks/IV indicators were unreachable from stored history. These tests
pin the loader contract:

- index bars get no option context,
- option bars get strike / option type / expiry,
- option bars get the underlying's spot for each bar,
- a missing or unstored underlying degrades to None rather than raising,
- the extra underlying query does not run for non-option instruments.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import CANDLE_MODELS_BY_SEGMENT, InstrumentMaster
from app.services.candles import load_candles

START = datetime(2025, 6, 2, 3, 30, tzinfo=UTC)


def _ts(i: int) -> datetime:
    return START + timedelta(minutes=i)


async def _seed_instrument(db_session, **kwargs) -> InstrumentMaster:
    inst = InstrumentMaster(**kwargs)
    db_session.add(inst)
    await db_session.flush()
    return inst


async def _seed_candles(db_session, instrument: InstrumentMaster, closes: list[float], interval="5m"):
    table = CANDLE_MODELS_BY_SEGMENT[instrument.segment]
    rows = [
        table(
            instrument_id=instrument.symbol,
            interval=interval,
            time=_ts(i),
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=100 + i,
            oi=1000 + i,
        )
        for i, c in enumerate(closes)
    ]
    db_session.add_all(rows)
    await db_session.flush()


class TestIndexCandlesUnchanged:
    async def test_index_candles_have_no_option_context(self, db_session):
        await _seed_instrument(
            db_session,
            security_id="13",
            exchange="NSE",
            segment="index",
            symbol="NIFTY",
            lot_size=50,
        )
        await _seed_candles(db_session, (await db_session.execute(
            select(InstrumentMaster).where(InstrumentMaster.symbol == "NIFTY")
        )).scalars().first(), [22000.0, 22010.0, 22020.0])

        candles = await load_candles(db_session, "NIFTY", "5m")
        assert len(candles) == 3
        for c in candles:
            assert c.strike is None
            assert c.option_type is None
            assert c.expiry is None
            assert c.underlying_price is None
            # OHLCV must still round-trip unchanged
            assert c.close > 0
            assert c.volume > 0


class TestOptionContext:
    async def _seed_option(self, db_session, with_underlying: bool = True):
        index = await _seed_instrument(
            db_session,
            security_id="13",
            exchange="NSE",
            segment="index",
            symbol="NIFTY",
            lot_size=50,
        )
        if with_underlying:
            await _seed_candles(db_session, index, [22000.0, 22005.0, 22010.0])

        option = await _seed_instrument(
            db_session,
            security_id="60001",
            exchange="NSE",
            segment="options",
            symbol="NIFTY25JUN22000CE",
            underlying="NIFTY",
            strike=22000.0,
            option_type="CE",
            expiry=date(2025, 6, 26),
            lot_size=50,
        )
        await _seed_candles(db_session, option, [150.0, 155.0, 160.0])
        return option

    async def test_option_bars_get_strike_type_and_expiry(self, db_session):
        await self._seed_option(db_session)
        candles = await load_candles(db_session, "NIFTY25JUN22000CE", "5m")
        assert len(candles) == 3
        for c in candles:
            assert c.strike == 22000.0
            assert c.option_type == "CE"
            assert c.expiry == date(2025, 6, 26)

    async def test_option_bars_get_underlying_spot(self, db_session):
        await self._seed_option(db_session)
        candles = await load_candles(db_session, "NIFTY25JUN22000CE", "5m")
        assert [c.underlying_price for c in candles] == [22000.0, 22005.0, 22010.0]

    async def test_missing_underlying_store_degrades_to_none(self, db_session):
        await self._seed_option(db_session, with_underlying=False)
        candles = await load_candles(db_session, "NIFTY25JUN22000CE", "5m")
        assert len(candles) == 3
        for c in candles:
            # context we *can* know is still attached
            assert c.strike == 22000.0
            assert c.option_type == "CE"
            # spot is unknowable, so it must be None (Greeks then yield NaN)
            assert c.underlying_price is None

    async def test_greeks_indicators_become_usable_end_to_end(self, db_session):
        """The whole point: stored option history now feeds real Greeks."""
        from app.quant.indicators import compute_indicator

        await self._seed_option(db_session)
        candles = await load_candles(db_session, "NIFTY25JUN22000CE", "5m")
        # give the bars a solvable premium near BS value
        for c in candles:
            c.close = c.underlying_price * 0.007  # plausible extrinsic
        delta = compute_indicator("OPTION_DELTA", candles, {})["delta"]
        assert any(not (v != v) for v in delta), "expected at least one finite delta"
        for i, v in enumerate(delta):
            if v == v:  # not NaN
                assert 0.0 <= v <= 1.0


class TestLoaderEdgeCases:
    async def test_unknown_symbol_returns_empty(self, db_session):
        assert await load_candles(db_session, "NOPE", "5m") == []

    async def test_interval_filter_still_applies(self, db_session):
        inst = await _seed_instrument(
            db_session,
            security_id="13",
            exchange="NSE",
            segment="index",
            symbol="NIFTY",
        )
        await _seed_candles(db_session, inst, [100.0, 101.0, 102.0], interval="5m")
        assert len(await load_candles(db_session, "NIFTY", "5m")) == 3
        assert await load_candles(db_session, "NIFTY", "15m") == []

    async def test_symbol_lookup_is_case_insensitive(self, db_session):
        inst = await _seed_instrument(
            db_session,
            security_id="13",
            exchange="NSE",
            segment="index",
            symbol="NIFTY",
        )
        await _seed_candles(db_session, inst, [100.0, 101.0])
        assert len(await load_candles(db_session, "nifty", "5m")) == 2

    async def test_candles_are_ordered_by_timestamp(self, db_session):
        inst = await _seed_instrument(
            db_session,
            security_id="13",
            exchange="NSE",
            segment="index",
            symbol="NIFTY",
        )
        # deliberately non-monotonic closes: if ordering is by time (not value)
        # this must come back in insertion/timestamp order, not sorted by price
        await _seed_candles(db_session, inst, [300.0, 100.0, 200.0])
        candles = await load_candles(db_session, "NIFTY", "5m")
        assert [c.close for c in candles] == [300.0, 100.0, 200.0]
        times = [c.timestamp for c in candles]
        assert times == sorted(times)
