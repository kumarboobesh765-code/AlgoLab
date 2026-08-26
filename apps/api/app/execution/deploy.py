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


_REGISTRY = DeploymentRegistry()


def get_deployment_registry() -> DeploymentRegistry:
    return _REGISTRY
