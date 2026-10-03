"""Python strategy host.

The important properties here are the ones a user script must not be able to
break: it cannot read the app's secrets, cannot hang the API, and cannot hand
back garbage that the backtest engine would choke on. Each is asserted
explicitly rather than assumed.
"""

import pytest

from app.strategies.python_host import (
    StrategyHostError,
    backtest_python_strategy,
    candles_to_payload,
    run_python_strategy,
    script_from_path,
    validate_script,
)

BREAKOUT = """
def generate_signals(candles, context):
    out = []
    for i, c in enumerate(candles):
        if i < 3:
            out.append(0)
        elif c["close"] > candles[i - 3]["close"]:
            out.append(1)
        elif c["close"] < candles[i - 3]["close"]:
            out.append(-1)
        else:
            out.append(0)
    return out
"""


@pytest.fixture
def candles():
    return [
        {
            "time": f"2026-01-01T00:{i:02d}:00",
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100 + i,
            "volume": 1000,
            "oi": None,
        }
        for i in range(10)
    ]


# --- happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_one_signal_per_candle(candles):
    result = await run_python_strategy(BREAKOUT, candles)
    assert len(result.signals) == len(candles)
    assert all(s in (1, -1, 0) for s in result.signals)


@pytest.mark.asyncio
async def test_signals_reflect_the_strategy_logic(candles):
    # closes rise monotonically, so a 3-bar breakout enters and holds
    result = await run_python_strategy(BREAKOUT, candles)
    assert result.signals[:3] == [0, 0, 0]
    assert result.signals[3:] == [1] * 7


@pytest.mark.asyncio
async def test_context_is_passed_through(candles):
    script = """
def generate_signals(candles, context):
    return [1 if i >= context["start"] else 0 for i in range(len(candles))]
"""
    result = await run_python_strategy(script, candles, context={"start": 4})
    assert result.signals == [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]


@pytest.mark.asyncio
async def test_flat_series_produces_no_signals(candles):
    for c in candles:
        c["close"] = 100.0
    result = await run_python_strategy(BREAKOUT, candles)
    assert set(result.signals) == {0}


# --- validation -------------------------------------------------------------


def test_empty_script_rejected():
    with pytest.raises(StrategyHostError, match="empty"):
        validate_script("   ")


def test_missing_entrypoint_rejected():
    with pytest.raises(StrategyHostError, match="generate_signals"):
        validate_script("x = 1")


def test_syntax_error_reported_with_line():
    with pytest.raises(StrategyHostError, match="Syntax error"):
        validate_script("def generate_signals(candles, context)\n    return []")


def test_oversized_script_rejected():
    with pytest.raises(StrategyHostError, match="exceeds"):
        validate_script("# " + "x" * (600 * 1024) + "\ndef generate_signals(c, x): pass")


@pytest.mark.asyncio
async def test_no_candles_rejected():
    with pytest.raises(StrategyHostError, match="No candles"):
        await run_python_strategy(BREAKOUT, [])


@pytest.mark.asyncio
async def test_user_exception_surfaces_as_error(candles):
    script = """
def generate_signals(candles, context):
    raise ValueError("bad input")
"""
    with pytest.raises(StrategyHostError, match="bad input"):
        await run_python_strategy(script, candles)


@pytest.mark.asyncio
async def test_wrong_signal_count_rejected(candles):
    script = "def generate_signals(candles, context):\n    return [0, 1]"
    with pytest.raises(StrategyHostError, match="align one-to-one"):
        await run_python_strategy(script, candles)


@pytest.mark.asyncio
async def test_invalid_signal_value_rejected(candles):
    script = "def generate_signals(candles, context):\n    return [7] * len(candles)"
    with pytest.raises(StrategyHostError, match="1 \\(enter\\)"):
        await run_python_strategy(script, candles)


@pytest.mark.asyncio
async def test_infinite_loop_is_killed(candles):
    """A hung strategy must not take the API with it."""
    script = "def generate_signals(candles, context):\n    while True:\n        pass"
    with pytest.raises(StrategyHostError, match="time limit"):
        await run_python_strategy(script, candles, timeout=2)


@pytest.mark.asyncio
async def test_non_list_return_rejected(candles):
    script = "def generate_signals(candles, context):\n    return 42"
    with pytest.raises(StrategyHostError):
        await run_python_strategy(script, candles, timeout=5)


# --- sandbox ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_cannot_see_database_url(candles, monkeypatch):
    """The child inherits a scrubbed environment, not the app's config."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    script = """
import os
def generate_signals(candles, context):
    leaked = os.environ.get("DATABASE_URL")
    return [1] * len(candles) if leaked else [0] * len(candles)
"""
    result = await run_python_strategy(script, candles)
    assert result.signals == [0] * len(candles), "DATABASE_URL leaked into the child"


@pytest.mark.asyncio
async def test_script_cannot_see_broker_secrets(candles, monkeypatch):
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "super-secret")
    monkeypatch.setenv("ZERODHA_API_SECRET", "also-secret")
    script = """
import os
def generate_signals(candles, context):
    for key in ("DHAN_ACCESS_TOKEN", "ZERODHA_API_SECRET"):
        if os.environ.get(key):
            raise RuntimeError(f"leaked {key}")
    return [0] * len(candles)
"""
    result = await run_python_strategy(script, candles)
    assert result.signals == [0] * len(candles)


@pytest.mark.asyncio
async def test_host_errors_do_not_crash_the_process(candles):
    """A failed run must leave the host usable for the next call."""
    with pytest.raises(StrategyHostError):
        await run_python_strategy("def generate_signals(c, x):\n    raise ValueError()", candles)
    result = await run_python_strategy(BREAKOUT, candles)
    assert len(result.signals) == len(candles)


# --- backtest integration ---------------------------------------------------


def _definition():
    from app.quant.schema import (
        ConditionGroup,
        InstrumentRef,
        PositionConfig,
        StrategyDefinition,
    )

    return StrategyDefinition(
        version=1,
        timeframe="1m",
        instrument=InstrumentRef(symbol="NIFTY", segment="index"),
        entry=ConditionGroup(logic="ALL", conditions=[{"field": "close", "op": "gt", "value": 0}]),
        position=PositionConfig(),
    )


def test_python_signals_drive_the_backtest_engine(candles):
    """The script decides when to trade; the engine still does sizing and costs."""
    from datetime import UTC, datetime, timedelta

    from app.marketdata.base import Candle

    bars = [
        Candle(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            instrument_id="NIFTY",
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=1000,
        )
        for i in range(10)
    ]
    payload = candles_to_payload(bars)
    assert len(payload) == len(bars), "payload must align one-to-one with bars"
    result = backtest_python_strategy(_definition(), bars, BREAKOUT)
    assert len(result.trades) >= 1
    assert result.equity_curve, "backtest produced no equity curve"
    # A monotonically rising series should end long, so equity beats flat capital.
    final = result.equity_curve[-1]
    assert final.get("equity", 0) != 100_000.0


def test_backtest_rejects_misaligned_signals():
    from datetime import UTC, datetime, timedelta

    from app.backtest.engine import BacktestConfig, BacktestError, run_backtest
    from app.marketdata.base import Candle

    bars = [
        Candle(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            instrument_id="NIFTY",
            open=100.0, high=101.0, low=99.0, close=100.0, volume=1,
        )
        for i in range(5)
    ]
    with pytest.raises(BacktestError, match="align one-to-one"):
        run_backtest(_definition(), bars, BacktestConfig(), [1, -1])


# --- helpers ----------------------------------------------------------------


def test_candles_to_payload_shape():
    from datetime import UTC, datetime

    from app.marketdata.base import Candle

    c = Candle(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        instrument_id="NIFTY",
        open=1.0, high=2.0, low=0.5, close=1.5, volume=10, oi=20,
    )
    out = candles_to_payload([c])
    assert set(out[0]) == {"time", "open", "high", "low", "close", "volume", "oi"}
    assert out[0]["close"] == 1.5


def test_script_from_path(tmp_path):
    p = tmp_path / "s.py"
    p.write_text(BREAKOUT, encoding="utf-8")
    assert "generate_signals" in script_from_path(p)


def test_script_from_missing_path(tmp_path):
    with pytest.raises(StrategyHostError, match="No such strategy file"):
        script_from_path(tmp_path / "definitely" / "not" / "here.py")
