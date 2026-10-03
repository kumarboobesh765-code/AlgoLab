"""Dhan adapter: error handling against the real API's conventions.

These are regression tests for two bugs found by probing the live Dhan endpoint
without credentials:

- Dhan returns HTTP 200 with {"errorType", "errorMessage"} for a rejected
  request. The shared REST parser only understands HTTP status codes and a
  `status: "error"` envelope, so that object reached the response parsers as
  data and an unauthenticated account reported zero available margin instead of
  an auth failure.
- `/v2/funds` does not exist on Dhan; it answers 404 with a Spring error body.
  Funds limits live at `/v2/fundlimit`.

Responses here are the byte-for-byte shapes Dhan actually returned, not invented
ones.
"""

import httpx
import pytest

from app.execution.dhan import DhanGateway
from app.execution.gateway import (
    AuthenticationError,
    BrokerError,
    InsufficientMarginError,
    OrderRejectedError,
)

# Captured from https://api.dhan.co with an invalid token.
REAL_INVALID_TOKEN = {
    "errorType": "Invalid_Authentication",
    "errorCode": "DH-901",
    "errorMessage": "Client ID or user generated access token is invalid",
}
# Captured from a wrong path.
REAL_SPRING_404 = {
    "timestamp": 1791028576765,
    "status": 404,
    "error": "Not Found",
    "path": "/v2/funds",
}


def response(body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=__import__("json").dumps(body).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://api.dhan.co/v2/profile"),
    )


@pytest.fixture
def gateway() -> DhanGateway:
    return DhanGateway({"client_id": "test", "access_token": "invalid"})


# --- error translation ------------------------------------------------------


def test_invalid_auth_body_raises_authentication(gateway):
    """The bug: this used to be returned as a payload."""
    with pytest.raises(AuthenticationError) as exc:
        gateway._handle(response(REAL_INVALID_TOKEN))
    assert "DH-901" in str(exc.value)
    assert exc.value.broker == "dhan"


def test_http_200_error_is_not_silently_accepted(gateway):
    assert gateway._handle.__doc__ and "HTTP 200" in gateway._handle.__doc__


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        ("Invalid_Authentication", "Client ID or token is invalid", AuthenticationError),
        ("Token_Expired", "Access token expired", AuthenticationError),
        ("Invalid_access_token", "bad token", AuthenticationError),
        ("Insufficient_Margin", "Not enough margin available", InsufficientMarginError),
        ("Invalid_Quantity", "quantity must be greater than zero", OrderRejectedError),
    ],
)
def test_error_types_are_classified(gateway, code, message, expected):
    with pytest.raises(expected):
        gateway._handle(response({"errorType": code, "errorMessage": message}))


def test_spring_error_body_raises(gateway):
    """A wrong endpoint returned an empty payload instead of an error."""
    with pytest.raises(BrokerError) as exc:
        gateway._handle(response(REAL_SPRING_404, status=404))
    assert "404" in str(exc.value)


def test_non_json_response_raises(gateway):
    resp = httpx.Response(
        502,
        content=b"<html>Bad Gateway</html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", "https://api.dhan.co/v2/profile"),
    )
    with pytest.raises(BrokerError):
        gateway._handle(resp)


# --- valid payloads still parse --------------------------------------------


def test_valid_profile_passes_through(gateway):
    body = {"dhanClientId": "1100000001", "ssoId": "abc", "clientName": "Test"}
    assert gateway._handle(response(body)) == body


def test_valid_fundlimit_passes_through(gateway):
    body = {"equity": {"availableMargin": 50000.0, "utilisedMargin": 1000.0}}
    assert gateway._handle(response(body)) == body


def test_list_payload_passes_through(gateway):
    assert gateway._handle(response([{"a": 1}])) == [{"a": 1}]


def test_data_envelope_still_unwrapped(gateway):
    """The shared parser's normalisation must keep working."""
    assert gateway._handle(response({"data": [1, 2]})) == [1, 2]


# --- endpoint correctness ---------------------------------------------------


@pytest.mark.asyncio
async def test_funds_uses_fundlimit_not_funds(gateway, monkeypatch):
    """/v2/funds 404s on the real API; funds must read /v2/fundlimit."""
    seen: list[str] = []

    async def fake_request(method, path, **kwargs):
        seen.append(path)
        return {"equity": {"availableMargin": 12345.0, "utilisedMargin": 555.0}}

    monkeypatch.setattr(gateway, "_request", fake_request)
    funds = await gateway.get_funds()
    assert seen == ["/v2/fundlimit"]
    assert funds.equity == 12345.0
    assert funds.used_margin == 555.0


@pytest.mark.asyncio
async def test_margin_uses_fundlimit(gateway, monkeypatch):
    seen: list[str] = []

    async def fake_request(method, path, **kwargs):
        seen.append(path)
        return {"equity": {"availableMargin": 1.0}, "commodity": {"availableMargin": 2.0}}

    monkeypatch.setattr(gateway, "_request", fake_request)
    await gateway.get_margin()
    assert seen == ["/v2/fundlimit"]


@pytest.mark.asyncio
async def test_no_method_calls_the_nonexistent_funds_path(gateway, monkeypatch):
    """Guard against a future edit reintroducing /v2/funds."""
    seen: list[str] = []

    async def fake_request(method, path, **kwargs):
        seen.append(path)
        return {}

    monkeypatch.setattr(gateway, "_request", fake_request)
    for call in (
        gateway.get_funds(),
        gateway.get_margin(),
        gateway.get_profile(),
        gateway.get_positions(),
        gateway.get_holdings(),
        gateway.get_orders(),
    ):
        await call
    assert "/v2/funds" not in seen


# --- behaviour without credentials -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    ["get_profile", "get_funds", "get_margin", "get_positions", "get_holdings", "get_orders"],
)
async def test_unauthenticated_calls_raise_rather_than_return_zeros(gateway, method):
    """Reporting zero margin for an expired token is worse than an error."""
    with pytest.raises(AuthenticationError):
        await getattr(gateway, method)()


@pytest.mark.asyncio
async def test_connect_returns_false_when_unauthenticated(gateway):
    assert await gateway.connect() is False
    assert await gateway.is_connected() is False


def test_gateway_identity(gateway):
    assert gateway.name == "dhan"
    # Live broker: never flagged as demo data.
    assert getattr(gateway, "is_demo", False) is False
