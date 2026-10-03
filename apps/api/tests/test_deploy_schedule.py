"""G11 auto-activation and G12 switch-to-manual.

The behaviour that matters is safety, so the tests lean on it: disarming must
stop a running deployment rather than merely disabling future auto-starts, an
armed deployment must stop itself when its window closes, and ticking must be
idempotent so a frequent scheduler cannot double-start.
"""

from datetime import datetime

import pytest

from app.execution.deploy import (
    DeploymentRegistry,
    _parse_hhmm,
    is_trading_window,
)

# 2026-01-05 is a Monday, 2026-01-04 a Sunday.
MONDAY_10AM = datetime(2026, 1, 5, 10, 0)
MONDAY_16PM = datetime(2026, 1, 5, 16, 0)
SUNDAY_10AM = datetime(2026, 1, 4, 10, 0)


@pytest.fixture
def registry() -> DeploymentRegistry:
    # A fresh registry per test: the module-level singleton is shared state and
    # would leak deployments between tests.
    return DeploymentRegistry()


@pytest.fixture
def deployment(registry: DeploymentRegistry):
    return registry.deploy("strat-1", "zerodha", "paper", "Test Strategy")


# --- defaults ---------------------------------------------------------------


def test_new_deployment_is_manual_and_stopped(registry, deployment):
    assert deployment.auto_start is False
    assert deployment.running is False
    assert deployment.schedule_summary == "Manual"


def test_manual_deployment_ignores_the_clock(registry, deployment):
    """A manual deployment must never start itself."""
    registry.arm(deployment.deployment_id, "00:00", "23:59")
    registry.disarm(deployment.deployment_id)
    assert registry.tick(MONDAY_10AM) == []
    assert deployment.running is False


# --- arming -----------------------------------------------------------------


def test_arm_enables_auto_and_records_the_window(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30", weekdays_only=True)
    assert deployment.auto_start is True
    assert deployment.start_time == "09:15"
    assert deployment.stop_time == "15:30"
    assert "09:15-15:30" in deployment.schedule_summary
    assert "weekdays" in deployment.schedule_summary


def test_arm_rejects_malformed_times(registry, deployment):
    for bad in ("25:00", "aa:bb", "", "9:15", "09:99"):
        with pytest.raises(ValueError, match="HH:MM"):
            registry.arm(deployment.deployment_id, bad, "15:30")


def test_arm_rejects_identical_start_and_stop(registry, deployment):
    with pytest.raises(ValueError, match="must differ"):
        registry.arm(deployment.deployment_id, "09:15", "09:15")


def test_arm_on_unknown_deployment_raises(registry):
    with pytest.raises(KeyError, match="Unknown deployment"):
        registry.arm("DEP-NOPE", "09:15", "15:30")


def test_parse_hhmm_rejects_out_of_range():
    assert _parse_hhmm("09:15") == (9, 15)
    assert _parse_hhmm("23:59") == (23, 59)
    assert _parse_hhmm("24:00") is None
    assert _parse_hhmm("12:60") is None
    assert _parse_hhmm("nonsense") is None
    assert _parse_hhmm("") is None


# --- trading window ---------------------------------------------------------


def test_window_boundaries_are_inclusive(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    assert is_trading_window(deployment, datetime(2026, 1, 5, 9, 15))
    assert is_trading_window(deployment, datetime(2026, 1, 5, 15, 30))
    assert not is_trading_window(deployment, datetime(2026, 1, 5, 9, 14))
    assert not is_trading_window(deployment, datetime(2026, 1, 5, 15, 31))


def test_weekends_excluded_when_weekdays_only(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30", weekdays_only=True)
    assert not is_trading_window(deployment, SUNDAY_10AM)
    assert is_trading_window(deployment, MONDAY_10AM)


def test_weekends_included_when_not_weekdays_only(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30", weekdays_only=False)
    assert is_trading_window(deployment, SUNDAY_10AM)


def test_saturday_is_excluded(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30", weekdays_only=True)
    assert not is_trading_window(deployment, datetime(2026, 1, 3, 10, 0))


def test_window_spanning_midnight_is_not_empty(registry, deployment):
    """A 19:00-03:30 session must read as spanning midnight, not as never open."""
    registry.arm(deployment.deployment_id, "19:00", "03:30", weekdays_only=False)
    assert is_trading_window(deployment, datetime(2026, 1, 5, 22, 0))
    assert is_trading_window(deployment, datetime(2026, 1, 6, 2, 0))
    assert not is_trading_window(deployment, datetime(2026, 1, 5, 12, 0))


def test_malformed_schedule_never_matches(registry, deployment):
    deployment.auto_start = True
    deployment.start_time = "not-a-time"
    assert not is_trading_window(deployment, MONDAY_10AM)


# --- ticking ----------------------------------------------------------------


def test_tick_starts_an_armed_deployment_inside_the_window(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    changed = registry.tick(MONDAY_10AM)
    assert [c.deployment_id for c in changed] == [deployment.deployment_id]
    assert deployment.running is True
    assert deployment.last_started_at is not None
    assert deployment.stop_reason is None


def test_tick_stops_when_the_window_closes(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.tick(MONDAY_10AM)
    changed = registry.tick(MONDAY_16PM)
    assert deployment.running is False
    assert deployment.stop_reason == "auto_window_closed"
    assert deployment.last_stopped_at is not None
    assert len(changed) == 1


def test_tick_is_idempotent(registry, deployment):
    """A scheduler ticking every second must not double-start."""
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.tick(MONDAY_10AM)
    first_started = deployment.last_started_at
    for _ in range(5):
        assert registry.tick(MONDAY_10AM) == []
    assert deployment.last_started_at == first_started


def test_tick_does_nothing_on_the_weekend(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30", weekdays_only=True)
    assert registry.tick(SUNDAY_10AM) == []
    assert deployment.running is False


def test_deactivated_deployment_is_not_started(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.deactivate(deployment.deployment_id)
    assert registry.tick(MONDAY_10AM) == []
    assert deployment.running is False


# --- manual override --------------------------------------------------------


def test_disarm_switches_to_manual(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.disarm(deployment.deployment_id)
    assert deployment.auto_start is False
    assert deployment.schedule_summary == "Manual"


def test_disarm_stops_a_running_deployment(registry, deployment):
    """Taking manual control must not leave orders flowing unattended."""
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.tick(MONDAY_10AM)
    assert deployment.running is True
    registry.disarm(deployment.deployment_id)
    assert deployment.running is False
    assert deployment.stop_reason == "switched_to_manual"


def test_disarmed_deployment_never_restarts(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.tick(MONDAY_10AM)
    registry.disarm(deployment.deployment_id)
    assert registry.tick(MONDAY_10AM) == []
    assert deployment.running is False


def test_disarm_on_idle_deployment_is_safe(registry, deployment):
    registry.arm(deployment.deployment_id, "09:15", "15:30")
    registry.disarm(deployment.deployment_id)
    assert deployment.running is False
    assert deployment.stop_reason is None


# --- explicit start/stop ----------------------------------------------------


def test_manual_start_and_stop(registry, deployment):
    registry.start(deployment.deployment_id, reason="manual")
    assert deployment.running is True
    registry.stop(deployment.deployment_id, reason="manual")
    assert deployment.running is False
    assert deployment.stop_reason == "manual"


def test_start_is_idempotent(registry, deployment):
    registry.start(deployment.deployment_id)
    first = deployment.last_started_at
    registry.start(deployment.deployment_id)
    assert deployment.last_started_at == first


def test_stop_is_idempotent(registry, deployment):
    registry.stop(deployment.deployment_id)
    assert deployment.running is False
    assert deployment.last_stopped_at is None


def test_cannot_start_a_deactivated_deployment(registry, deployment):
    registry.deactivate(deployment.deployment_id)
    with pytest.raises(ValueError, match="deactivated"):
        registry.start(deployment.deployment_id)


def test_unknown_deployment_start_raises(registry):
    with pytest.raises(KeyError):
        registry.start("DEP-NOPE")


def test_unknown_deployment_stop_raises(registry):
    with pytest.raises(KeyError):
        registry.stop("DEP-NOPE")


# --- deploy validation ------------------------------------------------------


def test_deploy_rejects_bad_mode(registry):
    with pytest.raises(ValueError, match="paper"):
        registry.deploy("s", "zerodha", "semi-live", "X")


def test_deployments_are_tracked_per_strategy(registry):
    a = registry.deploy("strat-a", "zerodha", "paper", "A")
    b = registry.deploy("strat-b", "dhan", "paper", "B")
    registry.arm(a.deployment_id, "09:15", "15:30")
    registry.tick(MONDAY_10AM)
    # One armed, one not: only the armed one may run.
    assert a.running is True
    assert b.running is False
    assert [d.deployment_id for d in registry.for_strategy("strat-a")] == [a.deployment_id]
