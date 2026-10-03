"""Contract tests for the MCP server.

Tools are called directly (the underlying functions, not the transport) so the
tests assert on the JSON an agent actually receives. The MCP registry is
checked separately, because a tool that exists but is unreachable is worse
than a missing one.
"""

import asyncio
import json

import pytest

from app import mcp_server as mcp_mod
from app.quant.indicators import INDICATORS


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def demo_provider(monkeypatch):
    """A deterministic in-process provider, so candle tests never touch HTTP."""
    from datetime import UTC, datetime, timedelta

    from app.marketdata.base import Candle

    class Fake:
        name = "test"
        is_demo = False

        async def get_historical_data(self, symbol, interval, start, end):
            base = datetime(2026, 1, 1, tzinfo=UTC)
            out = []
            price = 100.0
            for i in range(200):
                price += (i % 7) * 0.5 - 1.0
                out.append(
                    Candle(
                        timestamp=base + timedelta(minutes=i),
                        instrument_id="NIFTY",
                        open=price,
                        high=price + 2,
                        low=price - 2,
                        close=price + 0.25,
                        volume=1000 + i,
                        oi=5000 + i * 10,
                    )
                )
            return out

    fake = Fake()
    monkeypatch.setattr(mcp_mod, "get_provider", lambda: fake)
    return fake


# --- registry ---------------------------------------------------------------


def test_all_tools_registered():
    """Every exposed tool must be discoverable through the MCP server."""
    tools = asyncio.run(mcp_mod.server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_indicators",
        "get_candles",
        "compute_indicators",
        "option_chain",
        "basket_payoff",
        "list_strategies",
        "get_strategy",
        "health",
    }
    assert expected <= names


def test_tools_have_schemas():
    tools = asyncio.run(mcp_mod.server.list_tools())
    for tool in tools:
        assert tool.description, f"{tool.name} missing description"
        assert tool.input_schema["type"] == "object", f"{tool.name} bad input schema"


def test_registry_covers_indicator_count():
    """list_indicators must advertise the whole library, not a hand-written subset."""
    payload = json.loads(run(mcp_mod.list_indicators()))
    assert payload["count"] == len(INDICATORS) > 50
    types = {i["type"] for i in payload["indicators"]}
    assert types == set(INDICATORS)
    # option analytics must be advertised as real, not stubs
    assert {"OPTION_DELTA", "OPTION_GAMMA", "OPTION_VEGA"} <= types


# --- health ----------------------------------------------------------------


def test_health_reports_provider():
    payload = json.loads(run(mcp_mod.health()))
    assert payload["status"] == "ok"
    assert payload["provider"]
    assert payload["indicators"] == len(INDICATORS)


# --- candles ---------------------------------------------------------------


def test_get_candles_shape(demo_provider):
    payload = json.loads(run(mcp_mod.get_candles("NIFTY", "5m", 50)))
    assert payload["symbol"] == "NIFTY"
    assert payload["bars"] == 50
    assert len(payload["candles"]) == 50
    first = payload["candles"][0]
    assert {"time", "open", "high", "low", "close", "volume"} <= set(first)
    times = [c["time"] for c in payload["candles"]]
    assert times == sorted(times), "candles must be oldest first"


def test_get_candles_rejects_bad_interval(demo_provider):
    out = json.loads(run(mcp_mod.get_candles("NIFTY", "7m", 50)))
    assert "error" in out


def test_get_candles_rejects_absurd_bars(demo_provider):
    assert "error" in json.loads(run(mcp_mod.get_candles("NIFTY", "5m", 99999)))


# --- indicators ------------------------------------------------------------


def test_compute_indicators_series_aligned_to_price(demo_provider):
    payload = json.loads(run(mcp_mod.compute_indicators("NIFTY", "5m", "SMA:20,RSI:14", 200)))
    n = payload["bars"]
    assert len(payload["times"]) == n
    assert len(payload["close"]) == n
    for token in ("SMA:20", "RSI:14"):
        for values in payload["series"][token].values():
            assert len(values) == n, f"{token} not index-aligned"


def test_compute_indicators_null_warmup_not_nan(demo_provider):
    payload = json.loads(run(mcp_mod.compute_indicators("NIFTY", "5m", "SMA:20", 60)))
    sma = payload["series"]["SMA:20"]["sma"]
    assert sma[:19] == [None] * 19, "warm-up must be null, not NaN or 0"
    assert sma[19] is not None
    # strict JSON: NaN/Infinity would have broken json.loads above
    assert "NaN" not in json.dumps(payload)


def test_compute_indicators_band_outputs(demo_provider):
    payload = json.loads(run(mcp_mod.compute_indicators("NIFTY", "5m", "BBANDS:length=20,stddev=2", 80)))
    bands = payload["series"]["BBANDS:length=20,stddev=2"]
    assert set(bands) == {"upper", "middle", "lower"}
    upper, lower = bands["upper"], bands["lower"]
    for hi, lo in zip(upper, lower, strict=True):
        if hi is None or lo is None:
            continue
        assert hi >= lo, "upper band must sit above lower"


def test_compute_indicators_isolates_bad_token(demo_provider):
    payload = json.loads(run(mcp_mod.compute_indicators("NIFTY", "5m", "SMA:20,NOT_A_THING", 60)))
    assert "SMA:20" in payload["series"], "valid indicator must survive"
    assert "NOT_A_THING" in payload["errors"], "bad token must be isolated"


def test_compute_indicators_accepts_token_grammars(demo_provider):
    """Bare, positional and explicit parameter forms all resolve."""
    payload = json.loads(run(mcp_mod.compute_indicators("NIFTY", "5m", "SMA,SMA:14,SMA:length=9", 60)))
    assert set(payload["errors"]) == set()
    assert len(payload["series"]) == 3


def test_option_greeks_served_over_mcp(demo_provider):
    """The real Black-Scholes path must be reachable from the MCP surface."""
    from datetime import UTC, datetime, timedelta

    from app.marketdata.base import Candle

    base = datetime(2026, 1, 1, tzinfo=UTC)
    expiry = (base + timedelta(days=90)).date()
    candles = [
        Candle(
            timestamp=base + timedelta(days=i),
            instrument_id="NIFTY",
            open=100, high=101, low=99, close=100 + i * 0.5,
            volume=10, oi=100,
            strike=100.0, option_type="CE", expiry=expiry,
            underlying_price=100.0, iv=0.15,
        )
        for i in range(40)
    ]

    class FakeOptProvider:
        name = "test"
        is_demo = False

        async def get_historical_data(self, symbol, interval, start, end):
            return candles

    import app.mcp_server as mm

    original = mm.get_provider
    mm.get_provider = lambda: FakeOptProvider()
    try:
        payload = json.loads(run(mm.compute_indicators("NIFTY", "1d", "OPTION_DELTA,OPTION_VEGA", 40)))
    finally:
        mm.get_provider = original
    delta = payload["series"]["OPTION_DELTA"]
    values = list(delta.values())[0]
    finite = [v for v in values if v is not None]
    assert finite, "option greeks returned nothing"
    assert all(-1.0 <= v <= 1.0 for v in finite), "delta must stay within [-1, 1]"
    vega = [v for v in list(payload["series"]["OPTION_VEGA"].values())[0] if v is not None]
    assert all(v >= 0 for v in vega), "vega is non-negative"


# --- basket ----------------------------------------------------------------


def test_basket_payoff_from_json_string():
    legs = json.dumps(
        [
            {"action": "buy", "option_type": "CE", "strike": 22000, "premium": 300, "quantity": 1},
            {"action": "buy", "option_type": "PE", "strike": 22000, "premium": 290, "quantity": 1},
        ]
    )
    payload = json.loads(run(mcp_mod.basket_payoff(legs, spot=22000, days_to_expiry=7, volatility=16)))
    assert "error" not in payload, payload.get("error")
    assert "net_premium" in payload
    assert "payoff" in payload


def test_basket_payoff_exposes_pnl_not_gross_value():
    """Agents get expiry_pnl so breakevens and max loss agree with the curve."""
    legs = json.dumps(
        [
            {"action": "buy", "option_type": "CE", "strike": 22000, "premium": 300, "quantity": 1},
            {"action": "buy", "option_type": "PE", "strike": 22000, "premium": 300, "quantity": 1},
        ]
    )
    payload = json.loads(run(mcp_mod.basket_payoff(legs, spot=22000, days_to_expiry=7, volatility=16)))
    net = payload["net_premium"]
    for point in payload["payoff"]:
        assert point["expiry_pnl"] == pytest.approx(point["expiry_value"] + net, abs=0.02)
    assert payload["max_loss"] == pytest.approx(min(p["expiry_pnl"] for p in payload["payoff"]))


def test_basket_payoff_rejects_garbage():
    out = json.loads(run(mcp_mod.basket_payoff("not json at all")))
    assert "error" in out


def test_basket_payoff_long_straddle_max_loss_is_premium():
    """Unlimited upside, worst case exactly the 600 debit."""
    legs = json.dumps(
        [
            {"action": "buy", "option_type": "CE", "strike": 22000, "premium": 300, "quantity": 1},
            {"action": "buy", "option_type": "PE", "strike": 22000, "premium": 300, "quantity": 1},
        ]
    )
    payload = json.loads(run(mcp_mod.basket_payoff(legs, spot=22000, days_to_expiry=7, volatility=16)))
    assert payload["max_profit"] is None, "long call leg means unlimited upside"
    assert payload["max_loss"] == pytest.approx(-600.0, abs=1)
    assert payload["net_premium"] == pytest.approx(-600.0, abs=1)


# --- option chain ----------------------------------------------------------


def test_option_chain_surfaces_provider_errors(monkeypatch):
    class Boom:
        name = "test"
        is_demo = True

        async def get_option_chain(self, underlying, expiry=None):
            raise RuntimeError("provider down")

    monkeypatch.setattr(mcp_mod, "get_provider", lambda: Boom())
    out = json.loads(run(mcp_mod.option_chain("NIFTY")))
    assert "error" in out
    assert "provider down" in out["error"]


def test_option_chain_passes_expiry_through(monkeypatch):
    seen = {}

    class Ok:
        name = "test"
        is_demo = False

        async def get_option_chain(self, underlying, expiry=None):
            seen["underlying"], seen["expiry"] = underlying, expiry
            return {"rows": []}

    monkeypatch.setattr(mcp_mod, "get_provider", lambda: Ok())
    payload = json.loads(run(mcp_mod.option_chain("BANKNIFTY", "2026-01-30")))
    assert seen == {"underlying": "BANKNIFTY", "expiry": "2026-01-30"}
    assert payload["provider"] == "test"
    assert payload["is_demo"] is False


# --- strategies ------------------------------------------------------------


def test_get_strategy_rejects_non_uuid():
    out = json.loads(run(mcp_mod.get_strategy("not-a-uuid")))
    assert "error" in out
    assert "UUID" in out["error"]


# --- transport -------------------------------------------------------------


def test_cli_defaults_to_stdio(monkeypatch):
    """Desktop agents use stdio; defaulting to anything else breaks them silently."""
    called = {}
    monkeypatch.setattr(mcp_mod.server, "run", lambda **kw: called.update(kw))
    assert mcp_mod.main([]) == 0
    assert called == {"transport": "stdio"}


def test_cli_http_transport_passes_host_port(monkeypatch):
    called = {}
    monkeypatch.setattr(mcp_mod.server, "run", lambda **kw: called.update(kw))
    assert mcp_mod.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert called == {"transport": "streamable-http", "host": "0.0.0.0", "port": 9000}
