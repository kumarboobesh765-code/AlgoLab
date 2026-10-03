"""Market data abstraction.

All strategy/backtest/paper engines must consume data through
`MarketDataProvider` implementations — never through a vendor SDK directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(slots=True)
class Candle:
    """Normalized OHLCV candle (provider-agnostic).

    The trailing fields are optional option context. They stay `None` for
    index/equity/futures bars, and are populated for option bars so that
    Black-Scholes indicators (delta/gamma/theta/vega/IV/price) can be computed
    per bar rather than being unavailable outside a live chain snapshot.
    """

    timestamp: datetime
    instrument_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    oi: float | None = None
    # --- option context (None for non-option segments) ---
    strike: float | None = None
    option_type: str | None = None  # "CE" | "PE"
    expiry: date | None = None
    underlying_price: float | None = None  # spot for this bar
    iv: float | None = None  # annualised decimal, e.g. 0.15


class ProviderError(Exception):
    """Raised when a market-data provider is unavailable, misconfigured or fails."""


@dataclass(slots=True)
class Tick:
    """A single live price update for one instrument.

    `candle` is the in-progress bar for the subscribed interval: it carries the
    running open/high/low/close so a consumer can paint a partial bar without
    waiting for the interval to close.
    """

    instrument_id: str
    timestamp: datetime
    last_price: float
    candle: Candle


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

    async def stream_ticks(self, symbols: list[str], interval: str):
        """Yield ticks for `symbols` until the caller stops consuming.

        Optional: providers without a live feed raise NotImplementedError and the
        API falls back to the scheduler-driven stored-candle path, so this stays
        off the abstract base and no existing adapter breaks. Declared as an
        async generator so a caller can always ``async for`` it.
        """
        raise NotImplementedError(f"{self.name} does not support tick streaming")
        yield  # pragma: no cover - unreachable, marks this an async generator

    async def supports_streaming(self) -> bool:
        """Whether stream_ticks can actually serve requests for this provider."""
        return False
