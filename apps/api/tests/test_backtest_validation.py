"""In/Out-of-Sample validation.

The property that matters is discrimination: a strategy whose edge exists only
in the first half must be reported as such, and one whose edge persists must
not be. Tests assert both directions, plus the warm-up behaviour, because an
OOS number that cannot tell those apart is worse than no number.
"""

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from app.backtest.engine import BacktestConfig
from app.backtest.validation import (
    MIN_SEGMENT_BARS,
    ValidationError,
    required_warmup_bars,
    run_split_backtest,
    to_payload,
)
from app.marketdata.base import Candle
from app.quant.schema import (
    ConditionGroup,
    IndicatorDef,
    InstrumentRef,
    PositionConfig,
    StrategyDefinition,
)


def make_candles(n: int, drift_first: float = 0.0, drift_second: float = 0.0,
                 noise: float = 1.0, seed: int = 7, cycles: int = 8,
                 start=datetime(2026, 1, 1, tzinfo=UTC)) -> list[Candle]:
    """Build a trending series whose two halves can drift differently.

    That asymmetry is the whole point: it lets a test build a strategy that only
    works in-sample and assert the split notices.

    The path is a seeded PRNG walk around a slow sine trend rather than a pure
    random walk. A pure walk makes an EMA crossover fire once or not at all, so
    the strategy trades 0-1 times and there is no edge to generalise or lose -
    the test then passes or fails for reasons unrelated to overfitting. The
    oscillation also gives the crossover something to repeatedly catch, so the
    OOS leg holds real trades and the comparison is meaningful.
    """
    rng = random.Random(seed)
    out: list[Candle] = []
    price = 100.0
    for i in range(n):
        drift = drift_first if i < n // 2 else drift_second
        trend = 1.5 * (math.sin(2 * math.pi * i / (n / cycles)) + 1)
        price = max(price + drift + trend / 20 + rng.gauss(0.0, noise), 1.0)
        out.append(
            Candle(
                timestamp=start + timedelta(minutes=i),
                instrument_id="NIFTY",
                open=price,
                high=price + abs(noise) / 2,
                low=max(price - abs(noise) / 2, 0.5),
                close=price,
                volume=1000,
            )
        )
    return out


def crossover_definition() -> StrategyDefinition:
    return StrategyDefinition(
        version=1,
        timeframe="1m",
        instrument=InstrumentRef(symbol="NIFTY", segment="index"),
        indicators=[
            IndicatorDef(id="fast", type="EMA", params={"length": 5}),
            IndicatorDef(id="slow", type="EMA", params={"length": 20}),
        ],
        entry=ConditionGroup(
            logic="ALL",
            conditions=[
                {
                    "left": {"kind": "indicator", "ref": "fast"},
                    "op": "CROSS_ABOVE",
                    "right": {"kind": "indicator", "ref": "slow"},
                }
            ],
        ),
        position=PositionConfig(),
    )


# --- warm-up derivation -----------------------------------------------------


def test_warmup_follows_longest_lookback():
    d = crossover_definition()  # EMA 5 and EMA 20
    assert required_warmup_bars(d) == 20


def test_warmup_grows_with_a_longer_indicator():
    d = crossover_definition()
    d.indicators.append(IndicatorDef(id="long", type="SMA", params={"length": 100}))
    assert required_warmup_bars(d) == 100


def test_warmup_is_zero_without_indicators():
    d = crossover_definition()
    d.indicators = []
    assert required_warmup_bars(d) == 0


def test_warmup_accounts_for_rate_of_change_indicators():
    d = crossover_definition()
    d.indicators = [IndicatorDef(id="roc", type="ROC", params={"length": 14})]
    # 14 lookback plus 2 bars to difference.
    assert required_warmup_bars(d) == 16


# --- guards -----------------------------------------------------------------


def test_too_few_candles_rejected():
    d = crossover_definition()
    with pytest.raises(ValidationError, match="at least"):
        run_split_backtest(d, make_candles(MIN_SEGMENT_BARS))


@pytest.mark.parametrize("split", [0.0, 0.05, 0.95, 1.0])
def test_out_of_range_split_rejected(split):
    d = crossover_definition()
    with pytest.raises(ValidationError, match="between 0.1 and 0.9"):
        run_split_backtest(d, make_candles(400), split=split)


def test_split_boundaries_accepted():
    d = crossover_definition()
    candles = make_candles(400)
    for split in (0.1, 0.5, 0.9):
        result = run_split_backtest(d, candles, split=split)
        assert result.in_sample.summary and result.out_of_sample.summary


# --- split mechanics --------------------------------------------------------


def test_segments_partition_the_history():
    d = crossover_definition()
    candles = make_candles(400)
    result = run_split_backtest(d, candles, split=0.7)
    assert result.split_index == 280
    # Each leg's equity curve must cover its own window only.
    assert len(result.in_sample.equity_curve) <= 280
    assert len(result.out_of_sample.equity_curve) <= 120


def test_oos_equity_curve_excludes_warmup_bars():
    """The OOS window must be exactly the unseen bars, not the context bars.

    If warm-up leaked into the OOS curve, the OOS return would be measured
    partly on data the strategy was fitted to - the exact illusion this feature
    exists to remove.
    """
    d = crossover_definition()
    candles = make_candles(400)
    result = run_split_backtest(d, candles, split=0.7)
    oos_bars = len(candles) - result.split_index
    assert result.warmup_bars > 0, "expected warm-up for EMA20"
    assert len(result.out_of_sample.equity_curve) <= oos_bars


def test_window_timestamps_are_ordered():
    d = crossover_definition()
    result = run_split_backtest(d, make_candles(400))
    assert result.is_start < result.is_end
    assert result.is_end <= result.oos_start
    assert result.oos_start < result.oos_end


def test_oos_never_looks_before_the_split():
    """Every OOS trade must be entered on or after the split bar."""
    d = crossover_definition()
    candles = make_candles(400)
    result = run_split_backtest(d, candles, split=0.7)
    boundary = candles[result.split_index].timestamp
    for trade in result.out_of_sample.trades:
        entry = trade.entry_time
        if not isinstance(entry, datetime):
            entry = datetime.fromisoformat(str(entry))
        assert entry >= boundary, f"trade entered before split: {entry} < {boundary}"


# --- discrimination: the whole reason this exists --------------------------


def test_strategy_that_only_works_in_sample_is_flagged():
    """Rising first half, falling second half: OOS must not read as profitable."""
    d = crossover_definition()
    candles = make_candles(600, drift_first=0.35, drift_second=-0.30)
    result = run_split_backtest(d, candles, BacktestConfig(initial_capital=100_000))
    deg = result.degradation
    assert deg["is_return_pct"] > 0, "precondition: IS should be profitable"
    assert deg["oos_is_profitable"] is False, "OOS edge did not survive"
    assert deg["oos_return_pct"] < deg["is_return_pct"]


def test_strategy_that_generalises_keeps_a_positive_oos():
    """A steady trend in both halves should survive the split."""
    d = crossover_definition()
    candles = make_candles(600, drift_first=0.15, drift_second=0.15)
    result = run_split_backtest(d, candles, BacktestConfig(initial_capital=100_000))
    deg = result.degradation
    assert deg["oos_is_profitable"] is True
    assert deg["efficiency_ratio"] is None or deg["efficiency_ratio"] > 0


def test_degradation_reports_return_delta_consistently():
    d = crossover_definition()
    result = run_split_backtest(d, make_candles(400))
    deg = result.degradation
    expected = deg["oos_return_pct"] - deg["is_return_pct"]
    assert deg["return_delta_pct"] == pytest.approx(expected, abs=0.01)


def test_efficiency_ratio_undefined_when_in_sample_is_flat():
    """A no-trade in-sample leg makes efficiency meaningless, not infinite."""
    d = crossover_definition()
    flat = make_candles(400, noise=0.0)
    result = run_split_backtest(d, flat, BacktestConfig(initial_capital=100_000))
    assert result.degradation["efficiency_ratio"] is None


# --- serialisation ----------------------------------------------------------


def test_payload_shape():
    d = crossover_definition()
    payload = to_payload(run_split_backtest(d, make_candles(400)))
    assert set(payload) >= {"split_index", "split_time", "warmup_bars", "windows", "degradation"}
    assert set(payload["windows"]) == {"in_sample", "out_of_sample"}
    assert set(payload["windows"]["in_sample"]) == {"start", "end", "summary"}
    assert "return_pct" in payload["windows"]["out_of_sample"]["summary"]
    assert "oos_sharpe" in payload["degradation"]


def test_payload_is_json_serialisable():
    import json

    d = crossover_definition()
    json.dumps(to_payload(run_split_backtest(d, make_candles(400))))


# --- performance characteristics -------------------------------------------


def test_does_not_mutate_the_input_definition():
    d = crossover_definition()
    before = d.model_dump()
    run_split_backtest(d, make_candles(400))
    assert d.model_dump() == before


def test_does_not_mutate_the_input_candles():
    d = crossover_definition()
    candles = make_candles(400)
    snapshot = [(c.timestamp, c.close) for c in candles]
    run_split_backtest(d, candles)
    assert [(c.timestamp, c.close) for c in candles] == snapshot
