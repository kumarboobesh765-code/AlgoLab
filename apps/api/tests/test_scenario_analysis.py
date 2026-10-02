"""Tests for the scenario-analysis engine and endpoint (AlgoTest parity)."""

from app.options.basket import compute_scenarios
from app.schemas.basket import ScenarioRequest

STRANGLE = {
    "spot": 22000.0,
    "legs": [
        {"action": "sell", "option_type": "CE", "strike": 22200.0, "premium": 80.0},
        {"action": "sell", "option_type": "PE", "strike": 21800.0, "premium": 75.0},
    ],
    "days_to_expiry": 7,
    "volatility": 16.0,
}


def _req(**over):
    body = {**STRANGLE, **over}
    return ScenarioRequest.model_validate(body)


class TestScenarioEngine:
    def test_base_is_always_returned_first(self):
        r = compute_scenarios(_req(scenarios=[]))
        assert r.base.name == "Base"
        assert r.base.spot == 22000.0
        assert r.scenarios == []

    def test_scenarios_reprice_with_offsets(self):
        r = compute_scenarios(
            _req(
                scenarios=[
                    {"name": "Down 3%", "spot_offset_pct": -3.0},
                    {"name": "IV +8", "iv_offset_pts": 8.0},
                ]
            )
        )
        assert len(r.scenarios) == 2
        assert r.scenarios[0].spot == round(22000 * 0.97, 2)
        assert r.scenarios[0].volatility == 16.0
        assert r.scenarios[1].spot == 22000.0
        assert r.scenarios[1].volatility == 24.0

    def test_theta_accelerates_as_expiry_approaches(self):
        r = compute_scenarios(
            _req(scenarios=[{"name": "1 day out", "dte_offset_days": -6}])
        )
        assert r.scenarios[0].days_to_expiry == 1
        assert r.scenarios[0].combined_theta > r.base.combined_theta

    def test_theta_rises_with_iv(self):
        r = compute_scenarios(
            _req(scenarios=[{"name": "IV +8", "iv_offset_pts": 8.0}])
        )
        assert r.scenarios[0].combined_theta > r.base.combined_theta

    def test_iv_floor_is_enforced(self):
        r = compute_scenarios(
            _req(scenarios=[{"name": "IV crash", "iv_offset_pts": -100.0}])
        )
        assert r.scenarios[0].volatility >= 0.1

    def test_dte_floor_is_enforced(self):
        # base is 7 DTE; -365 exceeds it, so the engine clamps to 0
        r = compute_scenarios(
            _req(scenarios=[{"name": "expired", "dte_offset_days": -365}])
        )
        assert r.scenarios[0].days_to_expiry == 0

    def test_each_scenario_has_full_greeks_and_payoff(self):
        r = compute_scenarios(
            _req(scenarios=[{"name": "Down 5%", "spot_offset_pct": -5.0}])
        )
        s = r.scenarios[0]
        assert s.payoff, "scenario must carry its own payoff curve"
        assert isinstance(s.combined_delta, float)
        assert isinstance(s.combined_theta, float)
        assert isinstance(s.combined_vega, float)
