"""Tests for OAuth flow helpers (mock HTTP — no real broker calls)."""

import httpx
import pytest

from app.execution.gateway import AuthenticationError
from app.execution.oauth import build_auth_url, exchange_token, list_oauth_brokers


def test_lists_supported_brokers():
    assert set(list_oauth_brokers()) >= {"zerodha", "fyers", "upstox"}


def test_builds_zerodha_login_url():
    url = build_auth_url("zerodha", "apikey123", "https://app/callback", state="xyz")
    assert url.startswith("https://kite.zerodha.com/connect/login?")
    assert "api_key=apikey123" in url
    assert "state=xyz" in url


def test_upstox_uses_client_id_param():
    url = build_auth_url("upstox", "cid.abc", "https://app/cb")
    assert "client_id=cid.abc" in url
    assert "response_type=code" in url


def test_unknown_broker_rejected():
    with pytest.raises(AuthenticationError):
        build_auth_url("unknownbroker", "k", "u")


@pytest.mark.asyncio
async def test_zerodha_token_exchange():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.kite.trade"
        body = request.content.decode()
        assert "request_token=CODE" in body and "checksum=" in body
        return httpx.Response(200, json={"status": "success", "data": {"access_token": "TOK", "user_id": "AB1234"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await exchange_token("zerodha", "CODE", "key", "secret", client=client)
    assert out == {"access_token": "TOK", "user_id": "AB1234", "broker": "zerodha"}


@pytest.mark.asyncio
async def test_upstox_token_exchange():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.upstox.com"
        return httpx.Response(200, json={"access_token": "UTOK", "user_id": "U1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await exchange_token("upstox", "C", "id", "sec", "https://app/cb", client=client)
    assert out["access_token"] == "UTOK"


@pytest.mark.asyncio
async def test_exchange_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "bad checksum"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthenticationError):
            await exchange_token("zerodha", "BAD", "k", "s", client=client)
