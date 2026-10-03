"""Chart data-path performance.

/quant/series originally called provider.get_historical_data on every request,
which generated 60 days of synthetic candles (~160 ms) and then discarded all
but the last `bars`. A request for 20 bars therefore cost the same as one for
2000. These tests pin the two properties that fix relies on: the history window
is sized to the request, and stored candles are preferred over regeneration.
"""

import pytest

from app.api.v1.quant import _minutes_per_interval, _series_history_days

# --- history window sizing --------------------------------------------------


def test_small_request_asks_for_little_history():
    assert _series_history_days(20, "5m") <= 15


def test_window_grows_with_bar_count():
    small = _series_history_days(50, "5m")
    large = _series_history_days(2000, "5m")
    assert large > small


def test_window_is_not_the_old_fixed_60_days():
    """Regression guard: a 20-bar chart must not read months of history."""
    assert _series_history_days(20, "5m") < 60


def test_daily_bars_request_more_calendar_days():
    """Daily candles are sparse, so the same bar count spans far longer."""
    assert _series_history_days(2000, "1d") > _series_history_days(2000, "5m")


def test_minute_bars_request_fewer_days_than_daily():
    assert _series_history_days(500, "1m") < _series_history_days(500, "1d")


def test_window_is_bounded():
    """A pathological bar count must not ask for an unbounded query."""
    assert _series_history_days(10**9, "1m") <= 400
    assert _series_history_days(1, "1d") >= 10


@pytest.mark.parametrize("interval", ["1m", "5m", "15m", "30m", "1h", "1d"])
def test_every_timeframe_produces_a_sane_window(interval):
    days = _series_history_days(500, interval)
    assert 10 <= days <= 400


def test_unknown_interval_falls_back_rather_than_crashing():
    assert _series_history_days(500, "7m") >= 10


def test_minutes_per_interval_mapping():
    assert _minutes_per_interval("1m") == 1
    assert _minutes_per_interval("1h") == 60
    assert _minutes_per_interval("1d") == 1440
    assert _minutes_per_interval("bogus") == 5


# --- stored candles preferred ----------------------------------------------


class _FakeSession:
    """Minimal async context manager so load_candles sees a usable session."""


@pytest.mark.asyncio
async def test_stored_candles_are_preferred_over_the_provider(monkeypatch):
    """The whole point: a DB read beats regenerating history."""
    from app.api.v1 import quant

    calls = {"stored": 0, "provider": 0}

    async def fake_load(db, **kwargs):
        calls["stored"] += 1
        return [_bar(i) for i in range(500)]

    async def fake_provider_data(symbol, interval, start, end):
        calls["provider"] += 1
        return []

    import app.services.candles as candle_service

    monkeypatch.setattr(candle_service, "load_candles", fake_load)
    monkeypatch.setattr(quant, "load_candles", fake_load, raising=False)

    class P:
        name = "test"
        is_demo = False

        async def get_historical_data(self, s, i, a, b):
            return await fake_provider_data(s, i, a, b)

    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    out = await quant._load_series_candles(
        _FakeSession(), P(), "NIFTY", "5m", now - timedelta(days=14), now
    )
    assert len(out) == 500
    assert calls["stored"] == 1
    assert calls["provider"] == 0, "must not regenerate when history is stored"


@pytest.mark.asyncio
async def test_falls_back_to_provider_when_nothing_is_stored(monkeypatch):
    """The terminal must still work before any history has been ingested."""
    from datetime import UTC, datetime, timedelta

    from app.api.v1 import quant

    async def fake_load(db, **kwargs):
        return []

    monkeypatch.setattr(quant, "load_candles", fake_load, raising=False)

    class P:
        name = "test"
        is_demo = False

        async def get_historical_data(self, s, i, a, b):
            return [_bar(n) for n in range(300)]

    now = datetime.now(UTC)
    out = await quant._load_series_candles(
        _FakeSession(), P(), "NIFTY", "5m", now - timedelta(days=14), now
    )
    assert len(out) == 300


@pytest.mark.asyncio
async def test_store_failure_falls_back_instead_of_500(monkeypatch):
    """A database problem must not break the chart terminal."""
    from datetime import UTC, datetime, timedelta

    from app.api.v1 import quant

    async def boom(db, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(quant, "load_candles", boom, raising=False)

    class P:
        name = "test"
        is_demo = False

        async def get_historical_data(self, s, i, a, b):
            return [_bar(n) for n in range(10)]

    now = datetime.now(UTC)
    out = await quant._load_series_candles(
        _FakeSession(), P(), "NIFTY", "5m", now - timedelta(days=14), now
    )
    assert len(out) == 10


def _bar(index: int):
    from datetime import UTC, datetime, timedelta

    from app.marketdata.base import Candle

    return Candle(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
        instrument_id="NIFTY",
        open=100.0 + index,
        high=101.0 + index,
        low=99.0 + index,
        close=100.5 + index,
        volume=1000,
    )
