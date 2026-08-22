"""Definition evaluation engine.

Runs a validated strategy definition over a candle series and produces the
indicator series plus entry/exit signal vectors. The backtest engine (Phase 5)
and paper engine (Phase 7) consume exactly this output.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.marketdata.base import Candle
from app.quant.conditions import ConditionError, evaluate_group
from app.quant.indicators import IndicatorError, compute_indicator
from app.quant.schema import StrategyDefinition


@dataclass
class EvaluationResult:
    indicator_series: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    entry_signals: list[bool] = field(default_factory=list)
    exit_signals: list[bool] = field(default_factory=list)


def evaluate_definition(
    definition: StrategyDefinition, candles: Sequence[Candle]
) -> EvaluationResult:
    """Compute all indicators and evaluate entry/exit condition trees."""
    if not candles:
        raise ConditionError("Cannot evaluate a definition on an empty candle series")

    variables = {v.name: v.value for v in definition.variables}
    indicator_series: dict[str, dict[str, list[float]]] = {}

    for ind in definition.indicators:
        try:
            indicator_series[ind.id] = compute_indicator(ind.type, candles, ind.params)
        except IndicatorError as exc:
            raise ConditionError(f"Indicator {ind.id!r}: {exc}") from exc

    entry_signals = evaluate_group(
        definition.entry.model_dump(), candles, indicator_series, variables
    )
    exit_signals = (
        evaluate_group(definition.exit.model_dump(), candles, indicator_series, variables)
        if definition.exit is not None
        else [False] * len(candles)
    )
    return EvaluationResult(
        indicator_series=indicator_series,
        entry_signals=entry_signals,
        exit_signals=exit_signals,
    )


def count_signals(result: EvaluationResult) -> tuple[int, int]:
    """Convenience for previews: (entry_count, exit_count)."""
    return sum(result.entry_signals), sum(result.exit_signals)
