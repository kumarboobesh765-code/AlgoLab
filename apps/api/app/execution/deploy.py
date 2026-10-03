"""Strategy → live execution deployment seam (Phase 10).

Closes the research-to-trade loop: a backtested/paper strategy can be
*deployed* — registered as a SEBI algo ID and linked to a target broker in a
chosen mode (``paper`` for simulated routing, ``live`` for real brokerage).
Every order placed for the deployment carries the algo ID for audit/trace.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.execution.sebi import RegisteredAlgo, get_algo_registry


@dataclass
class Deployment:
    deployment_id: str
    strategy_id: str
    algo_id: str
    broker: str
    mode: str  # "paper" | "live"
    name: str
    segment: str
    exchange: str
    created_at: datetime = field(default_factory=datetime.now)
    active: bool = True

    # --- scheduling (G11 auto-activation) ---
    # auto_start makes the deployment resume on its own once armed, instead of
    # waiting for a human each session. Stored per deployment rather than
    # globally so one strategy can be automatic while another stays manual.
    auto_start: bool = False
    start_time: str = "09:15"  # HH:MM in IST, NSE open
    stop_time: str = "15:30"  # HH:MM in IST, NSE close
    weekdays_only: bool = True

    # --- runtime state ---
    running: bool = False
    last_started_at: datetime | None = None
    last_stopped_at: datetime | None = None
    stop_reason: str | None = None

    @property
    def schedule_summary(self) -> str:
        span = f"{self.start_time}-{self.stop_time}"
        if self.auto_start and self.weekdays_only:
            return f"Auto · weekdays {span} IST"
        if self.auto_start:
            return f"Auto · daily {span} IST"
        return "Manual"


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    """Parse a strict HH:MM string, returning None when malformed.

    Strict means zero-padded: `int("9")` would happily accept "9:15", which then
    fails to compare correctly against a stored "09:15" in a config file or a
    UI that round-trips the value.
    """
    if not isinstance(value, str):
        return None
    hh, sep, mm = value.partition(":")
    if sep != ":" or len(hh) != 2 or len(mm) != 2:
        return None
    if not (hh.isdigit() and mm.isdigit()):
        return None
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h, m


def is_trading_window(deployment: Deployment, now: datetime) -> bool:
    """Whether `now` falls inside the deployment's configured window.

    Deliberately naive about exchange holidays: a deployment armed for weekdays
    will fire on a market holiday, and the order path will reject it when the
    broker reports the market closed. Guessing a holiday calendar here would add
    a second source of truth that could silently disagree with the broker's.
    """
    start = _parse_hhmm(deployment.start_time)
    end = _parse_hhmm(deployment.stop_time)
    if start is None or end is None:
        return False
    if deployment.weekdays_only and now.weekday() >= 5:
        return False
    current = now.hour * 60 + now.minute
    begin, finish = start[0] * 60 + start[1], end[0] * 60 + end[1]
    # A window that wraps past midnight (e.g. 19:00-03:30 for a commodity
    # session) is treated as spanning midnight rather than being empty.
    if begin <= finish:
        return begin <= current <= finish
    return current >= begin or current <= finish


class DeploymentRegistry:
    """Maps a strategy to its broker deployments (each gets a SEBI algo ID)."""

    def __init__(self):
        self._deployments: dict[str, Deployment] = {}
        self._by_strategy: dict[str, list[str]] = {}

    def deploy(
        self,
        strategy_id: str,
        broker: str,
        mode: str,
        name: str,
        segment: str = "EQUITY",
        exchange: str = "NSE",
    ) -> Deployment:
        if mode not in ("paper", "live"):
            raise ValueError("mode must be 'paper' or 'live'")
        algo: RegisteredAlgo = get_algo_registry().register(
            name, segment, exchange, strategy_id=strategy_id
        )
        dep = Deployment(
            deployment_id=f"DEP-{uuid.uuid4().hex[:10].upper()}",
            strategy_id=strategy_id,
            algo_id=algo.algo_id,
            broker=broker,
            mode=mode,
            name=name,
            segment=segment,
            exchange=exchange,
        )
        self._deployments[dep.deployment_id] = dep
        self._by_strategy.setdefault(strategy_id, []).append(dep.deployment_id)
        return dep

    def list_deployments(self) -> list[Deployment]:
        return list(self._deployments.values())

    def get(self, deployment_id: str) -> Deployment | None:
        return self._deployments.get(deployment_id)

    def for_strategy(self, strategy_id: str) -> list[Deployment]:
        ids = self._by_strategy.get(strategy_id, [])
        return [self._deployments[i] for i in ids if i in self._deployments]

    def deactivate(self, deployment_id: str) -> bool:
        dep = self._deployments.get(deployment_id)
        if not dep:
            return False
        dep.active = False
        return True

    # ------------------------------------------------------------------
    # G11 auto-activation / G12 switch to manual
    # ------------------------------------------------------------------
    def arm(self, deployment_id: str, start_time: str, stop_time: str,
            weekdays_only: bool = True) -> Deployment:
        """Enable automatic start/stop for a deployment."""
        dep = self._require(deployment_id)
        for label, value in (("start_time", start_time), ("stop_time", stop_time)):
            if _parse_hhmm(value) is None:
                raise ValueError(f"{label} must be HH:MM, got {value!r}")
        if start_time == stop_time:
            raise ValueError("start_time and stop_time must differ")
        dep.start_time = start_time
        dep.stop_time = stop_time
        dep.weekdays_only = weekdays_only
        dep.auto_start = True
        return dep

    def disarm(self, deployment_id: str) -> Deployment:
        """Switch back to manual control and stop it if it was running.

        Disarming implies stopping: leaving a deployment trading after the user
        asked to take manual control would be the worst possible reading of
        "switch to manual".
        """
        dep = self._require(deployment_id)
        dep.auto_start = False
        if dep.running:
            self.stop(deployment_id, reason="switched_to_manual")
        return dep

    def start(self, deployment_id: str, *, reason: str = "manual") -> Deployment:
        dep = self._require(deployment_id)
        if not dep.active:
            raise ValueError("deployment is deactivated")
        if dep.running:
            return dep
        dep.running = True
        dep.last_started_at = datetime.now()
        dep.stop_reason = None
        dep.last_start_reason = reason
        return dep

    def stop(self, deployment_id: str, *, reason: str = "manual") -> Deployment:
        dep = self._require(deployment_id)
        if not dep.running:
            return dep
        dep.running = False
        dep.last_stopped_at = datetime.now()
        dep.stop_reason = reason
        return dep

    def tick(self, now: datetime | None = None) -> list[Deployment]:
        """Advance auto-managed deployments to match the clock.

        Idempotent: calling it twice in the same window produces no second
        start, so a scheduler can tick as often as it likes.
        """
        moment = now or datetime.now()
        changed: list[Deployment] = []
        for dep in self._deployments.values():
            if not dep.active or not dep.auto_start:
                continue
            inside = is_trading_window(dep, moment)
            if inside and not dep.running:
                changed.append(self.start(dep.deployment_id, reason="auto_window_open"))
            elif not inside and dep.running:
                changed.append(self.stop(dep.deployment_id, reason="auto_window_closed"))
        return changed

    def _require(self, deployment_id: str) -> Deployment:
        dep = self._deployments.get(deployment_id)
        if dep is None:
            raise KeyError(f"Unknown deployment: {deployment_id}")
        return dep


_REGISTRY = DeploymentRegistry()


def get_deployment_registry() -> DeploymentRegistry:
    return _REGISTRY
