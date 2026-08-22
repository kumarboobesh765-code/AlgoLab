"""DhanHQ v2 market-data adapter.

Implements the `MarketDataProvider` interface against Dhan's REST API:
  - instrument master CSV (public download, no auth)
  - historical charts (POST /charts/period)
  - option chain (PUT /optionchain) + expiry list (GET /optionchain/expirylist)

STATUS: implemented against the published DhanHQ v2 API contract and covered by
unit tests with mocked HTTP responses. It has NOT yet been verified against the
live API because no credentials were available — field mappings marked with
`# LIVE-VERIFY` must be confirmed during first real integration.

The rest of the system never imports this module directly; it goes through
`app.marketdata.factory`.
"""

import asyncio
import csv
import io
import time
from datetime import UTC, date, datetime

import httpx

from app.core.config import get_settings
from app.marketdata.base import Candle, MarketDataProvider, ProviderError

# Well-known Dhan security IDs for major indices.
DHAN_INDICES: dict[str, dict] = {
    "NIFTY": {"security_id": "13", "exchange": "NSE", "exchange_segment": "IDX_I"},
    "BANKNIFTY": {"security_id": "25", "exchange": "NSE", "exchange_segment": "IDX_I"},
    "FINNIFTY": {"security_id": "27", "exchange": "NSE", "exchange_segment": "IDX_I"},
    "MIDCPNIFTY": {"security_id": "442", "exchange": "NSE", "exchange_segment": "IDX_I"},
    # LIVE-VERIFY: confirm BSE index segment id ("IDX_B") against live API.
    "SENSEX": {"security_id": "51", "exchange": "BSE", "exchange_segment": "IDX_B"},
}

# DhanHQ v2 supported chart intervals. 30m is NOT offered by Dhan — callers
# must aggregate from a lower interval themselves (never silently substitute).
INTERVAL_MAP = {"1m": "1", "5m": "5", "15m": "15", "25m": "25", "1h": "60", "1d": "DAY"}

INSTRUMENT_TYPE_TO_SEGMENT = {
    "INDEX": "index",
    "EQUITY": "equity",
    "FUTIDX": "futures",
    "FUTSTK": "futures",
    "OPTIDX": "options",
    "OPTSTK": "options",
}

MASTER_COLUMNS = {
    "security_id": "SEM_SMST_SECURITY_ID",
    "exchange": "SEM_EXM_EXCH_ID",
    "instrument_type": "SEM_INSTRUMENT_NAME",
    "trading_symbol": "SEM_TRADING_SYMBOL",
    "custom_symbol": "SEM_CUSTOM_SYMBOL",
    "lot_size": "SEM_LOT_UNITS",
    "expiry_date": "SEM_EXPIRY_DATE",
    "expiry_code": "SEM_EXPIRY_CODE",
    "strike_price": "SEM_STRIKE_PRICE",
    "option_type": "SEM_OPTION_TYPE",
    "tick_size": "SEM_TICK_SIZE",
}


class DhanProvider(MarketDataProvider):
    name = "dhan"
    is_demo = False

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        if not settings.DHAN_ACCESS_TOKEN or not settings.DHAN_CLIENT_ID:
            raise ProviderError(
                "Dhan credentials are not configured. Set DHAN_CLIENT_ID and "
                "DHAN_ACCESS_TOKEN in your environment, or use MARKET_DATA_PROVIDER=demo."
            )
        self._settings = settings
        self._auth_headers = {
            "access-token": settings.DHAN_ACCESS_TOKEN,
            "client-id": settings.DHAN_CLIENT_ID,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._client = http_client or httpx.AsyncClient(
            base_url=settings.DHAN_BASE_URL,
            headers=dict(self._auth_headers),
            timeout=httpx.Timeout(30.0),
        )
        self._min_request_gap = 1.0 / max(settings.DHAN_RATE_LIMIT_PER_SEC, 0.1)
        self._last_request_at = 0.0
        self._throttle_lock = asyncio.Lock()
        self._master_by_symbol: dict[str, dict] | None = None
        self._master_by_security: dict[tuple[str, str], dict] | None = None
        self._master_loaded_at: float = 0.0

    # ------------------------------------------------------------------ HTTP
    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {**self._auth_headers, **(kwargs.pop("headers", None) or {})}
        async with self._throttle_lock:
            wait = self._min_request_gap - (time.monotonic() - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()
        try:
            resp = await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Dhan request failed: {exc}") from exc
        if resp.status_code != 200:
            detail = resp.text[:300]
            try:
                body = resp.json()
                detail = body.get("errorMessage") or detail
            except Exception:
                pass
            raise ProviderError(f"Dhan API error {resp.status_code}: {detail}")
        return resp

    # ------------------------------------------------------- instrument master
    def _parse_master_row(self, row: dict) -> dict | None:
        itype = (row.get(MASTER_COLUMNS["instrument_type"]) or "").strip().upper()
        segment_kind = INSTRUMENT_TYPE_TO_SEGMENT.get(itype)
        if segment_kind is None:
            return None
        exchange = (row.get(MASTER_COLUMNS["exchange"]) or "").strip().upper()
        security_id = (row.get(MASTER_COLUMNS["security_id"]) or "").strip()
        if not exchange or not security_id:
            return None

        expiry_raw = (row.get(MASTER_COLUMNS["expiry_date"]) or "").strip()
        expiry: date | None = None
        if expiry_raw:
            try:
                expiry = date.fromisoformat(expiry_raw)
            except ValueError:
                expiry = None  # tolerate unexpected formats; keep the row

        strike_raw = (row.get(MASTER_COLUMNS["strike_price"]) or "").strip()
        try:
            strike = float(strike_raw) if strike_raw else None
        except ValueError:
            strike = None

        option_type = (row.get(MASTER_COLUMNS["option_type"]) or "").strip().upper() or None
        if option_type in {"XC", "XX"}:  # non-standard codes in some master dumps
            option_type = option_type[-1]

        symbol = (row.get(MASTER_COLUMNS["trading_symbol"]) or "").strip()
        name = (row.get(MASTER_COLUMNS["custom_symbol"]) or "").strip() or symbol

        def _int(value: str, default: int) -> int:
            try:
                return int(float(value)) if value else default
            except (TypeError, ValueError):
                return default

        def _float(value: str, default: float) -> float:
            try:
                return float(value) if value else default
            except (TypeError, ValueError):
                return default

        exchange_segment = self._exchange_segment(exchange, segment_kind)
        underlying = symbol
        if segment_kind in {"futures", "options"} and len(symbol) > 3:
            # strip trailing month/year tokens heuristically; refined in Phase 3
            underlying = symbol.rstrip("0123456789")

        return {
            "security_id": security_id,
            "exchange": exchange,
            "segment": segment_kind,
            "exchange_segment": exchange_segment,
            "symbol": symbol,
            "name": name,
            "underlying": underlying,
            "instrument_type": itype,
            "expiry_code": _int(row.get(MASTER_COLUMNS["expiry_code"]) or "", 0),
            "expiry": expiry,
            "strike": strike,
            "option_type": option_type,
            "lot_size": _int(row.get(MASTER_COLUMNS["lot_size"]) or "", 1),
            "tick_size": _float(row.get(MASTER_COLUMNS["tick_size"]) or "", 0.05),
            "status": "active",
        }

    @staticmethod
    def _exchange_segment(exchange: str, segment_kind: str) -> str:
        """Map (exchange, kind) to Dhan exchangeSegment enums."""
        if segment_kind == "index":
            return "IDX_I" if exchange == "NSE" else "IDX_B"
        prefix = "NSE" if exchange == "NSE" else "BSE"
        suffix = {"equity": "EQ", "futures": "FNO", "options": "FNO"}[segment_kind]
        return f"{prefix}_{suffix}"

    async def _load_master(self, force: bool = False) -> tuple[dict, dict]:
        """Download + parse the scrip master CSV into lookup indexes (24h cache)."""
        max_age = 24 * 3600
        if (
            not force
            and self._master_by_symbol is not None
            and time.monotonic() - self._master_loaded_at < max_age
        ):
            return self._master_by_symbol, self._master_by_security

        try:
            resp = await self._client.get(self._settings.DHAN_MASTER_CSV_URL)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Failed to download Dhan instrument master: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"Dhan instrument master download failed: HTTP {resp.status_code}")

        by_symbol: dict[str, dict] = {}
        by_security: dict[tuple[str, str], dict] = {}
        reader = csv.DictReader(io.StringIO(resp.text))
        missing = [col for col in MASTER_COLUMNS.values() if col not in (reader.fieldnames or [])]
        if missing:
            raise ProviderError(
                "Dhan instrument master format changed; missing columns: "
                f"{missing}. Update MASTER_COLUMNS mapping."
            )
        for row in reader:
            parsed = self._parse_master_row(row)
            if parsed is None:
                continue
            by_symbol.setdefault(parsed["symbol"], parsed)
            by_security[(parsed["exchange"], parsed["security_id"])] = parsed

        self._master_by_symbol = by_symbol
        self._master_by_security = by_security
        self._master_loaded_at = time.monotonic()
        return by_symbol, by_security

    async def get_instruments(self) -> list[dict]:
        by_symbol, _ = await self._load_master()
        return list(by_symbol.values())

    # ---------------------------------------------------------------- candles
    async def _resolve(self, symbol: str) -> dict:
        symbol = symbol.strip().upper()
        if symbol in DHAN_INDICES:
            base = DHAN_INDICES[symbol]
            return {
                **base,
                "segment": "index",
                "instrument_type": "INDEX",
                "expiry_code": 0,
                "symbol": symbol,
            }
        by_symbol, by_security = await self._load_master()
        record = by_symbol.get(symbol)
        if record is None and symbol.isdigit():
            # search all exchanges for this numeric security id
            matches = [r for (ex, sid), r in by_security.items() if sid == symbol]
            if len(matches) == 1:
                record = matches[0]
        if record is None:
            raise ProviderError(
                f"Unknown Dhan instrument '{symbol}'. Use a trading symbol or security_id "
                "present in the instrument master."
            )
        return record

    @staticmethod
    def _parse_timestamp(value) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    async def get_historical_data(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Candle]:
        if interval not in INTERVAL_MAP:
            raise ProviderError(
                f"Dhan does not support interval '{interval}'. Supported: {sorted(INTERVAL_MAP)}. "
                "Aggregate from a lower interval instead of assuming data exists."
            )
        record = await self._resolve(symbol)
        payload = {
            "securityId": record["security_id"],
            "exchangeSegment": record["exchange_segment"],
            "instrument": record["instrument_type"],
            "expiryCode": record.get("expiry_code", 0),
            "oi": True,
            "interval": INTERVAL_MAP[interval],
            "fromDate": start.date().isoformat(),
            "toDate": end.date().isoformat(),
        }
        resp = await self._request("POST", "/charts/period", json=payload)
        data = resp.json()

        # LIVE-VERIFY: response is parallel arrays per DhanHQ v2 docs.
        timestamps = data.get("timestamp") or []
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        volumes = data.get("volume") or []
        ois = data.get("oi") or []

        candles: list[Candle] = []
        for i, ts in enumerate(timestamps):
            if i >= len(opens) or i >= len(closes):
                break
            oi_value = ois[i] if i < len(ois) else None
            candles.append(
                Candle(
                    timestamp=self._parse_timestamp(ts),
                    instrument_id=record["symbol"],
                    open=float(opens[i]),
                    high=float(highs[i]) if i < len(highs) else float(opens[i]),
                    low=float(lows[i]) if i < len(lows) else float(opens[i]),
                    close=float(closes[i]),
                    volume=float(volumes[i]) if i < len(volumes) else 0.0,
                    oi=float(oi_value) if oi_value is not None else None,
                )
            )
        return candles

    # ------------------------------------------------------------ option chain
    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        symbol = underlying.strip().upper()
        if symbol not in DHAN_INDICES:
            by_symbol, _ = await self._load_master()
            if symbol not in by_symbol:
                raise ProviderError(f"Unknown Dhan underlying '{underlying}'.")
        record = DHAN_INDICES[symbol]

        if expiry is None:
            resp = await self._request(
                "GET",
                "/optionchain/expirylist",
                params={
                    "UnderlyingScrip": record["security_id"],
                    "UnderlyingSeg": record["exchange_segment"],
                },
            )
            expiries = resp.json().get("data") or []
            if not expiries:
                raise ProviderError(f"Dhan returned no expiries for {symbol}.")
            expiry = expiries[0]

        resp = await self._request(
            "PUT",
            "/optionchain",
            json={
                "UnderlyingScrip": int(record["security_id"]),
                "UnderlyingSeg": record["exchange_segment"],
                "Expiry": expiry,
            },
        )
        raw_rows = resp.json().get("data") or []

        strikes = []
        for row in raw_rows:
            strikes.append(
                {
                    "strike": int(row.get("strike_price", 0)),
                    "call_ltp": float(row.get("call_ltp") or 0),
                    "put_ltp": float(row.get("put_ltp") or 0),
                    "call_iv": float(row.get("call_iv") or 0),
                    "put_iv": float(row.get("put_iv") or 0),
                    "call_oi": float(row.get("call_oi") or 0),
                    "put_oi": float(row.get("put_oi") or 0),
                    "call_volume": float(row.get("call_volume") or 0),
                    "put_volume": float(row.get("put_volume") or 0),
                    "call_delta": float(row.get("call_delta") or 0),
                    "put_delta": float(row.get("put_delta") or 0),
                }
            )
        strikes.sort(key=lambda r: r["strike"])

        return {
            "underlying": symbol,
            "spot": float(resp.json().get("last_price") or 0),  # LIVE-VERIFY field name
            "expiry": expiry,
            "strikes": strikes,
            "provider": self.name,
            "is_demo": self.is_demo,
        }
