"""In/Out-of-Sample validation.

A strategy scored on the same bars it was fitted to will look profitable even
when it has no edge. This splits the history into an in-sample segment and an
out-of-sample segment and reports both, so a user can see whether performance
survives on data the strategy was not built against.

Two details matter for the number to mean anything:

- **Warm-up is carried into the OOS leg.** Indicators need history before they
  produce values. Evaluating the OOS segment from a cold start would drop the
  first `length` bars of every overlay, biasing the OOS sample against the
  strategy for reasons that have nothing to do with its edge. So the OOS run
  receives leading bars from the IS segment as context and those bars are
  excluded from the OOS metrics.

- **The OOS leg starts flat with fresh capital.** It is a standalone backtest of
  the unseen period, not a continuation of a carried position. This is the
  standard reading of "would this have worked out of sample", and it keeps the
  two segments independently interpretable.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.backtest.engine import (
    BacktestConfig,
    BacktestError,
    BacktestResult,
    run_backtest,
)
from app.marketdata.base import Candle
from app.quant.schema import StrategyDefinition

DEFAULT_SPLIT = 0.7
MIN_SEGMENT_BARS = 30


class ValidationError(Exception):
    """Not enough history to produce a meaningful split."""


def required_warmup_bars(definition: StrategyDefinition) -> int:
    """Longest lookback any indicator in the definition needs.

    Derived from the definition rather than hardcoded, so adding a long-lookback
    indicator to a strategy automatically widens the OOS warm-up instead of
    silently truncating it.
    """
    longest = 0
    for ind in definition.indicators:
        params = ind.params or {}
        for key in ("length", "period", "k_length", "d_length", "fast", "slow", "signal"):
            value = params.get(key)
            if isinstance(value, (int, float)) and value > longest:
                longest = int(value)
        # Rate-of-change style indicators need an extra bar to difference.
        if ind.type.upper() in {"ROC", "MOM", "CHAIKIN_MONEY_FLOW", "AO", "PPO"}:
            longest += 2
    return longest


@dataclass(slots=True)
class SplitResult:
    in_sample: BacktestResult
    out_of_sample: BacktestResult
    split_index: int
    split_time: str
    warmup_bars: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str

    @property
    def degradation(self) -> dict:
        """How much of the in-sample edge survived on unseen data.

        Efficiency (OOS return / IS return) below ~0.5 is the conventional
        warning sign for curve fitting. It is reported as a number rather than a
        verdict so the user can judge it against their own risk appetite.
        """
        is_ret = self.in_sample.summary.get("return_pct", 0.0) or 0.0
        oos_ret = self.out_of_sample.summary.get("return_pct", 0.0) or 0.0
        is_sharpe = self.in_sample.summary.get("sharpe_ratio", 0.0) or 0.0
        oos_sharpe = self.out_of_sample.summary.get("sharpe_ratio", 0.0) or 0.0
        efficiency = (oos_ret / is_ret) if is_ret else None
        return {
            "is_return_pct": is_ret,
            "oos_return_pct": oos_ret,
            "return_delta_pct": round(oos_ret - is_ret, 4),
            "is_sharpe": is_sharpe,
            "oos_sharpe": oos_sharpe,
            "efficiency_ratio": round(efficiency, 4) if efficiency is not None else None,
            "oos_is_profitable": oos_ret > 0,
            "oos_trades": self.out_of_sample.summary.get("total_trades", 0),
        }


def _as_datetime(value):
    """Normalise a trade timestamp to an aware datetime for comparison.

    Trade.entry_time is typed `object` in the engine and callers may hand us
    either a datetime or a string depending on the storage path.
    """
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _segment(result: BacktestResult, from_index: int, to_index: int) -> dict:
    """Recompute a summary restricted to a candle window of the equity curve."""
    window = result.equity_curve[from_index:to_index]
    if not window:
        return {}
    start_equity = window[0]["equity"]
    end_equity = window[-1]["equity"]
    net = end_equity - start_equity
    base = dict(result.summary)
    base.update(
        {
            "start_equity": round(start_equity, 2),
            "final_equity": round(end_equity, 2),
            "net_pnl": round(net, 2),
            "return_pct": round(net / start_equity * 100.0, 4) if start_equity else 0.0,
            "bars": len(window),
        }
    )
    return base


def run_split_backtest(
    definition: StrategyDefinition,
    candles: Sequence[Candle],
    config: BacktestConfig | None = None,
    split: float = DEFAULT_SPLIT,
) -> SplitResult:
    """Backtest `definition` over an in-sample and out-of-sample segment."""
    cfg = config or BacktestConfig()
    n = len(candles)
    if n < MIN_SEGMENT_BARS * 2:
        raise ValidationError(
            f"Need at least {MIN_SEGMENT_BARS * 2} candles to split "
            f"in/out of sample; got {n}"
        )
    if not 0.1 <= split <= 0.9:
        raise ValidationError("split must be between 0.1 and 0.9")

    warmup = required_warmup_bars(definition)
    is_end = int(n * split)
    # Give the OOS leg real context without letting it eat the sample.
    warmup = min(warmup, max(0, is_end - MIN_SEGMENT_BARS))
    oos_start = is_end
    is_candles = list(candles[:is_end])
    # Context bars are prepended but their metrics are discarded afterwards.
    oos_candles = list(candles[max(0, is_end - warmup) :])
    warmup_bars = len(oos_candles) - (n - is_end)

    if len(is_candles) < 2 or len(oos_candles) < 2:
        raise ValidationError("Split produced an empty segment")

    try:
        is_result = run_backtest(definition, is_candles, cfg)
        oos_result = run_backtest(definition, oos_candles, cfg)
    except BacktestError as exc:
        raise ValidationError(str(exc)) from exc

    # Drop the warm-up prefix from the OOS equity curve so return_pct and
    # max_drawdown_pct describe only the unseen bars.
    if warmup_bars > 0 and oos_result.equity_curve:
        # Compare timestamps as datetimes, not strings: str(datetime) uses a
        # space separator while isoformat() uses "T", so a string comparison
        # against an isoformat boundary silently keeps the warm-up trades.
        boundary = candles[oos_start].timestamp
        trimmed = BacktestResult(
            trades=[t for t in oos_result.trades if _as_datetime(t.entry_time) >= boundary],
            equity_curve=oos_result.equity_curve[warmup_bars:],
            summary=dict(oos_result.summary),
        )
        window = _segment(trimmed, 0, len(trimmed.equity_curve))
        if window:
            merged = dict(trimmed.summary)
            merged.update(
                {
                    "start_equity": window["start_equity"],
                    "final_equity": window["final_equity"],
                    "net_pnl": window["net_pnl"],
                    "return_pct": window["return_pct"],
                }
            )
            # Costs and trade counts belong to the full warm-up-inclusive run;
            # only the equity-derived figures are restated.
            trimmed.summary = merged
        oos_result = trimmed

    return SplitResult(
        in_sample=is_result,
        out_of_sample=oos_result,
        split_index=is_end,
        split_time=candles[is_end - 1].timestamp.isoformat(),
        warmup_bars=warmup_bars,
        is_start=candles[0].timestamp.isoformat(),
        is_end=candles[is_end - 1].timestamp.isoformat(),
        oos_start=candles[oos_start].timestamp.isoformat(),
        oos_end=candles[-1].timestamp.isoformat(),
    )


def to_payload(result: SplitResult) -> dict:
    """Serialise for the API and UI."""
    return {
        "split_index": result.split_index,
        "split_time": result.split_time,
        "warmup_bars": result.warmup_bars,
        "windows": {
            "in_sample": {
                "start": result.is_start,
                "end": result.is_end,
                "summary": result.in_sample.summary,
            },
            "out_of_sample": {
                "start": result.oos_start,
                "end": result.oos_end,
                "summary": result.out_of_sample.summary,
            },
        },
        "degradation": result.degradation,
    }
