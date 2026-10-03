"""Portfolio subset picker (G6).

Picking N strategies by individual rank is the obvious approach and the wrong
one: three strategies that each returned 20% but all peaked in the same month
are one bet, not three. This scores candidate subsets on the *combined* curve so
a subset is rewarded for diversification, and reports the runners-up so the
choice is legible rather than a black box.

Search is exhaustive up to `max_subset` with a greedy fallback beyond it, because
"which 3 of 40" is C(40,3) = 9880 combinations - tractable - while "which 12 of
40" is not. The fallback is explicit in the result so a caller can tell an
exhaustive search from a heuristic one.
"""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from app.backtest.portfolio_engine import PortfolioInput, combine

# Enough history to smooth daily noise without straddling regime changes.
MAX_SUBSET = 6


@dataclass(slots=True)
class SubsetScore:
    run_ids: tuple[str, ...]
    strategy_names: tuple[str, ...]
    metrics: dict
    rank: int = 0


def _fitness(metrics: dict, objective: str) -> float:
    """Score a subset on the requested objective.

    Sharpe is the default because return alone rewards a single lucky trade and
    drawdown alone rewards never trading.
    """
    if objective == "return_pct":
        return float(metrics.get("return_pct") or 0.0)
    if objective == "calmar":
        dd = abs(float(metrics.get("max_drawdown_pct") or 0.0))
        ret = float(metrics.get("return_pct") or 0.0)
        return ret / dd if dd > 1e-9 else ret
    return float(metrics.get("sharpe_ratio") or 0.0)


def _tradeable(inputs: Sequence[PortfolioInput]) -> list[PortfolioInput]:
    """Drop runs with no equity curve, which would skew the combination."""
    return [i for i in inputs if i.result and i.result.equity_curve]


def evaluate_subset(
    inputs: Sequence[PortfolioInput], objective: str = "sharpe_ratio"
) -> SubsetScore:
    curve, summary = combine(inputs)
    return SubsetScore(
        run_ids=tuple(i.strategy_id for i in inputs),
        strategy_names=tuple(i.strategy_name for i in inputs),
        metrics={
            **(summary or {}),
            "bars": len(curve),
        },
    )


def optimise_subset(
    inputs: Sequence[PortfolioInput],
    size: int | None = None,
    objective: str = "sharpe_ratio",
    top_n: int = 5,
    max_exhaustive: int = MAX_SUBSET,
) -> dict:
    """Rank candidate subsets of the given runs.

    Returns the best subset plus runners-up, whether the search was exhaustive,
    and the single best run as a baseline. That baseline matters: a subset that
    does not beat its best individual component has not added anything, and the
    result says so instead of implying the subset is a win.
    """
    usable = _tradeable(inputs)
    n = len(usable)
    if n == 0:
        return {
            "objective": objective,
            "exhaustive": False,
            "subset_size": 0,
            "candidates_considered": 0,
            "best": None,
            "runners_up": [],
            "single_best": None,
            "note": "No completed runs with equity curves were supplied.",
        }

    subset_size = size or min(2, n)
    subset_size = max(1, min(subset_size, n))

    # Baseline: the strongest single run on the same objective.
    singles = [evaluate_subset([i], objective) for i in usable]
    singles.sort(key=lambda s: _fitness(s.metrics, objective), reverse=True)
    single_best = singles[0]

    total_combinations = 1
    for k in range(subset_size):
        total_combinations = total_combinations * (n - k) // (k + 1)

    if total_combinations <= 20_000:
        combos = itertools.combinations(usable, subset_size)
        exhaustive = True
    else:
        # Greedy: start from the best single, then repeatedly add whichever
        # remaining run most improves the combined curve.
        combos = _greedy_combinations(usable, single_best, subset_size)
        exhaustive = False

    scored: list[SubsetScore] = []
    for combo in combos:
        if not combo:
            continue
        score = evaluate_subset(list(combo), objective)
        scored.append(score)
    scored.sort(key=lambda s: _fitness(s.metrics, objective), reverse=True)

    for i, s in enumerate(scored[:top_n], start=1):
        s.rank = i

    best = scored[0] if scored else None
    best_value = _fitness(best.metrics, objective) if best else 0.0
    single_value = _fitness(single_best.metrics, objective)

    notes: list[str] = []
    if not exhaustive:
        notes.append(
            f"Greedy search: {total_combinations} combinations of size "
            f"{subset_size} from {n} runs is too many to enumerate, so "
            "candidates were grown from the strongest single run."
        )
    if best is not None and len(best.run_ids) > 1 and best_value <= single_value:
        notes.append(
            "The best subset does not beat its strongest single strategy. "
            "Diversification is not adding value here."
        )
    if best is not None and len(best.run_ids) == 1 and n > 1:
        notes.append("Only one run was supplied, so this is not a subset comparison.")

    return {
        "objective": objective,
        "exhaustive": exhaustive,
        "subset_size": subset_size,
        "candidates_considered": len(scored),
        "combinations_possible": total_combinations,
        "best": _to_dict(best),
        "runners_up": [_to_dict(s) for s in scored[1:top_n]],
        "single_best": _to_dict(single_best),
        "note": " ".join(notes) if notes else None,
    }


def _greedy_combinations(
    usable: Sequence[PortfolioInput],
    single_best: SubsetScore,
    subset_size: int,
):
    """Yield one greedily-grown candidate plus each single as a fallback."""
    chosen_ids = set(single_best.run_ids)
    chosen = [i for i in usable if i.strategy_id in chosen_ids]
    remaining = [i for i in usable if i.strategy_id not in chosen_ids]

    while len(chosen) < subset_size and remaining:
        best_addition = None
        best_value = None
        for candidate in remaining:
            combo = chosen + [candidate]
            value = _fitness(evaluate_subset(combo).metrics, "sharpe_ratio")
            if best_value is None or value > best_value:
                best_value = value
                best_addition = candidate
        if best_addition is None:
            break
        chosen.append(best_addition)
        remaining = [i for i in remaining if i is not best_addition]
    yield tuple(chosen)


def _to_dict(score: SubsetScore | None) -> dict | None:
    if score is None:
        return None
    return {
        "rank": score.rank,
        "run_ids": list(score.run_ids),
        "strategy_names": list(score.strategy_names),
        "metrics": score.metrics,
    }
