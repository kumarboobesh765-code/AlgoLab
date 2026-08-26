"""SEBI algo-trading registration (Phase 10 compliance).

Indian algos must be registered with the exchange/clearing member and carry a
unique ``algo_id`` on every order. This module provides an in-memory registry
that mints and tracks algo IDs, so the OMS can tag every order for audit and
regulatory traceability.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RegisteredAlgo:
    algo_id: str
    name: str
    strategy_id: str | None
    segment: str
    exchange: str
    registered_at: datetime = field(default_factory=datetime.now)
    active: bool = True


class AlgoRegistry:
    """Mints and tracks SEBI algo IDs."""

    def __init__(self):
        self._algos: dict[str, RegisteredAlgo] = {}

    def register(
        self,
        name: str,
        segment: str,
        exchange: str,
        strategy_id: str | None = None,
    ) -> RegisteredAlgo:
        algo_id = f"ALGO-{uuid.uuid4().hex[:12].upper()}"
        algo = RegisteredAlgo(
            algo_id=algo_id,
            name=name,
            strategy_id=strategy_id,
            segment=segment,
            exchange=exchange,
        )
        self._algos[algo_id] = algo
        return algo

    def get(self, algo_id: str) -> RegisteredAlgo | None:
        return self._algos.get(algo_id)

    def deactivate(self, algo_id: str) -> bool:
        algo = self._algos.get(algo_id)
        if not algo:
            return False
        algo.active = False
        return True

    def list_algos(self) -> list[RegisteredAlgo]:
        return list(self._algos.values())


_REGISTRY = AlgoRegistry()


def get_algo_registry() -> AlgoRegistry:
    return _REGISTRY
