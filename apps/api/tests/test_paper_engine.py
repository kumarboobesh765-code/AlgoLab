"""Unit tests for the incremental paper execution engine."""

from datetime import UTC, datetime, timedelta

from app.marketdata.base import Candle
from app.paper import required_warmup, step_paper
from app.quant.schema import StrategyDefinition

T0 = datetime(2026, 8, 3, 9, 15, tzinfo=UTC)

SERIES = [
    100, 100, 100, 100, 100,
    104, 108, 112,
    110, 106, 102,
    98, 96,
    100, 104, 108,
]


def make_candles(closes: list[float], spread: float = 0.5) -> list[Candle]:
    candles = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev if i > 0 else c
        candles.append(
            Candle(
                timestamp=T0 + timedelta(minutes=5 * i),
                instrument_id="TEST",
                open=o,
                high=max(o, c) + spread / 2,
                low=min(o, c) - spread / 2,
                close=c,
            )
        )
        prev = c
    return candles


def cross_def(**overrides) -> dict:
    d = {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "TEST"},
        "indicators": [
            {"id": "f", "type": "SMA", "params": {"length": 2}},
            {"id": "s", "type": "SMA", "params": {"length": 4}},
        ],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "s"}}
            ],
        },
        "exit": {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "s"}}
            ],
        },
        "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
    }
    d.update(overrides)
    return d


async def test_signal_seen_in_first_tick_carries_to_next():
    """Live-like: first tick processes up to signal bar, second tick fills at next open."""
    definition = StrategyDefinition.model_validate(cross_def())
    candles = make_candles(SERIES)
    # Tick 1: process bars 0..5 (signal bar i5 is included)
    r1 = step_paper(definition, [], candles[:6], None, None, cash=100_000, costs_pct=0.0)
    assert r1.pending_action == "entry_long"
    assert r1.actions == []
    # Tick 2: history is bars 0..5, new bar is i6 — fills at i6.open
    r2 = step_paper(definition, candles[:6], candles[6:7], r1.position, r1.pending_action, cash=100_000, costs_pct=0.0)
    entries = [a for a in r2.actions if a.reason == "entry"]
    assert len(entries) == 1
    assert entries[0].price == candles[6].open
    assert r2.position is not None
    assert r2.position["direction"] == "long"


async def test_full_cycle_continuous_ticks():
    definition = StrategyDefinition.model_validate(cross_def())
    candles = make_candles(SERIES)
    position = None
    pending = None
    history = []
    fills = []
    # Feed sequentially in live-sized chunks
    for batch in (candles[:6], candles[6:11], candles[11:]):
        step = step_paper(definition, history, batch, position, pending, cash=100_000, costs_pct=0.0)
        fills.extend(step.actions)
        position = step.position
        pending = step.pending_action
        history = history + list(batch)
    entries = [f for f in fills if f.reason == "entry"]
    exits = [f for f in fills if f.reason != "entry"]
    assert len(entries) >= 1
    assert exits, "expected an exit fill across the down-leg"
    assert exits[0].side == "SELL"
    # Second up-leg produces a re-entry — final position may be open; that's fine.


async def test_stop_loss_intrabar():
    d = cross_def(risk={"stop_loss_pct": 5.0})
    closes = [100, 100, 100, 100, 100, 102, 104, 106, 108, 80, 79]
    definition = StrategyDefinition.model_validate(d)
    hist = make_candles(closes[:6])
    r1 = step_paper(definition, [], hist, None, None, 100_000, 0.0)
    rest = step_paper(definition, hist, make_candles(closes)[6:], r1.position, r1.pending_action, 100_000, 0.0)
    stops = [a for a in rest.actions if a.reason in ("stop_loss", "trailing_stop")]
    assert stops and stops[0].pnl < 0


async def test_trailing_stop_locks_profit():
    d = cross_def(risk={"trailing_sl_pct": 1.0})
    closes = [100, 100, 100, 100, 100, 104, 108, 112, 116, 120, 124, 128, 120, 116]
    definition = StrategyDefinition.model_validate(d)
    hist = make_candles(closes[:6], spread=0.1)
    r1 = step_paper(definition, [], hist, None, None, 100_000, 0.0)
    rest = step_paper(definition, hist, make_candles(closes, spread=0.1)[6:], r1.position, r1.pending_action, 100_000, 0.0)
    trails = [a for a in rest.actions if a.reason == "trailing_stop"]
    assert trails and trails[0].pnl > 0


async def test_short_only_opposes():
    d = cross_def(position={"quantity_type": "fixed", "quantity": 10, "direction": "short_only"})
    definition = StrategyDefinition.model_validate(d)
    candles = make_candles(SERIES)
    position = None
    pending = None
    history = []
    sides = []
    for batch in (candles[:6], candles[6:12], candles[12:]):
        step = step_paper(definition, history, batch, position, pending, cash=100_000, costs_pct=0.0)
        sides.extend(a.side for a in step.actions if a.reason == "entry")
        position = step.position
        pending = step.pending_action
        history = history + list(batch)
    assert sides and all(s == "SELL" for s in sides)


async def test_both_mode_reverses():
    d = cross_def(position={"quantity_type": "fixed", "quantity": 10, "direction": "both"})
    definition = StrategyDefinition.model_validate(d)
    candles = make_candles(SERIES)
    position = None
    pending = None
    history = []
    actions = []
    for batch in (candles[:6], candles[6:12], candles[12:]):
        step = step_paper(definition, history, batch, position, pending, cash=100_000, costs_pct=0.0)
        actions.extend(step.actions)
        position = step.position
        pending = step.pending_action
        history = history + list(batch)
    reasons = [a.reason for a in actions]
    assert "entry" in reasons
    shorts = [a for a in actions if a.side == "SELL" and a.reason == "entry"]
    assert shorts, "expected reverse short entry"


async def test_costs_reflected_in_pnl():
    definition = StrategyDefinition.model_validate(cross_def())
    candles = make_candles(SERIES)
    position = None
    pending = None
    history = []
    pnl = 0.0
    for batch in (candles[:6], candles[6:12], candles[12:]):
        step = step_paper(definition, history, batch, position, pending, cash=100_000, costs_pct=0.5)
        for a in step.actions:
            if a.pnl is not None:
                pnl += a.pnl
        position = step.position
        pending = step.pending_action
        history = history + list(batch)
    free_pnl = 0.0
    position = None
    pending = None
    history = []
    for batch in (candles[:6], candles[6:12], candles[12:]):
        step = step_paper(definition, history, batch, position, pending, cash=100_000, costs_pct=0.0)
        for a in step.actions:
            if a.pnl is not None:
                free_pnl += a.pnl
        position = step.position
        pending = step.pending_action
        history = history + list(batch)
    assert pnl < free_pnl


async def test_empty_new_batch_is_noop():
    definition = StrategyDefinition.model_validate(cross_def())
    result = step_paper(definition, [], [], None, "entry_long", cash=100_000, costs_pct=0.03)
    assert result.actions == []
    assert result.pending_action == "entry_long"


async def test_required_warmup():
    definition = StrategyDefinition.model_validate(cross_def())
    # max param is 4, but starts at base 5, so 5*3=15
    assert required_warmup(definition) == 15
    d = cross_def()
    d["indicators"].append({"id": "m", "type": "SMA", "params": {"length": 200}})
    assert required_warmup(StrategyDefinition.model_validate(d)) == 500  # 200*3=600 capped
