"""Tests for the DhanHQ v2 adapter using mocked HTTP responses."""

from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import get_settings
from app.marketdata.base import ProviderError
from app.marketdata.dhan import DhanProvider

MASTER_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE
NSE,I,13,INDEX,0,NIFTY 50,1,NIFTY,,,,
NSE,E,11536,EQUITY,0,TCS,1,TCS,,,,0.05
NSE,D,47081,FUTIDX,1,NIFTY25AUGFUT,75,NIFTY 28 AUG FUT,2026-08-27,0,,0.05
NSE,D,47090,OPTIDX,1,NIFTY25AUG25000CE,75,NIFTY 25000 CE,2026-08-27,25000,CE,0.05
MCX,D,123456,FUTCOM,1,GOLD25OCTFUT,100,GOLD OCT FUT,2026-10-05,0,,1.00
"""

TS0 = int(datetime(2026, 8, 21, 3, 45, tzinfo=UTC).timestamp())  # 09:15 IST


def make_provider(handler) -> DhanProvider:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.dhan.co/v2",
    )
    return DhanProvider(http_client=client)


@pytest.fixture
def dhan_env(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "test-access-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def master_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=MASTER_CSV)


async def test_missing_credentials_raise(dhan_env, monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID")
    monkeypatch.delenv("DHAN_ACCESS_TOKEN")
    get_settings.cache_clear()
    with pytest.raises(ProviderError, match="credentials are not configured"):
        DhanProvider()
    get_settings.cache_clear()


async def test_auth_headers_sent(dhan_env):
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(dict(request.headers))
        return httpx.Response(200, json={"timestamp": [], "open": []})

    provider = make_provider(handler)
    await provider.get_historical_data(
        "NIFTY", "5m", datetime(2026, 8, 21), datetime(2026, 8, 21)
    )
    assert seen_headers.get("access-token") == "test-access-token"
    assert seen_headers.get("client-id") == "test-client-id"


async def test_instruments_parse_and_filter(dhan_env):
    async def combined_handler(request: httpx.Request) -> httpx.Response:
        return master_handler(request)

    provider = make_provider(combined_handler)
    instruments = await provider.get_instruments()

    by_symbol = {i["symbol"]: i for i in instruments}
    # MCX FUTCOM row must be filtered out (unsupported instrument type)
    assert "GOLD25OCTFUT" not in by_symbol
    assert len(instruments) == 4

    nifty = by_symbol["NIFTY 50"]
    assert nifty["security_id"] == "13"
    assert nifty["segment"] == "index"
    assert nifty["exchange_segment"] == "IDX_I"

    tcs = by_symbol["TCS"]
    assert tcs["segment"] == "equity"
    assert tcs["tick_size"] == 0.05

    opt = by_symbol["NIFTY25AUG25000CE"]
    assert opt["segment"] == "options"
    assert opt["strike"] == 25000.0
    assert opt["option_type"] == "CE"
    assert opt["expiry"].isoformat() == "2026-08-27"
    assert opt["lot_size"] == 75


async def test_historical_candles_parse(dhan_env):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "images.dhan.co":
            return master_handler(request)
        payload = {
            "timestamp": [TS0, TS0 + 300],
            "open": [24800.5, 24810.0],
            "high": [24812.0, 24820.0],
            "low": [24795.0, 24805.0],
            "close": [24808.0, 24818.5],
            "volume": [125000, 131000],
            "oi": [None, None],
        }
        return httpx.Response(200, json=payload)

    provider = make_provider(handler)
    candles = await provider.get_historical_data(
        "NIFTY", "5m", datetime(2026, 8, 21), datetime(2026, 8, 21)
    )
    assert len(candles) == 2
    assert candles[0].close == 24808.0
    assert candles[0].timestamp.hour == 3  # UTC
    assert candles[0].oi is None
    assert candles[1].volume == 131000


async def test_unsupported_interval_rejected(dhan_env):
    provider = make_provider(master_handler)
    with pytest.raises(ProviderError, match="does not support interval '30m'"):
        await provider.get_historical_data(
            "NIFTY", "30m", datetime(2026, 8, 21), datetime(2026, 8, 21)
        )


async def test_unknown_symbol_raises(dhan_env):
    provider = make_provider(master_handler)
    with pytest.raises(ProviderError, match="Unknown Dhan instrument"):
        await provider.get_historical_data(
            "NOTAREALSYMBOL", "5m", datetime(2026, 8, 21), datetime(2026, 8, 21)
        )


async def test_api_error_maps_to_provider_error(dhan_env):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "images.dhan.co":
            return master_handler(request)
        return httpx.Response(
            401, json={"errorCode": "DH-904", "errorMessage": "Authentication failed"}
        )

    provider = make_provider(handler)
    with pytest.raises(ProviderError, match="Authentication failed"):
        await provider.get_historical_data(
            "NIFTY", "5m", datetime(2026, 8, 21), datetime(2026, 8, 21)
        )


async def test_option_chain_flow(dhan_env):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/optionchain/expirylist"):
            return httpx.Response(200, json={"data": ["2026-08-27", "2026-09-03"]})
        if request.url.path.endswith("/optionchain"):
            body = {
                "data": [
                    {"strike_price": 24750, "call_ltp": 180.5, "put_ltp": 95.2, "call_oi": 1.2e6},
                    {"strike_price": 24800, "call_ltp": 150.1, "put_ltp": 120.4, "call_oi": 2.4e6},
                ],
                "last_price": 24810.25,
            }
            return httpx.Response(200, json=body)
        return master_handler(request)

    provider = make_provider(handler)
    chain = await provider.get_option_chain("NIFTY")

    assert chain["provider"] == "dhan"
    assert chain["is_demo"] is False
    assert chain["expiry"] == "2026-08-27"  # nearest expiry auto-selected
    assert chain["spot"] == 24810.25
    assert [s["strike"] for s in chain["strikes"]] == [24750, 24800]
