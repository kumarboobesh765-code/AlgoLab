"""Demo market-data provider.

Generates deterministic synthetic Indian-market data (NIFTY/BANKNIFTY/... index
candles plus a synthetic option chain) so the platform is fully usable without
broker credentials. Every response is clearly labeled `is_demo=True`.

NEVER present this data as real market data.
"""

import hashlib
import math
from datetime import datetime, time, timedelta, timezone

from app.marketdata.base import Candle, MarketDataProvider

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# symbol -> (name, base_price, lot_size, strike_step)
DEMO_INDICES: dict[str, tuple[str, float, int, int]] = {
    "NIFTY": ("Nifty 50", 24800.0, 75, 50),
    "BANKNIFTY": ("Nifty Bank", 51200.0, 35, 100),
    "FINNIFTY": ("Nifty Financial Services", 23100.0, 65, 50),
    "MIDCPNIFTY": ("Nifty Midcap Select", 12350.0, 120, 25),
    "SENSEX": ("BSE Sensex", 81400.0, 20, 100),
}

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 375}


def _seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


class _Rng:
    """Small deterministic PRNG (xorshift) so demo data is reproducible."""

    def __init__(self, seed: int) -> None:
        self.state = seed or 0x9E3779B97F4A7C15

    def next_u64(self) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        self.state = x
        return x

    def uniform(self, lo: float = 0.0, hi: float = 1.0) -> float:
        return lo + (hi - lo) * (self.next_u64() >> 11) / float(1 << 53)

    def normal(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        u1 = max(self.uniform(), 1e-12)
        u2 = self.uniform()
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


class DemoProvider(MarketDataProvider):
    name = "demo"
    is_demo = True

    async def get_instruments(self) -> list[dict]:
        """Normalized instrument records (same shape as the Dhan adapter emits)."""
        instruments = []
        for symbol, (name, base_price, lot_size, strike_step) in DEMO_INDICES.items():
            instruments.append(
                {
                    "security_id": f"DEMO-{symbol}",
                    "exchange": "NSE" if symbol != "SENSEX" else "BSE",
                    "segment": "index",
                    "exchange_segment": "IDX_I" if symbol != "SENSEX" else "IDX_B",
                    "symbol": symbol,
                    "name": name,
                    "underlying": symbol,
                    "instrument_type": "INDEX",
                    "expiry_code": 0,
                    "expiry": None,
                    "strike": None,
                    "option_type": None,
                    "lot_size": lot_size,
                    "tick_size": 0.05,
                    "status": "active",
                }
            )
        return instruments

    async def get_historical_data(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Candle]:
        if interval not in INTERVAL_MINUTES:
            raise ValueError(f"Unsupported interval '{interval}'. Supported: {sorted(INTERVAL_MINUTES)}")
        meta = DEMO_INDICES.get(symbol.upper())
        if meta is None:
            raise ValueError(f"Unknown demo symbol '{symbol}'. Available: {sorted(DEMO_INDICES)}")
        _, base_price, _, _ = meta

        minutes = [d for d in self._market_minutes(start, end)]
        if not minutes:
            return []

        candles_1m: list[Candle] = []
        current_day: datetime | None = None
        day_open = base_price
        price = base_price

        for ts in minutes:
            if current_day != ts.date():
                # new trading day: gap open seeded by the calendar date
                rng_day = _Rng(_seed(symbol, ts.date().isoformat()))
                current_day = ts.date()
                gap_pct = rng_day.normal(0, 0.0035)
                day_open = round(price * (1 + gap_pct), 2)
                price = day_open
            rng = _Rng(_seed(symbol, ts.isoformat()))
            drift = rng.normal(0, base_price * 0.00045)
            open_px = price
            close_px = max(open_px + drift, base_price * 0.5)
            high_px = max(open_px, close_px) + abs(rng.normal(0, base_price * 0.00022))
            low_px = min(open_px, close_px) - abs(rng.normal(0, base_price * 0.00022))
            volume = float(int(abs(rng.normal(180_000, 55_000))))
            candles_1m.append(
                Candle(
                    timestamp=ts,
                    instrument_id=symbol.upper(),
                    open=round(open_px, 2),
                    high=round(high_px, 2),
                    low=round(max(low_px, 1.0), 2),
                    close=round(close_px, 2),
                    volume=volume,
                )
            )
            price = close_px

        step = INTERVAL_MINUTES[interval]
        if step == 1:
            return candles_1m
        return self._aggregate(candles_1m, step)

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        symbol = underlying.upper()
        meta = DEMO_INDICES.get(symbol)
        if meta is None:
            raise ValueError(f"Unknown demo underlying '{underlying}'.")
        _, base_price, _, strike_step = meta

        spot_rng = _Rng(_seed("spot", symbol, datetime.now(IST).date().isoformat()))
        spot = round(base_price * (1 + spot_rng.normal(0, 0.01)), 2)

        atm = round(spot / strike_step) * strike_step
        strikes = [atm + i * strike_step for i in range(-10, 11)]

        # nearest Thursday as weekly expiry (demo approximation)
        today = datetime.now(IST).date()
        days_ahead = (3 - today.weekday()) % 7
        expiry_date = today + timedelta(days=days_ahead)
        dte = max((expiry_date - today).days, 0.5)

        rows = []
        for k in strikes:
            call_iv = 0.13 + abs(k - atm) / atm * 0.35
            put_iv = call_iv + 0.008
            call_ltp = self._theo_price(spot, k, dte / 365.0, call_iv, "call")
            put_ltp = self._theo_price(spot, k, dte / 365.0, put_iv, "put")
            oi_falloff = math.exp(-((k - atm) ** 2) / (2 * (4.0 * strike_step) ** 2))
            rows.append(
                {
                    "strike": k,
                    "call_ltp": round(call_ltp, 2),
                    "put_ltp": round(put_ltp, 2),
                    "call_iv": round(call_iv * 100, 2),
                    "put_iv": round(put_iv * 100, 2),
                    "call_oi": round(2_400_000 * oi_falloff * (1.05 if k >= atm else 0.95)),
                    "put_oi": round(2_600_000 * oi_falloff * (1.05 if k <= atm else 0.95)),
                    "call_volume": round(900_000 * oi_falloff),
                    "put_volume": round(850_000 * oi_falloff),
                    "call_delta": round(self._bs_delta(spot, k, dte / 365.0, call_iv, "call"), 4),
                    "put_delta": round(self._bs_delta(spot, k, dte / 365.0, put_iv, "put"), 4),
                }
            )

        return {
            "underlying": symbol,
            "spot": spot,
            "expiry": expiry_date.isoformat(),
            "strikes": rows,
            "provider": self.name,
            "is_demo": self.is_demo,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _market_minutes(start: datetime, end: datetime) -> list[datetime]:
        """All 1-minute timestamps inside NSE hours (09:15-15:29 IST) between start and end."""
        # Naive inputs are interpreted as IST (Indian-market platform convention).
        if start.tzinfo is None:
            start = start.replace(tzinfo=IST)
        if end.tzinfo is None:
            end = end.replace(tzinfo=IST)
        start = start.astimezone(IST)
        end = end.astimezone(IST)
        minutes: list[datetime] = []
        day = start.date()
        while day <= end.date():
            if day.weekday() < 5:  # Mon-Fri only
                session_start = datetime.combine(day, MARKET_OPEN, tzinfo=IST)
                session_end = datetime.combine(day, MARKET_CLOSE, tzinfo=IST)
                t = max(session_start, start.replace(second=0, microsecond=0))
                last = min(session_end, end)
                while t < last:
                    minutes.append(t)
                    t += timedelta(minutes=1)
            day += timedelta(days=1)
        return minutes

    @staticmethod
    def _aggregate(candles: list[Candle], step: int) -> list[Candle]:
        out: list[Candle] = []
        for i in range(0, len(candles), step):
            chunk = candles[i : i + step]
            if not chunk:
                continue
            out.append(
                Candle(
                    timestamp=chunk[0].timestamp,
                    instrument_id=chunk[0].instrument_id,
                    open=chunk[0].open,
                    high=max(c.high for c in chunk),
                    low=min(c.low for c in chunk),
                    close=chunk[-1].close,
                    volume=sum(c.volume for c in chunk),
                )
            )
        return out

    @staticmethod
    def _bs_d1(spot: float, strike: float, years: float, iv: float) -> float:
        r = 0.065
        sqrt_t = math.sqrt(years)
        return (math.log(spot / strike) + (r + 0.5 * iv * iv) * years) / (iv * sqrt_t)

    def _bs_delta(self, spot: float, strike: float, years: float, iv: float, kind: str) -> float:
        if years <= 0 or iv <= 0:
            return 1.0 if (kind == "call" and spot > strike) else 0.0
        d1 = self._bs_d1(spot, strike, years, iv)
        nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        return nd1 if kind == "call" else nd1 - 1.0

    def _theo_price(self, spot: float, strike: float, years: float, iv: float, kind: str) -> float:
        r = 0.065
        intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
        if years <= 0 or iv <= 0:
            return intrinsic
        d1 = self._bs_d1(spot, strike, years, iv)
        d2 = d1 - iv * math.sqrt(years)
        nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        if kind == "call":
            return spot * nd1 - strike * math.exp(-r * years) * nd2
        return strike * math.exp(-r * years) * (1 - nd2) - spot * (1 - nd1)
