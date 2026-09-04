"""Tests for options backtest engine (AlgoTest-parity)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.backtest.options_engine import OptionsBacktestError, run_options_backtest
from app.marketdata.base import Candle
from app.quant.schema import (
    InstrumentRef,
    LegwiseSettings,
    OptionLeg,
    OverallConfig,
    StrategyDefinition,
    TimeControlConfig,
)

T0 = datetime(2026, 6, 1, 9, 15, tzinfo=UTC)


def make_candles(closes: list[float]) -> list[Candle]:
    candles = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev if i > 0 else c
        hi = max(o, c)
        lo = min(o, c)
        candles.append(Candle(
            timestamp=T0 + timedelta(minutes=5 * i),
            instrument_id="NIFTY", open=o, high=hi, low=lo, close=c, volume=1000, oi=5000,
        ))
        prev = c
    return candles


def _def(legs: list[OptionLeg], **kwargs) -> StrategyDefinition:
    return StrategyDefinition(
        version=1, timeframe="5m",
        instrument=InstrumentRef(symbol="NIFTY", exchange="NSE", segment="options"),
        entry={"logic": "ALL", "conditions": [{"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "constant", "value": 0}}]},
        legs=legs, **kwargs,
    )


class TestOptionsEngineBasic:
    def test_basic_long_call(self):
        candles = make_candles([22000, 22100, 22200, 22300, 22400, 22500, 22600])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1
        assert "net_pnl" in result.summary

    def test_basic_long_put(self):
        candles = make_candles([22000, 21900, 21800, 21700, 21600])
        legs = [OptionLeg(action="buy", option_type="PE", strike_offset=0, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_short_straddle(self):
        candles = make_candles([22000, 22050, 22000, 21950, 22000, 22050, 22000])
        legs = [
            OptionLeg(action="sell", option_type="CE", strike_offset=0, lots=1),
            OptionLeg(action="sell", option_type="PE", strike_offset=0, lots=1),
        ]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 2

    def test_iron_condor(self):
        candles = make_candles([22000] * 10)
        legs = [
            OptionLeg(action="sell", option_type="CE", strike_offset=1, lots=1),
            OptionLeg(action="buy", option_type="CE", strike_offset=2, lots=1),
            OptionLeg(action="sell", option_type="PE", strike_offset=-1, lots=1),
            OptionLeg(action="buy", option_type="PE", strike_offset=-2, lots=1),
        ]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 4

    def test_requires_candles(self):
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1)]
        with pytest.raises(OptionsBacktestError):
            run_options_backtest(_def(legs), [])

    def test_requires_at_least_one_leg(self):
        candles = make_candles([22000] * 5)
        with pytest.raises(OptionsBacktestError):
            run_options_backtest(_def([]), candles)


class TestPerLegSL:
    def test_sl_pts_triggers(self):
        candles = make_candles([22000, 22050, 21900, 21800, 21700])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1, sl_mode="pts", sl_value=20)]
        result = run_options_backtest(_def(legs), candles)
        sl_trades = [t for t in result.trades if t.exit_reason == "stop_loss"]
        assert len(sl_trades) >= 1

    def test_sl_pct_triggers(self):
        candles = make_candles([22000, 22100, 21800, 21700])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1, sl_mode="%", sl_value=30)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_target_pts_triggers(self):
        candles = make_candles([22000, 22300, 22500, 22600])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1, target_mode="pts", target_value=200)]
        result = run_options_backtest(_def(legs), candles)
        tgt_trades = [t for t in result.trades if t.exit_reason == "target"]
        assert len(tgt_trades) >= 1

    def test_target_pct_triggers(self):
        candles = make_candles([22000, 22300, 22500])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1, target_mode="%", target_value=50)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1


class TestTrailSL:
    def test_trail_sl_pts(self):
        candles = make_candles([22000, 22100, 22200, 22150, 22050])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1,
                          sl_mode="pts", sl_value=50, trail_mode="pts", trail_step=30, trail_by=60)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1


class TestReEntry:
    def test_reentry_asap(self):
        candles = make_candles([22000, 22100, 21800, 22200, 22300])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1,
                          sl_mode="pts", sl_value=30, reentry_on_sl="asap", max_reentries=2)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 2


class TestOverallSettings:
    def test_overall_sl(self):
        candles = make_candles([22000, 22100, 21800, 21600, 21500])
        legs = [
            OptionLeg(action="sell", option_type="CE", strike_offset=0, lots=1),
            OptionLeg(action="sell", option_type="PE", strike_offset=0, lots=1),
        ]
        overall = OverallConfig(overall_sl=2000)
        result = run_options_backtest(_def(legs, overall=overall), candles)
        assert result.summary["total_trades"] >= 2

    def test_overall_target(self):
        candles = make_candles([22000, 21800, 21600, 21500, 21400])
        legs = [
            OptionLeg(action="sell", option_type="CE", strike_offset=0, lots=1),
            OptionLeg(action="sell", option_type="PE", strike_offset=0, lots=1),
        ]
        overall = OverallConfig(overall_target=3000)
        result = run_options_backtest(_def(legs, overall=overall), candles)
        assert result.summary["total_trades"] >= 2


class TestTimeControls:
    def test_force_exit(self):
        candles = make_candles([22000, 22100, 22200, 22300, 22400, 22500, 22600, 22700, 22800, 22900,
                                23000, 23100, 23200, 23300, 23400, 23500, 23600, 23700, 23800, 23900,
                                24000, 24100, 24200, 24300, 24400, 24500, 24600, 24700, 24800, 24900,
                                25000, 25100, 25200, 25300, 25400, 25500])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1)]
        tc = TimeControlConfig(time_exit="09:20")
        result = run_options_backtest(_def(legs, time_control=tc), candles)
        time_exits = [t for t in result.trades if t.exit_reason == "time_exit"]
        assert len(time_exits) >= 1


class TestSquareOff:
    def test_square_off_complete(self):
        candles = make_candles([22000, 22100, 21800, 21700, 21600])
        legs = [
            OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1, sl_mode="pts", sl_value=50, square_off="complete"),
            OptionLeg(action="buy", option_type="PE", strike_offset=0, lots=1),
        ]
        lw = LegwiseSettings(trail_sl_to_breakeven="none", square_off_on_leg_sl=True)
        result = run_options_backtest(_def(legs, legwise=lw), candles)
        assert result.summary["total_trades"] >= 2


class TestSummary:
    def test_summary_fields(self):
        candles = make_candles([22000, 22100, 22200, 22300, 22400])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        s = result.summary
        assert "initial_capital" in s
        assert "final_equity" in s
        assert "net_pnl" in s
        assert "return_pct" in s
        assert "total_trades" in s
        assert "win_rate" in s
        assert "max_drawdown_pct" in s

    def test_equity_curve_length(self):
        candles = make_candles([22000, 22100, 22200, 22300])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert len(result.equity_curve) == len(candles)

    def test_trades_have_as_dict(self):
        candles = make_candles([22000, 22100, 21800, 21700])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1, sl_mode="pts", sl_value=30)]
        result = run_options_backtest(_def(legs), candles)
        for t in result.trades:
            d = t.as_dict()
            assert "leg_index" in d
            assert "entry_time" in d
            assert "exit_time" in d


class TestStrikeSelection:
    def test_strike_formula_atm(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_formula="ATM", lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_strike_formula_delta(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_formula="DELTA:0.20", lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_strike_selection_closest_premium(self):
        candles = make_candles([22000, 22100, 22200, 22300])
        legs = [OptionLeg(action="buy", option_type="CE", strike_selection="closest_premium", strike_selection_value=50, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_strike_selection_delta_range(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_selection="delta_range", strike_selection_value=0.10, strike_selection_value_2=0.30, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1


class TestRangeBreakout:
    def test_range_breakout_entry(self):
        candles = make_candles([22000]*5 + [22050]*3 + [22100]*5)
        legs = [OptionLeg(action="buy", option_type="CE", lots=1)]
        rb = {"start_time": "09:15", "end_time": "09:20", "entry_on": "high"}
        result = run_options_backtest(_def(legs, range_breakout=rb), candles)
        assert result.summary["total_trades"] >= 1


class TestReExecuteReentry:
    def test_reexecute_on_sl(self):
        candles = make_candles([22000, 22100, 21800, 22200, 22300])
        legs = [OptionLeg(action="buy", option_type="CE", strike_offset=0, lots=1,
                          sl_mode="pts", sl_value=30, reentry_on_sl="reexecute", max_reentries=1)]
        overall = OverallConfig(overall_sl=5000, overall_reentry_on_sl="reexecute")
        result = run_options_backtest(_def(legs, overall=overall), candles)
        assert result.summary["total_trades"] >= 1


class TestStrikeTypeAndSynthetic:
    def test_strike_type_itm(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_selection="strike_type", strike_offset=1, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_strike_type_otm(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_selection="strike_type", strike_offset=2, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1

    def test_synthetic_future(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_selection="synthetic_future", lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1


class TestClosestDelta:
    def test_closest_delta_search(self):
        candles = make_candles([22000, 22100, 22200])
        legs = [OptionLeg(action="buy", option_type="CE", strike_selection="closest_delta", strike_selection_value=0.20, lots=1)]
        result = run_options_backtest(_def(legs), candles)
        assert result.summary["total_trades"] >= 1


class TestRangeBreakoutReentry:
    def test_range_breakout_reentry_on_sl(self):
        candles = make_candles([22000]*5 + [22050]*3 + [22100]*5 + [22050]*3 + [22200]*5)
        legs = [OptionLeg(action="buy", option_type="CE", lots=1,
                          sl_mode="pts", sl_value=30, reentry_on_sl="range_breakout", max_reentries=1)]
        rb = {"start_time": "09:15", "end_time": "09:20", "entry_on": "high"}
        result = run_options_backtest(_def(legs, range_breakout=rb), candles)
        assert result.summary["total_trades"] >= 1


class TestOptionsBacktestEndpoint:
    async def test_options_backtest_endpoint(self, client):
        payload = {
            "underlying": "NIFTY",
            "legs": [
                {
                    "action": "buy",
                    "option_type": "CE",
                    "strike_selection": "closest_premium",
                    "strike_selection_value": 50,
                    "lots": 1,
                }
            ],
            "initial_capital": 100000,
            "volatility": 0.2,
        }
        resp = await client.post("/api/v1/options/backtest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "legs" in data
        assert "daily_values" in data
        assert "cost_breakdown" in data
