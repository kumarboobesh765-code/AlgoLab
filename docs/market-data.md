# Market Data

## Provider abstraction

All market data flows through `MarketDataProvider` (`apps/api/app/marketdata/base.py`):

```python
class MarketDataProvider(ABC):
    name: str
    is_demo: bool

    async def get_instruments(self) -> list[dict]: ...
    async def get_historical_data(self, symbol, interval, start, end) -> list[Candle]: ...
    async def get_option_chain(self, underlying, expiry=None) -> dict: ...
```

The strategy engine, backtest engine and paper engine must never import a vendor SDK.

## Demo provider (Phase 1)

`DemoProvider` generates deterministic synthetic data:

- Symbols: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX
- Sessions: Mon–Fri, 09:15–15:30 IST, 1-minute base candles aggregated to 5m/15m/30m/1h/1d
- Reproducibility: candles are seeded by `(symbol, timestamp)` — the same request always returns
  the same data, which makes tests stable
- Option chain: strikes around ATM, Black-Scholes prices/deltas, bell-curve OI

**Every response carries `is_demo: true` and the UI renders a persistent `DEMO DATA` badge.**
Synthetic data must never be presented as real market data.

## Normalized candle

```json
{
  "timestamp": "2026-08-21T09:15:00+05:30",
  "instrument_id": "NIFTY",
  "open": 24800.0,
  "high": 24812.4,
  "low": 24795.1,
  "close": 24808.2,
  "volume": 182340,
  "oi": null
}
```

## Dhan provider (Phase 2)

`DhanProvider` (`apps/api/app/marketdata/dhan.py`) implements the same interface against
DhanHQ v2. Selected with `MARKET_DATA_PROVIDER=dhan` plus `DHAN_CLIENT_ID` /
`DHAN_ACCESS_TOKEN`.

- **Instruments**: master CSV from `https://images.dhan.co/api-data/api-scrip-master.csv`,
  parsed and filtered to NSE/BSE index, equity, futures and options rows.
- **Historical candles**: `POST /charts/period`; intervals mapped
  `{1m:1, 5m:5, 15m:15, 25m:25, 1h:60, 1d:DAY}` — **30m is not offered by Dhan and raises
  `ProviderError`** (surfaced as HTTP 503).
- **Option chain**: expiry list via `GET /optionchain/expirylist`, full chain via `PUT /optionchain`.
- **Rate limiting**: requests are throttled through an async lock (min gap between calls).
- **Auth failures** (401) raise `ProviderError` instead of leaking vendor errors.

> LIVE-VERIFY markers in `dhan.py` flag response-field mappings that were written from the
> published API docs but have not yet been exercised against live credentials. Verify them
> during the first real-data smoke test (especially SENSEX `IDX_B` segment).

## Ingestion pipeline

`POST /api/v1/data/history/ingest` → `app/services/ingest.py`:

1. Resolve symbol → instrument row (404-style error if the master hasn't been synced).
2. Fetch candles from the active provider.
3. Normalize timestamps to **UTC**, drop duplicates within the batch.
4. Validate (`app/services/validation.py`) — issue types: `empty`, `invalid_ohlc`,
   `duplicate_timestamp`, `abnormal_jump`, `misaligned_timestamp`, `outside_market_hours`.
5. Upsert into the segment's candle table (idempotent; re-runs never duplicate rows).
6. Return stats + a coverage report (`healthy` / `warning` / `critical` vs expected NSE bars).

Range is capped by `INGEST_MAX_DAYS` (default 90). Ingestion runs inline for now;
long backfills move to background jobs later.

## Caching

Option chains are cached per `(underlying, expiry)` for `OPTION_CHAIN_CACHE_TTL` seconds
(20s default). Redis is used when `REDIS_URL` is set; otherwise a process-local TTL cache
keeps dev environments dependency-free.

## Data-quality endpoints

- `GET /api/v1/data/quality/{symbol}?interval=5m&days=30` — validates stored candles.
- `GET /api/v1/data/status` — instrument count, candle counts per segment, latest timestamps.
