"""SEBI retail-algo compliance guards.

- OrderRateLimiter: sliding-window OPS (orders-per-second) limiter.
  SEBI's framework sets 10 orders/second as the threshold above which a
  retail API user must register as an algo provider; brokers cap at 10 OPS
  regardless. The OMS refuses submissions beyond this rate per user.

- OTRTracker: order-to-trade ratio monitoring. Exchanges flag accounts whose
  order-to-trade ratio is excessive; we track it per session and expose it
  through the risk status so operators can see it before the exchange does.
"""

import time
from collections import defaultdict, deque

# SEBI circular CIR/2025/0000013 threshold; brokers enforce the same cap.
SEBI_MAX_OPS = 10


class OrderRateLimiter:
    """Per-key sliding-window OPS limiter (key = user/broker identity)."""

    def __init__(self, max_ops: int = SEBI_MAX_OPS, window_seconds: float = 1.0):
        self.max_ops = max_ops
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        """True when one more order is permitted within the window."""
        t = time.monotonic() if now is None else now
        q = self._events[key]
        cutoff = t - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= self.max_ops:
            return False
        q.append(t)
        return True

    def current_rate(self, key: str, now: float | None = None) -> int:
        """Orders recorded inside the active window for the key."""
        t = time.monotonic() if now is None else now
        q = self._events[key]
        cutoff = t - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return len(q)


class OTRTracker:
    """Rolling order-to-trade ratio tracker."""

    def __init__(self, warn_threshold: float = 10.0):
        self.orders_placed = 0
        self.trades_executed = 0
        self.warn_threshold = warn_threshold

    def record_order(self) -> None:
        self.orders_placed += 1

    def record_trade(self, quantity: int = 1) -> None:
        self.trades_executed += quantity

    @property
    def ratio(self) -> float | None:
        """OTR as orders/trades; None when no trades yet (avoid div-by-zero)."""
        if self.trades_executed == 0:
            return None
        return round(self.orders_placed / self.trades_executed, 2)

    def is_excessive(self) -> bool:
        r = self.ratio
        return r is not None and r > self.warn_threshold


# Process-wide limiter shared across OrderManager instances (per user key).
_global_limiter = OrderRateLimiter()


def get_rate_limiter() -> OrderRateLimiter:
    return _global_limiter
