"""OAuth 2.0 login-flow helpers for Indian broker APIs.

SEBI's retail-algo framework bans credential-sharing auth; third-party access
must use OAuth. This module builds per-broker authorization URLs and performs
the code->token exchange. Token exchange is LIVE-VERIFY: unit tests mock the
HTTP layer, real calls need broker credentials.

Supported flows (session/token based):
- Zerodha Kite: request_token -> access_token (POST /session/token)
- Fyers: auth_code -> access_token (POST /api/v3/validate-authcode)
- Upstox: code -> access_token (POST /login/authorization/token, v2)
"""

from dataclasses import dataclass

import httpx

from app.execution.gateway import AuthenticationError


@dataclass(frozen=True)
class OAuthSpec:
    broker: str
    auth_url: str
    token_url: str
    token_uses_basic_auth: bool = False  # Zerodha uses checksum instead


SPECS: dict[str, OAuthSpec] = {
    "zerodha": OAuthSpec(
        broker="zerodha",
        auth_url="https://kite.zerodha.com/connect/login",
        token_url="https://api.kite.trade/session/token",
        token_uses_basic_auth=True,
    ),
    "fyers": OAuthSpec(
        broker="fyers",
        auth_url="https://api-t1.fyers.in/api/v3/generate-authtoken",
        token_url="https://api-t1.fyers.in/api/v3/validate-authcode",
    ),
    "upstox": OAuthSpec(
        broker="upstox",
        auth_url="https://api.upstox.com/v2/login/authorization/dialog",
        token_url="https://api.upstox.com/v2/login/authorization/token",
    ),
}


def list_oauth_brokers() -> list[str]:
    return sorted(SPECS)


def build_auth_url(broker: str, api_key: str, redirect_uri: str, state: str = "") -> str:
    """Authorization URL the user opens in a browser to consent."""
    spec = SPECS.get(broker)
    if spec is None:
        raise AuthenticationError("OAUTH_UNSUPPORTED", f"No OAuth flow for '{broker}'", broker)
    from urllib.parse import urlencode

    params = {"api_key": api_key, "redirect_uri": redirect_uri}
    if broker == "upstox":
        params = {"client_id": api_key, "redirect_uri": redirect_uri, "response_type": "code"}
    if state:
        params["state"] = state
    return f"{spec.auth_url}?{urlencode(params)}"


async def exchange_token(
    broker: str,
    code: str,
    api_key: str,
    api_secret: str,
    redirect_uri: str = "",
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Exchange the OAuth/request code for an access token.

    Returns a normalized {"access_token", "user_id", "broker"} dict.
    Raises AuthenticationError on rejection. LIVE-VERIFY against real brokers.
    """
    spec = SPECS.get(broker)
    if spec is None:
        raise AuthenticationError("OAUTH_UNSUPPORTED", f"No OAuth flow for '{broker}'", broker)

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=30)

    try:
        if broker == "zerodha":
            import hashlib
            checksum = hashlib.sha256(f"{api_key}{code}{api_secret}".encode()).hexdigest()
            resp = await http.post(
                spec.token_url,
                data={"api_key": api_key, "request_token": code, "checksum": checksum},
                headers={"X-Kite-Version": "3"},
            )
            payload = _unwrap(resp, broker, ["data"])
            return {
                "access_token": payload.get("access_token", ""),
                "user_id": payload.get("user_id", ""),
                "broker": broker,
            }

        if broker == "fyers":
            resp = await http.post(
                spec.token_url,
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": api_key,
                    "code": code,
                },
            )
            payload = _unwrap(resp, broker)
            return {
                "access_token": payload.get("access_token", ""),
                "user_id": "",
                "broker": broker,
            }

        # upstox
        resp = await http.post(
            spec.token_url,
            data={
                "code": code,
                "client_id": api_key,
                "client_secret": api_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = _unwrap(resp, broker)
        return {
            "access_token": payload.get("access_token", ""),
            "user_id": payload.get("user_id", ""),
            "broker": broker,
        }
    finally:
        if own_client:
            await http.aclose()


def _unwrap(resp: httpx.Response, broker: str, wrapper: list[str] | None = None) -> dict:
    if resp.status_code >= 400:
        raise AuthenticationError("TOKEN_EXCHANGE_FAILED", f"HTTP {resp.status_code}: {resp.text[:200]}", broker)
    data = resp.json()
    if wrapper:
        for key in wrapper:
            if isinstance(data, dict) and key in data:
                data = data[key]
    return data if isinstance(data, dict) else {}
