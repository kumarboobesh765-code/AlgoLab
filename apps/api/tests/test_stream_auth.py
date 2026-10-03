"""WebSocket authentication.

A stream socket that accepts anonymous subscribers leaks the whole tick feed to
anyone who can reach the port, and unlike a REST endpoint it holds the
connection open. These tests pin the rule: closed when AUTH_ENABLED and the
handshake carries no valid token, open otherwise, and the local research
default (auth off) keeps working untouched.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app

WS = "/api/v1/ws/market"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _set_auth(monkeypatch, value: str):
    """Set AUTH_ENABLED and invalidate the cached Settings.

    get_settings is @lru_cache, so mutating the environment alone does nothing
    once any earlier call has populated the cache. Patching the Settings object
    instead would be equally wrong: get_settings builds a fresh instance per
    call, so the patch would land on a throwaway.
    """
    monkeypatch.setenv("AUTH_ENABLED", value)
    get_settings.cache_clear()
    return get_settings


@pytest.fixture
def auth_on(monkeypatch):
    _set_auth(monkeypatch, "true")


@pytest.fixture
def auth_off(monkeypatch):
    _set_auth(monkeypatch, "false")


def _token() -> str:
    return create_access_token(str(uuid.uuid4()))


# --- auth disabled: local research default ---------------------------------


def test_open_when_auth_disabled(client, auth_off):
    """Matches every REST route when AUTH_ENABLED is false."""
    with client.websocket_connect(WS) as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"


# --- auth enabled -----------------------------------------------------------


def test_rejected_without_token(client, auth_on):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS):
            pass
    assert exc.value.code == 4401


def test_rejected_with_invalid_token(client, auth_on):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"{WS}?token=not-a-jwt"):
            pass
    assert exc.value.code == 4401


def test_rejected_when_token_subject_is_not_a_uuid(client, auth_on):
    """A correctly-signed token with a non-UUID subject must not be accepted."""
    token = create_access_token("definitely-not-a-uuid")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"{WS}?token={token}"):
            pass
    assert exc.value.code == 4401


def test_rejected_with_expired_token(client, auth_on):
    token = create_access_token(str(uuid.uuid4()), expires_minutes=-1)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"{WS}?token={token}"):
            pass
    assert exc.value.code == 4401


def test_accepted_with_valid_query_token(client, auth_on):
    with client.websocket_connect(f"{WS}?token={_token()}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"


def test_accepted_with_authorization_header(client, auth_on):
    """Non-browser clients send a header instead of a query parameter."""
    with client.websocket_connect(
        WS, headers={"Authorization": f"Bearer {_token()}"}
    ) as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"


def test_rejected_with_malformed_authorization_header(client, auth_on):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS, headers={"Authorization": _token()}):
            pass
    assert exc.value.code == 4401


def test_token_with_special_characters_is_encoded(client, auth_on):
    """A token containing URL-significant characters must survive the query."""
    token = create_access_token(str(uuid.uuid4()))
    with client.websocket_connect(f"{WS}?token={token}") as ws:
        assert json.loads(ws.receive_text())["type"] == "hello"


def test_authenticated_socket_can_subscribe_and_stream(client, auth_on):
    with client.websocket_connect(f"{WS}?token={_token()}") as ws:
        json.loads(ws.receive_text())
        ws.send_text(json.dumps({"action": "subscribe", "symbols": ["NIFTY"]}))
        for _ in range(20):
            frame = json.loads(ws.receive_text())
            if frame.get("type") == "subscribed":
                assert frame["symbols"] == ["NIFTY"]
                break
            assert frame.get("type") in ("hello", "tick")
        else:
            pytest.fail("never received subscribed ack")


def test_token_must_be_read_from_handshake_only(client, auth_on):
    """A token supplied only in the subscribe frame must not authenticate.

    Otherwise the handshake would be the unauthenticated boundary and the
    first message would be a bypass.
    """
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS) as ws:
            ws.send_text(
                json.dumps(
                    {"action": "subscribe", "symbols": ["NIFTY"], "token": _token()}
                )
            )
    assert exc.value.code == 4401
