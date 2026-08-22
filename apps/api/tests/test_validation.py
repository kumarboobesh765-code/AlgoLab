"""Tests for data-quality validation functions."""

from datetime import UTC, datetime, timedelta, timezone

from app.marketdata.base import Candle
from app.services.validation import missing_candles_report, validate_candle_series

IST = timezone(timedelta(hours=5, minutes=30))


def candle(ts, open_=100.0, high=101.0, low=99.0, close=100.5):
    return Candle(timestamp=ts, instrument_id="X", open=open_, high=high, low=low, close=close)


def clean_series(n=10, start=datetime(2026, 8, 10, 3, 45, tzinfo=UTC)):
    return [candle(start + timedelta(minutes=5 * i)) for i in range(n)]


def test_clean_series_has_no_issues():
    assert validate_candle_series(clean_series(), "5m") == []


def test_empty_series_flagged():
    issues = validate_candle_series([], "5m")
    assert issues[0]["type"] == "empty"


def test_invalid_ohlc_detected():
    bad = candle(datetime(2026, 8, 10, 3, 45, tzinfo=UTC), high=90.0, low=95.0)
    issues = validate_candle_series([bad], "5m")
    types = {i["type"] for i in issues}
    assert "invalid_ohlc" in types


def test_duplicate_timestamps_detected():
    ts = datetime(2026, 8, 10, 3, 45, tzinfo=UTC)
    issues = validate_candle_series([candle(ts), candle(ts)], "5m")
    types = {i["type"] for i in issues}
    assert "duplicate_timestamp" in types


def test_abnormal_jump_detected():
    base = datetime(2026, 8, 10, 3, 45, tzinfo=UTC)
    series = [
        candle(base, close=100.0),
        candle(base + timedelta(minutes=5), close=120.0),  # +20%
    ]
    issues = validate_candle_series(series, "5m", jump_threshold_pct=10.0)
    types = {i["type"] for i in issues}
    assert "abnormal_jump" in types


def test_misaligned_timestamp_detected():
    off_grid = datetime(2026, 8, 10, 3, 47, tzinfo=UTC)  # not on 5m grid
    series = clean_series(3) + [candle(off_grid)]
    issues = validate_candle_series(series, "5m")
    types = {i["type"] for i in issues}
    assert "misaligned_timestamp" in types


def test_outside_market_hours_detected():
    sunday = datetime(2026, 8, 16, 5, 0, tzinfo=UTC)  # Sunday IST
    issues = validate_candle_series([candle(sunday)], "5m")
    types = {i["type"] for i in issues}
    assert "outside_market_hours" in types


def test_daily_interval_skips_intraday_checks():
    daily = datetime(2026, 8, 16, 0, 0, tzinfo=UTC)  # Sunday is fine for 1d bars
    assert validate_candle_series([candle(daily)], "1d") == []


def test_missing_candles_report():
    start = datetime(2026, 8, 10, 3, 45, tzinfo=UTC)  # Monday
    end = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
    partial = clean_series(n=50, start=start)  # only 50 of 75 expected
    report = missing_candles_report(partial, start, end, "5m")
    assert report["expected_bars"] == 75
    assert report["actual_unique_bars"] == 50
    assert report["missing_bars"] == 25
    assert report["status"] in {"warning", "critical"}

    full = clean_series(n=75, start=start)
    ok = missing_candles_report(full, start, end, "5m")
    assert ok["status"] == "healthy"
