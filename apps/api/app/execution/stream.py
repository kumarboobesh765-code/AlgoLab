"""In-memory tick/order stream manager.

Provides a pub/sub hub for live market data and order updates. Real brokers
push through their WebSocket feeds (see :mod:`app.execution.zerodha` /
:mod:`app.execution.upstox`); the OMS publishes each received tick here so the
dashboard and any subscriber can consume a unified quote stream.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Tick:
    symbol: str
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    oi: int = 0
    change: float = 0.0
    change_pct: float = 0.0
    timestamp: str = ""


TickCallback = Callable[[Tick], None]


class StreamManager:
    """Holds latest quotes per symbol and dispatches ticks to subscribers."""

    def __init__(self):
        self._latest: dict[str, Tick] = {}
        self._subscribers: list[TickCallback] = []

    def publish(self, tick: Tick) -> None:
        self._latest[tick.symbol] = tick
        for cb in self._subscribers:
            try:
                cb(tick)
            except Exception:
                # A faulty subscriber must not break the stream.
                pass

    def subscribe(self, callback: TickCallback) -> int:
        """Register a callback. Returns a handle usable for unsubscribe."""
        self._subscribers.append(callback)
        return id(callback)

    def unsubscribe(self, handle: int) -> None:
        self._subscribers = [c for c in self._subscribers if id(c) != handle]

    def snapshot(self) -> list[Tick]:
        return list(self._latest.values())

    def latest(self, symbol: str) -> Tick | None:
        return self._latest.get(symbol)
