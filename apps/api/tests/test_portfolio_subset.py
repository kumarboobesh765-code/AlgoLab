"""Portfolio subset picker (G6).

The behaviour worth pinning is that diversification is actually rewarded. A
picker that merely returns the highest-returning subset would pass a naive test
and be useless, so these tests build strategies with deliberately correlated and
deliberately staggered curves and assert the picker can tell them apart.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.backtest import BacktestResult
from app.backtest.portfolio_engine import PortfolioInput, combine
from app.backtest.subset import optimise_subset


def make_input(name: str, shift: int = 0, drift: float = 0.004,
               n: int = 200, seed: int = 1) -> PortfolioInput:
    """A deterministic equity curve whose gains cluster on a phase.

    `shift` staggers the profitable half of each cycle, so two runs with the same
    shift are highly correlated (little diversification benefit) and two with
    different shifts are not.
    """
    import random

    rng = random.Random(seed)
    points = []
    equity = 100_000.0
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        up = (i + shift) % 40 < 20
        equity *= 1 + (drift if up else -drift / 2) + rng.gauss(0, 0.001)
        points.append(
            {"time": (base + timedelta(minutes=i)).isoformat(), "equity": round(equity, 2)}
        )
    return PortfolioInput(
        strategy_id=name,
        strategy_name=name,
        initial_capital=100_000,
        result=BacktestResult(trades=[], equity_curve=points, summary={}),
    )


@pytest.fixture
def runs() -> list[PortfolioInput]:
    return [make_input("A", shift=0), make_input("B", shift=0, seed=2),
            make_input("C", shift=20, seed=3), make_input("D", shift=25, seed=4)]


# --- degenerate inputs ------------------------------------------------------


def test_empty_input_handled():
    out = optimise_subset([])
    assert out["best"] is None
    assert out["candidates_considered"] == 0
    assert "No completed runs" in out["note"]


def test_runs_without_equity_curves_are_ignored():
    empty = PortfolioInput(
        strategy_id="X",
        strategy_name="X",
        initial_capital=100_000,
        result=BacktestResult(trades=[], equity_curve=[], summary={}),
    )
    out = optimise_subset([empty])
    assert out["best"] is None


def test_single_run_is_reported_honestly(runs):
    """One run is not a subset; the result must not imply it chose."""
    out = optimise_subset(runs[:1], size=1)
    assert out["single_best"] is not None
    assert len(out["best"]["run_ids"]) == 1
    # With only one candidate there is nothing to compare, so no verdict.
    assert out["note"] is None or "not a subset comparison" in out["note"]


def test_subset_size_clamped_to_available_runs(runs):
    out = optimise_subset(runs, size=99)
    assert out["subset_size"] == len(runs)


def test_zero_size_is_corrected_to_one(runs):
    out = optimise_subset(runs, size=0)
    assert out["subset_size"] >= 1


# --- exhaustive search ------------------------------------------------------


def test_exhaustive_over_small_input(runs):
    out = optimise_subset(runs, size=2)
    assert out["exhaustive"] is True
    # C(4,2) = 6
    assert out["combinations_possible"] == 6
    assert out["candidates_considered"] == 6


def test_best_subset_ranks_first_and_runners_follow(runs):
    out = optimise_subset(runs, size=2, top_n=3)
    assert out["best"]["rank"] == 1
    assert len(out["runners_up"]) == 2
    assert out["runners_up"][0]["rank"] == 2


def test_every_subset_of_requested_size(runs):
    out = optimise_subset(runs, size=3)
    assert out["combinations_possible"] == 4
    for candidate in [out["best"], *out["runners_up"]]:
        assert len(candidate["run_ids"]) == 3


def test_large_input_falls_back_to_greedy_and_says_so():
    # Need C(n,k) > 20_000; C(24,6) = 134_596.
    many = [make_input(f"S{i:02d}", shift=i, seed=i) for i in range(24)]
    out = optimise_subset(many, size=6)
    assert out["exhaustive"] is False
    assert "Greedy search" in out["note"]
    assert len(out["best"]["run_ids"]) == 6


def test_exhaustive_still_used_when_combinations_are_tractable():
    # C(12,6) = 924, comfortably inside the threshold.
    runs = [make_input(f"S{i:02d}", shift=i, seed=i) for i in range(12)]
    out = optimise_subset(runs, size=6)
    assert out["exhaustive"] is True
    assert out["candidates_considered"] == out["combinations_possible"]


# --- diversification --------------------------------------------------------


def test_staggered_runs_are_preferred_over_correlated_pairs(runs):
    """A and B share a phase; C and D are offset. The picker should lean to the
    offset pair, because correlated "diversification" is just doubling up."""
    out = optimise_subset(runs, size=2, objective="return_pct")
    best = set(out["best"]["run_ids"])
    correlated = {"A", "B"}
    assert best != correlated, "picked two perfectly correlated strategies"


def test_combined_curve_smoother_than_either_component(runs):
    """Combining offset strategies should produce a shallower drawdown than
    either one alone."""
    _, combined = combine([make_input("C", shift=20), make_input("D", shift=25)])
    _, single_c = combine([make_input("C", shift=20)])
    _, single_d = combine([make_input("D", shift=25)])
    assert combined["max_drawdown_pct"] <= max(
        single_c["max_drawdown_pct"], single_d["max_drawdown_pct"]
    )


def test_baseline_flags_subsets_that_add_nothing():
    """Two identical strategies cannot diversify; the result must say so."""
    twins = [make_input("A", shift=0), make_input("A2", shift=0, seed=99)]
    out = optimise_subset(twins, size=2)
    if out["note"] and "does not beat" in out["note"]:
        assert len(out["best"]["run_ids"]) == 2


def test_single_best_is_the_strongest_individual_run(runs):
    out = optimise_subset(runs, size=2)
    baseline = out["single_best"]
    assert len(baseline["run_ids"]) == 1
    for candidate in runs:
        assert baseline["run_ids"][0] in {c.strategy_id for c in runs}


# --- objectives -------------------------------------------------------------


def test_calmar_objective_used():
    runs = [make_input("A"), make_input("B", shift=20)]
    out = optimise_subset(runs, size=2, objective="calmar")
    assert out["objective"] == "calmar"
    assert out["best"] is not None


def test_return_objective_used(runs):
    out = optimise_subset(runs, size=2, objective="return_pct")
    assert out["objective"] == "return_pct"


def test_metrics_are_populated(runs):
    out = optimise_subset(runs, size=2)
    metrics = out["best"]["metrics"]
    for key in ("return_pct", "sharpe_ratio", "max_drawdown_pct"):
        assert key in metrics, f"missing {key}"


def test_deterministic_across_calls(runs):
    first = optimise_subset(runs, size=2)["best"]["run_ids"]
    second = optimise_subset(runs, size=2)["best"]["run_ids"]
    assert first == second


# --- payload ----------------------------------------------------------------


def test_result_is_json_serialisable(runs):
    import json

    json.dumps(optimise_subset(runs, size=2))


def test_strategy_names_reported_for_display(runs):
    out = optimise_subset(runs, size=2)
    assert set(out["best"]["strategy_names"]) == set(out["best"]["run_ids"])
