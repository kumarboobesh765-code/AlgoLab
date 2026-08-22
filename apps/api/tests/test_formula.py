"""Tests for the safe formula engine."""

import math

import pytest

from app.quant.formula import FormulaError, compile_and_evaluate, parse_formula


def env(**series):
    length = len(next(iter(series.values())))
    return {**series}, length


class TestParsing:
    def test_valid_formulas_parse(self):
        for text in ("1 + 2", "close * 2", "-ema.ema ^ 2", "max(a.b, 0) + (3 - x) / 4"):
            assert parse_formula(text)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "1 +",
            "(1 + 2",
            "1 2",
            "f()",
            "min(1)",
            "unknownfn(1)",
            "1 ? 2 : 3",
            "'string'",
            "__import__('os')",
            "lambda: 0",
            "a; b",
            "x = 5",
        ],
    )
    def test_invalid_formulas_rejected(self, text):
        with pytest.raises(FormulaError):
            parse_formula(text)

    def test_overlong_formula_rejected(self):
        with pytest.raises(FormulaError, match="too long"):
            parse_formula("1+" * 300 + "1")


class TestEvaluation:
    def test_precedence(self):
        out = compile_and_evaluate("2 + 3 * 4", {}, 3)
        assert out == [14.0] * 3

    def test_power_right_associative(self):
        out = compile_and_evaluate("2 ^ 3 ^ 2", {}, 2)
        assert out == [512.0] * 2

    def test_unary_minus_and_parens(self):
        out = compile_and_evaluate("-(2 + 3) * -1", {}, 1)
        assert out == [5.0]

    def test_identifiers_resolve_from_env(self):
        e, n = env(close=[10.0, 20.0], ema_fast_ema=[9.0, 19.0])
        out = compile_and_evaluate("close - ema_fast_ema", e, n)
        assert out == [1.0, 1.0]

    def test_unknown_identifier_raises(self):
        with pytest.raises(FormulaError, match="Unknown identifier"):
            compile_and_evaluate("mystery * 2", {"close": [1.0]}, 1)

    def test_functions(self):
        e, n = env(close=[-4.0, 16.0])
        assert compile_and_evaluate("abs(close)", e, n) == [4.0, 16.0]
        assert compile_and_evaluate("min(close, 5)", e, n) == [-4.0, 5.0]
        assert compile_and_evaluate("max(close, 0)", e, n) == [0.0, 16.0]

        e2, n2 = env(x=[4.0, 16.0])
        assert compile_and_evaluate("sqrt(x)", e2, n2) == [2.0, 4.0]
        assert compile_and_evaluate("round(sqrt(x))", e2, n2) == [2.0, 4.0]

    def test_division_by_zero_is_nan_not_crash(self):
        out = compile_and_evaluate("1 / zero_guard", {"zero_guard": [0.0, 2.0]}, 2)
        assert math.isnan(out[0])
        assert out[1] == 0.5

    def test_negative_sqrt_is_nan(self):
        out = compile_and_evaluate("sqrt(x)", {"x": [-1.0]}, 1)
        assert math.isnan(out[0])

    def test_nan_propagates(self):
        out = compile_and_evaluate("a + b", {"a": [float("nan")], "b": [1.0]}, 1)
        assert math.isnan(out[0])

    def test_length_mismatch_raises(self):
        with pytest.raises(FormulaError, match="length"):
            compile_and_evaluate("close + 1", {"close": [1.0, 2.0]}, 3)
