"""Shared REST broker helper.

Most Indian brokers expose a similar REST surface (JSON, bearer/OAuth auth,
standard error envelope). :class:`BaseRestBroker` factors out the HTTP plumbing
and error mapping so concrete adapters (Zerodha, Upstox, Angel, ...) only
implement the mapping between broker-specific payloads and our unified types.
"""


import httpx

from app.execution.gateway import (
    AuthenticationError,
    BrokerError,
    BrokerGateway,
    InsufficientMarginError,
    OrderRejectedError,
    RateLimitError,
)


class BaseRestBroker(BrokerGateway):
    """Base class for JSON REST brokers."""

    base_url: str = ""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = httpx.AsyncClient(timeout=15.0)

    # -- subclasses override -------------------------------------------------

    def auth_headers(self) -> dict:
        raise NotImplementedError("Subclasses must implement auth_headers()")

    # -- HTTP plumbing -------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        h = {**self.auth_headers(), **(headers or {})}
        resp = await self._client.request(
            method, f"{self.base_url}{path}", params=params, data=data, json=json, headers=h
        )
        return self._handle(resp)

    def _handle(self, resp: httpx.Response) -> dict:
        if resp.status_code in (401, 403):
            raise AuthenticationError("AUTH", "Authentication failed / token expired", self.name)
        if resp.status_code == 429:
            raise RateLimitError("RATE", "Rate limit exceeded", self.name)
        try:
            body = resp.json()
        except Exception as exc:
            raise BrokerError("PARSE", f"Non-JSON response: {resp.text[:200]}", self.name) from exc

        # Many brokers wrap data in a "status"/"data" envelope; normalise.
        if isinstance(body, dict) and body.get("status") == "error":
            msg = body.get("message", "Broker error")
            code = str(body.get("errorCode") or body.get("code") or "ERR")
            if "MARGIN" in code.upper() or "INSUFFICIENT" in msg.upper():
                raise InsufficientMarginError(code, msg, self.name)
            raise OrderRejectedError(code, msg, self.name)
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    async def disconnect(self) -> bool:
        await self._client.aclose()
        self._connected = False
        return True
