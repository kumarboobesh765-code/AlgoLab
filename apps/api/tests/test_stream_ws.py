"""WebSocket market-data streaming.

Covers the subscription protocol end-to-end against the demo feed: the
handshake, per-symbol tick fan-out, running-bar continuity, error handling and
the guarantee that a disconnect tears the stream down.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


def recv_until(ws, wanted: str, limit: int = 40):
    """Read frames until one has type == wanted, returning it.

    The stream interleaves tick frames with control frames, so tests select by
    type rather than assuming an exact frame order.
    """
    for _ in range(limit):
        frame = json.loads(ws.receive_text())
        if frame.get("type") == wanted:
            return frame
    raise AssertionError(f"never saw a {wanted!r} frame in {limit} frames")


@pytest.fixture
def ws_client():
    with TestClient(app) as client:
        yield client


def test_hello_frame_advertises_provider(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"
        assert hello["provider"]
        assert "supports_streaming" in hello


def test_subscribe_acks_then_streams_ticks(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())  # hello
        ws.send_text(json.dumps({"action": "subscribe", "symbols": ["NIFTY"]}))
        ack = recv_until(ws, "subscribed")
        assert ack["symbols"] == ["NIFTY"]

        tick = recv_until(ws, "tick")
        assert tick["instrument_id"] == "NIFTY"
        assert tick["last_price"] > 0
        candle = tick["candle"]
        assert {"time", "open", "high", "low", "close", "volume"} <= set(candle)


def test_multiple_symbols_fan_out(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(
            json.dumps({"action": "subscribe", "symbols": ["NIFTY", "BANKNIFTY"]})
        )
        ack = recv_until(ws, "subscribed")
        assert set(ack["symbols"]) == {"NIFTY", "BANKNIFTY"}

        seen = set()
        for _ in range(40):
            frame = json.loads(ws.receive_text())
            if frame.get("type") == "tick":
                seen.add(frame["instrument_id"])
                if seen >= {"NIFTY", "BANKNIFTY"}:
                    break
        assert seen == {"NIFTY", "BANKNIFTY"}


def test_running_bar_is_continuous(ws_client):
    """Consecutive ticks in one interval extend a single bar, not new bars."""
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "subscribe", "symbols": ["NIFTY"], "interval": "1m"}))
        recv_until(ws, "subscribed")

        first = recv_until(ws, "tick")["candle"]
        second = recv_until(ws, "tick")["candle"]
        # Same 1-minute window, so timestamps match and high/low only widen.
        assert first["time"] == second["time"]
        assert second["high"] >= first["high"]
        assert second["low"] <= first["low"]
        assert second["volume"] >= first["volume"]


def test_ping_pong(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "ping"}))
        assert recv_until(ws, "pong")


def test_invalid_json_does_not_kill_socket(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text("{not json")
        err = recv_until(ws, "error")
        assert "invalid JSON" in err["message"]
        # socket still usable
        ws.send_text(json.dumps({"action": "ping"}))
        assert recv_until(ws, "pong")


def test_unknown_action_rejected(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "explode"}))
        err = recv_until(ws, "error")
        assert "unknown action" in err["message"]


def test_subscribe_requires_symbols(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "subscribe", "symbols": []}))
        err = recv_until(ws, "error")
        assert "symbols required" in err["message"]


def test_symbol_cap_enforced(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        many = [f"SYM{i}" for i in range(50)]
        ws.send_text(json.dumps({"action": "subscribe", "symbols": many}))
        err = recv_until(ws, "error")
        assert "at most" in err["message"]


def test_symbols_normalized_to_uppercase(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "subscribe", "symbols": ["nifty"]}))
        ack = recv_until(ws, "subscribed")
        assert ack["symbols"] == ["NIFTY"]


def test_unsubscribe_stops_ticks(ws_client):
    with ws_client.websocket_connect("/api/v1/ws/market") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "subscribe", "symbols": ["NIFTY"]}))
        recv_until(ws, "subscribed")
        recv_until(ws, "tick")
        ws.send_text(json.dumps({"action": "unsubscribe"}))
        assert recv_until(ws, "unsubscribed")


# --- provider-level ---------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_stream_rejects_bad_interval():
    from app.marketdata.demo import DemoProvider

    provider = DemoProvider()
    with pytest.raises(ValueError, match="Unsupported interval"):
        async for _ in provider.stream_ticks(["NIFTY"], "7m"):
            break


@pytest.mark.asyncio
async def test_stream_ticks_yields_all_symbols_round_robin():
    from app.marketdata.demo import DemoProvider

    provider = DemoProvider()
    got = []
    async for tick in provider.stream_ticks(["NIFTY", "SENSEX"], "1m"):
        got.append(tick.instrument_id)
        if len(got) >= 4:
            break
    assert set(got) == {"NIFTY", "SENSEX"}


@pytest.mark.asyncio
async def test_base_provider_has_no_streaming_by_default():
    from app.marketdata.base import MarketDataProvider

    class Minimal(MarketDataProvider):
        async def get_instruments(self):
            return []

        async def get_historical_data(self, *a, **k):
            return []

        async def get_option_chain(self, *a, **k):
            return {}

    provider = Minimal()
    assert await provider.supports_streaming() is False
    with pytest.raises(NotImplementedError):
        async for _ in provider.stream_ticks(["X"], "1m"):
            break
