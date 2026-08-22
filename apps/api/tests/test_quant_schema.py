"""Tests for the condition engine and canonical schema validation."""

from datetime import UTC, datetime, timedelta

import pytest

from app.marketdata.base import Candle
from app.quant.conditions import ConditionError, evaluate_group, validate_condition_node
from app.quant.engine import evaluate_definition
from app.quant.schema import StrategyDefinition, validate_definition

START = datetime(2026, 8, 3, 3, 45, tzinfo=UTC)


def zigzag(n: int = 30) -> list[Candle]:
    candles = []
    ts = START
    for i in range(n):
        close = 100.0 + (5 if (i // 3) % 2 == 0 else -5)
        candles.append(Candle(ts, "T", close, close + 1, close - 1, close, 100))
        ts += timedelta(minutes=1)
    return candles


def ema_def() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [
            {"id": "ema_fast", "type": "EMA", "params": {"length": 3}},
            {"id": "ema_slow", "type": "EMA", "params": {"length": 8}},
        ],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {
                    "left": {"kind": "indicator", "ref": "ema_fast"},
                    "op": "CROSS_ABOVE",
                    "right": {"kind": "indicator", "ref": "ema_slow"},
                }
            ],
        },
    }


class TestConditionValidation:
    def test_valid_condition_passes(self):
        node = {
            "left": {"kind": "price", "price": "close"},
            "op": "GT",
            "right": {"kind": "constant", "value": 10},
        }
        assert validate_condition_node(node, set()) == []

    def test_missing_fields_reported(self):
        errors = validate_condition_node({"left": {"kind": "price", "price": "close"}}, set())
        assert any("missing field" in e for e in errors)

    def test_unknown_operator(self):
        errors = validate_condition_node(
            {
                "left": {"kind": "price", "price": "close"},
                "op": "BETWEEN",
                "right": {"kind": "constant", "value": 1},
            },
            set(),
        )
        assert any("Unknown operator" in e for e in errors)

    def test_unknown_variable(self):
        errors = validate_condition_node(
            {
                "left": {"kind": "variable", "name": "threshold"},
                "op": "LT",
                "right": {"kind": "constant", "value": 1},
            },
            set(),
        )
        assert any("unknown variable" in e for e in errors)

    def test_nested_groups_depth_capped(self):
        deep = {
            "left": {"kind": "price", "price": "close"},
            "op": "GT",
            "right": {"kind": "constant", "value": 1},
        }
        node = deep
        for _ in range(6):
            node = {"logic": "ALL", "conditions": [node]}
        errors = validate_condition_node(node, set())
        assert any("nesting exceeds" in e for e in errors)


class TestConditionEvaluation:
    def test_gt_with_constant(self):
        candles = zigzag()
        cond = {
            "left": {"kind": "price", "price": "close"},
            "op": "GT",
            "right": {"kind": "constant", "value": 100},
        }
        result = evaluate_group(
            {"logic": "ALL", "conditions": [cond]}, candles, {}, {}
        )
        assert all(isinstance(v, bool) for v in result)
        assert any(result)

    def test_cross_above_semantics(self):
        # left crosses above constant 100 exactly once.
        closes = [90.0, 95.0, 99.0, 101.0, 103.0]
        candles = [
            Candle(START + timedelta(minutes=i), "T", c, c, c, c, 0)
            for i, c in enumerate(closes)
        ]
        cond = {
            "left": {"kind": "price", "price": "close"},
            "op": "CROSS_ABOVE",
            "right": {"kind": "constant", "value": 100},
        }
        result = evaluate_group({"logic": "ANY", "conditions": [cond]}, candles, {}, {})
        assert result == [False, False, False, True, False]

    def test_cross_below_touch_does_not_trigger(self):
        closes = [101.0, 100.0, 99.0]  # touch then drop
        candles = [
            Candle(START + timedelta(minutes=i), "T", c, c, c, c, 0)
            for i, c in enumerate(closes)
        ]
        cond = {
            "left": {"kind": "price", "price": "close"},
            "op": "CROSS_BELOW",
            "right": {"kind": "constant", "value": 100},
        }
        result = evaluate_group({"logic": "ANY", "conditions": [cond]}, candles, {}, {})
        assert result == [False, False, True]

    def test_any_vs_all_logic(self):
        candles = zigzag(4)
        c1 = {
            "left": {"kind": "price", "price": "close"},
            "op": "GT",
            "right": {"kind": "constant", "value": 200},
        }
        c2 = {
            "left": {"kind": "price", "price": "close"},
            "op": "GT",
            "right": {"kind": "constant", "value": 90},
        }
        all_res = evaluate_group({"logic": "ALL", "conditions": [c1, c2]}, candles, {}, {})
        any_res = evaluate_group({"logic": "ANY", "conditions": [c1, c2]}, candles, {}, {})
        assert not any(all_res)
        assert all(any_res)

    def test_formula_operand(self):
        candles = zigzag(6)
        cond = {
            "left": {"kind": "formula", "expression": "high - low"},
            "op": "GTE",
            "right": {"kind": "constant", "value": 1},
        }
        result = evaluate_group({"logic": "ALL", "conditions": [cond]}, candles, {}, {})
        assert all(result)

    def test_unknown_indicator_ref_raises_at_eval(self):
        candles = zigzag(5)
        cond = {
            "left": {"kind": "indicator", "ref": "ghost.sma"},
            "op": "GT",
            "right": {"kind": "constant", "value": 1},
        }
        with pytest.raises(ConditionError, match="unknown indicator"):
            evaluate_group({"logic": "ALL", "conditions": [cond]}, candles, {}, {})


class TestSchemaValidation:
    def test_minimal_valid_definition(self):
        errors, warnings = validate_definition(ema_def())
        assert errors == []
        assert warnings == []

    def test_bad_timeframe(self):
        d = ema_def()
        d["timeframe"] = "7m"
        errors, _ = validate_definition(d)
        assert any("timeframe" in e for e in errors)

    def test_duplicate_indicator_ids(self):
        d = ema_def()
        d["indicators"].append({"id": "ema_fast", "type": "SMA"})
        errors, _ = validate_definition(d)
        assert any("Duplicate indicator id" in e for e in errors)

    def test_unknown_indicator_type(self):
        d = ema_def()
        d["indicators"].append({"id": "weird", "type": "MOON_PHASE"})
        errors, _ = validate_definition(d)
        assert any("unknown type" in e for e in errors)

    def test_param_out_of_range(self):
        d = ema_def()
        d["indicators"][0]["params"]["length"] = 0
        errors, _ = validate_definition(d)
        assert any(">= 1" in e for e in errors)

    def test_unused_indicator_warns(self):
        d = ema_def()
        d["indicators"].append({"id": "rsi_extra", "type": "RSI"})
        _, warnings = validate_definition(d)
        assert any("rsi_extra" in w and "never referenced" in w for w in warnings)

    def test_variable_reference_and_warning(self):
        d = ema_def()
        d["variables"] = [{"name": "threshold", "value": 105}]
        d["entry"]["conditions"].append(
            {
                "left": {"kind": "price", "price": "close"},
                "op": "LT",
                "right": {"kind": "variable", "name": "threshold"},
            }
        )
        errors, warnings = validate_definition(d)
        assert errors == []
        assert warnings == []

        d["variables"] = []
        errors, _ = validate_definition(d)
        assert any("unknown variable" in e for e in errors)

    def test_indicator_param_via_variable(self):
        d = ema_def()
        d["variables"] = [{"name": "fast_len", "value": 9}]
        d["indicators"][0]["params"] = {"length": {"var": "fast_len"}}
        errors, _ = validate_definition(d)
        assert errors == []

        d["variables"] = [{"name": "fast_len", "value": 9999}]
        errors, _ = validate_definition(d)
        assert any("<= 500" in e for e in errors)

    def test_invalid_formula_operand(self):
        d = ema_def()
        d["entry"]["conditions"] = [
            {
                "left": {"kind": "formula", "expression": "1 +* 2"},
                "op": "GT",
                "right": {"kind": "constant", "value": 0},
            }
        ]
        errors, _ = validate_definition(d)
        assert any("Formula parse error" in e or "parse" in e.lower() for e in errors)

    def test_schema_rejects_extra_top_level_keys(self):
        d = ema_def()
        d["hax"] = True
        errors, _ = validate_definition(d)
        assert errors and "Schema error" in errors[0]


class TestEngineIntegration:
    def test_evaluate_definition_produces_signals(self):
        parsed = StrategyDefinition.model_validate(ema_def())
        result = evaluate_definition(parsed, zigzag(60))
        assert len(result.entry_signals) == 60
        assert len(result.exit_signals) == 60
        assert set(result.indicator_series) == {"ema_fast", "ema_slow"}
        # A zigzag series must eventually cross short EMA over long EMA.
        assert any(result.entry_signals)

    def test_exit_conditions_evaluated_when_present(self):
        d = ema_def()
        d["exit"] = {
            "logic": "ALL",
            "conditions": [
                {
                    "left": {"kind": "indicator", "ref": "ema_fast"},
                    "op": "CROSS_BELOW",
                    "right": {"kind": "indicator", "ref": "ema_slow"},
                }
            ],
        }
        parsed = StrategyDefinition.model_validate(d)
        result = evaluate_definition(parsed, zigzag(60))
        assert any(result.exit_signals)

    def test_nan_head_has_no_signals(self):
        parsed = StrategyDefinition.model_validate(ema_def())
        result = evaluate_definition(parsed, zigzag(20))
        warmup = 8  # slow EMA length
        assert not any(result.entry_signals[:warmup])
