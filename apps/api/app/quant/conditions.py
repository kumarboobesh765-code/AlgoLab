"""Condition engine.

A condition compares two operands bar-by-bar:

    {"left": {"kind": "indicator", "ref": "ema_fast.ema"},
     "op": "CROSS_ABOVE",
     "right": {"kind": "price", "price": "close"}}

Operand kinds: `price` (open/high/low/close/volume/hl2/hlc3/ohlc4),
`constant`, `variable` (named strategy variable), `indicator` ("<id>.<output>"
or "<id>" when the indicator has a single output), `formula` (safe expression).

Operators: GT, LT, GTE, LTE, CROSS_ABOVE, CROSS_BELOW.
Groups combine conditions with ALL/ANY logic and may nest (depth-capped).
"""

import math
from collections.abc import Sequence
from typing import Any

from app.marketdata.base import Candle
from app.quant.formula import FormulaError, compile_and_evaluate
from app.quant.indicators import SOURCES, _source_series

NAN = math.nan


class ConditionError(ValueError):
    """Raised for malformed or unresolvable conditions."""


OPERATORS = ("GT", "LT", "GTE", "LTE", "CROSS_ABOVE", "CROSS_BELOW")
PRICE_SOURCES = SOURCES
MAX_GROUP_DEPTH = 3


# ------------------------------------------------------------- structural


def validate_condition_node(node: Any, variables: set[str], depth: int = 0) -> list[str]:
    """Structural validation without data. Returns a list of error strings."""
    errors: list[str] = []
    if depth > MAX_GROUP_DEPTH:
        return [f"Condition group nesting exceeds {MAX_GROUP_DEPTH} levels"]
    if not isinstance(node, dict):
        return ["Condition node must be an object"]
    if "logic" in node:
        if node["logic"] not in ("ALL", "ANY"):
            errors.append(f"Group logic must be ALL or ANY, got {node['logic']!r}")
        children = node.get("conditions")
        if not isinstance(children, list) or not children:
            errors.append("Group must contain a non-empty 'conditions' list")
            return errors
        for child in children:
            errors.extend(validate_condition_node(child, variables, depth + 1))
        return errors

    missing = [k for k in ("left", "op", "right") if k not in node]
    if missing:
        return [f"Condition is missing field(s): {', '.join(missing)}"]
    if node["op"] not in OPERATORS:
        errors.append(
            f"Unknown operator {node['op']!r}; expected one of {list(OPERATORS)}"
        )
    for side in ("left", "right"):
        errs = _validate_operand(node[side], variables)
        errors.extend(f"{side}: {e}" for e in errs)
    return errors


def _validate_operand(operand: Any, variables: set[str]) -> list[str]:
    if not isinstance(operand, dict):
        return ["Operand must be an object"]
    kind = operand.get("kind")
    if kind == "price":
        if operand.get("price") not in PRICE_SOURCES:
            return [f"price must be one of {list(PRICE_SOURCES)}"]
        return []
    if kind == "constant":
        value = operand.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return ["constant operand requires a numeric 'value'"]
        return []
    if kind == "variable":
        name = operand.get("name")
        if not isinstance(name, str) or not name:
            return ["variable operand requires a 'name'"]
        if name not in variables:
            return [f"unknown variable {name!r}"]
        return []
    if kind == "indicator":
        ref = operand.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            return ["indicator operand requires a 'ref' like '<id>.<output>'"]
        return []
    if kind == "formula":
        text = operand.get("expression")
        if not isinstance(text, str) or not text.strip():
            return ["formula operand requires an 'expression'"]
        from app.quant.formula import parse_formula

        try:
            parse_formula(text)
        except FormulaError as exc:
            return [f"invalid formula: {exc}"]
        return []
    return [f"operand.kind must be one of price|constant|variable|indicator|formula, got {kind!r}"]


# -------------------------------------------------------------- evaluation


def build_operand_series(
    operand: dict,
    candles: Sequence[Candle],
    indicator_series: dict[str, dict[str, list[float]]],
    variables: dict[str, float],
) -> list[float]:
    """Resolve one operand to a float series aligned with the candles."""
    kind = operand["kind"]
    n = len(candles)
    if kind == "price":
        return _source_series(candles, operand["price"])
    if kind == "constant":
        return [float(operand["value"])] * n
    if kind == "variable":
        name = operand["name"]
        if name not in variables:
            raise ConditionError(f"Unknown variable {name!r}")
        return [float(variables[name])] * n
    if kind == "indicator":
        ref = operand["ref"].strip()
        ind_id, _, output = ref.partition(".")
        outputs = indicator_series.get(ind_id)
        if outputs is None:
            raise ConditionError(f"Reference to unknown indicator {ind_id!r}")
        if output:
            if output not in outputs:
                raise ConditionError(
                    f"Indicator {ind_id!r} has no output {output!r}; "
                    f"available: {sorted(outputs)}"
                )
            return outputs[output]
        if len(outputs) > 1:
            raise ConditionError(
                f"Indicator {ind_id!r} has multiple outputs; qualify the reference "
                f"(e.g. '{ind_id}.{sorted(outputs)[0]}')"
            )
        return next(iter(outputs.values()))
    if kind == "formula":
        env: dict[str, Sequence[float]] = {}
        env.update({p: _source_series(candles, p) for p in ("open", "high", "low", "close", "volume")})
        env.update({p: _source_series(candles, p) for p in ("hl2", "hlc3", "ohlc4")})
        for ind_id, outputs in indicator_series.items():
            for out_name, series in outputs.items():
                env[f"{ind_id}.{out_name}" if len(outputs) > 1 else ind_id] = series
        env.update({name: [float(v)] * n for name, v in variables.items()})
        try:
            return compile_and_evaluate(operand["expression"], env, n)
        except FormulaError as exc:
            raise ConditionError(f"Formula evaluation failed: {exc}") from exc
    raise ConditionError(f"Unsupported operand kind {kind!r}")


def evaluate_condition(
    condition: dict,
    candles: Sequence[Candle],
    indicator_series: dict[str, dict[str, list[float]]],
    variables: dict[str, float],
) -> list[bool]:
    left = build_operand_series(condition["left"], candles, indicator_series, variables)
    right = build_operand_series(condition["right"], candles, indicator_series, variables)
    op = condition["op"]

    if op in ("GT", "LT", "GTE", "LTE"):
        fn = {
            "GT": lambda a, b: a > b,
            "LT": lambda a, b: a < b,
            "GTE": lambda a, b: a >= b,
            "LTE": lambda a, b: a <= b,
        }[op]
        return [
            bool(fn(a, b)) if not (math.isnan(a) or math.isnan(b)) else False
            for a, b in zip(left, right, strict=True)
        ]

    # Cross semantics on the previous completed pair of bars:
    # CROSS_ABOVE: prev <= prev_right and now > right
    # CROSS_BELOW: prev >= prev_right and now < right
    out = [False] * len(candles)
    for i in range(1, len(candles)):
        a_prev, b_prev = left[i - 1], right[i - 1]
        a_now, b_now = left[i], right[i]
        if any(math.isnan(v) for v in (a_prev, b_prev, a_now, b_now)):
            continue
        if op == "CROSS_ABOVE":
            out[i] = a_prev <= b_prev and a_now > b_now
        else:
            out[i] = a_prev >= b_prev and a_now < b_now
    return out


def evaluate_group(
    group: dict,
    candles: Sequence[Candle],
    indicator_series: dict[str, dict[str, list[float]]],
    variables: dict[str, float],
    depth: int = 0,
) -> list[bool]:
    """Evaluate a condition tree to a boolean series."""
    if depth > MAX_GROUP_DEPTH:
        raise ConditionError(f"Condition group nesting exceeds {MAX_GROUP_DEPTH} levels")
    logic = group.get("logic", "ALL")
    children = group.get("conditions", [])
    results = [
        (
            evaluate_group(child, candles, indicator_series, variables, depth + 1)
            if "logic" in child
            else evaluate_condition(child, candles, indicator_series, variables)
        )
        for child in children
    ]
    if not results:
        return [logic == "ANY"] * len(candles)
    if logic == "ANY":
        return [any(vals[i] for vals in results) for i in range(len(candles))]
    return [all(vals[i] for vals in results) for i in range(len(candles))]
