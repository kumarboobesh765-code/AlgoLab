"""Data-quality validation for candle series (spec §68).

Pure functions over normalized candle rows so they are trivially testable and
reusable by both the ingestion pipeline and the /data/quality API.
"""

from collections import Counter
from datetime import UTC, datetime, time, timedelta, timezone

from app.marketdata.base import Candle

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}

EPSILON = 1e-6


def ensure_utc(ts: datetime) -> datetime:
    """DB reads may return naive datetimes; they are always written as UTC."""
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _issue(issues: list[dict], kind: str, detail: str, examples: list[str]) -> None:
    issues.append({"type": kind, "detail": detail, "examples": examples[:3]})


def validate_candle_series(
    candles: list[Candle],
    interval: str,
    jump_threshold_pct: float = 10.0,
    check_market_hours: bool = True,
) -> list[dict]:
    """Return a list of issue dicts; empty list means the series is clean."""
    issues: list[dict] = []
    if not candles:
        return [{"type": "empty", "detail": "No candles in range", "examples": []}]

    # 1. Invalid OHLC relationships / non-positive prices
    bad_ohlc = [
        f"{c.timestamp.isoformat()} H={c.high} L={c.low} O={c.open} C={c.close}"
        for c in candles
        if c.open <= 0
        or c.high <= 0
        or c.low <= 0
        or c.close <= 0
        or c.high < c.low - EPSILON
        or c.high < max(c.open, c.close) - EPSILON
        or c.low > min(c.open, c.close) + EPSILON
    ]
    if bad_ohlc:
        _issue(issues, "invalid_ohlc", f"{len(bad_ohlc)} candles violate OHLC rules", bad_ohlc)

    # 2. Duplicate timestamps
    counts = Counter(c.timestamp for c in candles)
    dupes = [ts.isoformat() for ts, n in counts.items() if n > 1]
    if dupes:
        _issue(issues, "duplicate_timestamp", f"{len(dupes)} duplicated timestamps", dupes)

    # 3. Abnormal price jumps between consecutive closes
    ordered = sorted(candles, key=lambda c: c.timestamp)
    jumps = []
    for prev, cur in zip(ordered, ordered[1:]):
        if prev.close > 0:
            change_pct = abs(cur.close / prev.close - 1) * 100
            if change_pct > jump_threshold_pct:
                jumps.append(
                    f"{cur.timestamp.isoformat()} {prev.close:.2f}->{cur.close:.2f} "
                    f"({change_pct:.1f}%)"
                )
    if jumps:
        _issue(
            issues,
            "abnormal_jump",
            f"{len(jumps)} moves exceed {jump_threshold_pct}% between closes",
            jumps,
        )

    step = INTERVAL_MINUTES.get(interval)
    if step is not None:
        # 4. Timestamp alignment to interval grid
        misaligned = [
            c.timestamp.isoformat()
            for c in candles
            if (c.timestamp.hour * 60 + c.timestamp.minute - (9 * 60 + 15)) % step != 0
            or c.timestamp.second != 0
        ]
        if misaligned:
            _issue(
                issues,
                "misaligned_timestamp",
                f"{len(misaligned)} timestamps not on the {interval} grid",
                misaligned,
            )

        # 5. Market-hour violations (NSE session, Mon-Fri, IST)
        if check_market_hours:
            outside = []
            for c in candles:
                local = ensure_utc(c.timestamp).astimezone(IST)
                t = local.time()
                if local.weekday() >= 5 or t < MARKET_OPEN or t >= MARKET_CLOSE:
                    outside.append(local.isoformat())
            if outside:
                _issue(
                    issues,
                    "outside_market_hours",
                    f"{len(outside)} timestamps outside NSE hours (09:15-15:30 IST, Mon-Fri)",
                    outside,
                )

    return issues


def expected_bar_count(start: datetime, end: datetime, interval: str) -> int | None:
    """Approximate expected number of bars for NSE sessions in range (intraday only)."""
    step = INTERVAL_MINUTES.get(interval)
    if step is None:
        return None
    minutes_per_day = 375
    bars_per_day = minutes_per_day // step
    days = 0
    day = ensure_utc(start).astimezone(IST).date()
    last = ensure_utc(end).astimezone(IST).date()
    while day <= last:
        if day.weekday() < 5:
            days += 1
        day += timedelta(days=1)
    return days * bars_per_day


def missing_candles_report(
    candles: list[Candle], start: datetime, end: datetime, interval: str
) -> dict | None:
    """Compare actual vs expected bar count for intraday intervals."""
    expected = expected_bar_count(start, end, interval)
    if expected is None or expected == 0:
        return None
    unique_times = len({c.timestamp for c in candles})
    missing = max(expected - unique_times, 0)
    pct = round(missing / expected * 100, 2)
    status = "healthy" if pct < 1.0 else ("warning" if pct < 5.0 else "critical")
    return {
        "expected_bars": expected,
        "actual_unique_bars": unique_times,
        "missing_bars": missing,
        "missing_pct": pct,
        "status": status,
    }
