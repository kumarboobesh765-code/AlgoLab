"""Market data abstraction.

All strategy/backtest/paper engines must consume data through
`MarketDataProvider` implementations — never through a vendor SDK directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Candle:
    """Normalized OHLCV candle (provider-agnostic)."""

    timestamp: datetime
    instrument_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    oi: float | None = None


class ProviderError(Exception):
    """Raised when a market-data provider is unavailable, misconfigured or fails."""


class MarketDataProvider(ABC):
    """Base interface every market-data adapter must implement.

    Implementations: DemoProvider (Phase 1), DhanProvider (Phase 2),
    TrueDataProvider / NSEProvider (future).
    """

    name: str = "base"
    is_demo: bool = False

    @abstractmethod
    async def get_instruments(self) -> list[dict]:
        """Return the instrument master supported by this provider."""

    @abstractmethod
    async def get_historical_data(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Candle]:
        """Return normalized historical candles for a symbol."""

    @abstractmethod
    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        """Return a normalized option chain snapshot."""
