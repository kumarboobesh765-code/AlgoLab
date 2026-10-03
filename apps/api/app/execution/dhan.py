"""Dhan (DhanHQ v2) broker adapter.

Best-effort :class:`BrokerGateway` implementation over the DhanHQ REST API
(https://api.dhan.co). Auth uses the ``access_token`` header.
"""

from datetime import datetime

import httpx

from app.execution.base_rest import BaseRestBroker
from app.execution.gateway import (
    AuthenticationError,
    BrokerError,
    Exchange,
    Funds,
    Holding,
    Instrument,
    InsufficientMarginError,
    Margin,
    Order,
    OrderRejectedError,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Segment,
    Trade,
)

_DHAN_BASE = "https://api.dhan.co"

_EXCHANGE_MAP = {"NSE": Exchange.NSE, "BSE": Exchange.BSE, "NFO": Exchange.NFO, "BFO": Exchange.BFO, "MCX": Exchange.MCX, "CDS": Exchange.NCDEX}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {"CNC": ProductType.CNC, "INTRADAY": ProductType.MIS, "MARGIN": ProductType.MIS, "NRML": ProductType.NRML}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT, "STOP_LOSS": OrderType.SL, "STOP_LOSS_MARKET": OrderType.SL_M}
_ORDER_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {"PENDING": OrderStatus.PENDING, "EXECUTED": OrderStatus.COMPLETE, "PARTIALLY_FILLED": OrderStatus.PARTIAL, "CANCELLED": OrderStatus.CANCELLED, "REJECTED": OrderStatus.REJECTED, "EXPIRED": OrderStatus.EXPIRED, "OPEN": OrderStatus.OPEN}


class DhanGateway(BaseRestBroker):
    name = "dhan"
    is_demo = False
    base_url = _DHAN_BASE

    def __init__(self, config: dict):
        super().__init__(config)
        self.access_token = config.get("access_token", "")
        self.client_id = config.get("client_id", "")

    def auth_headers(self) -> dict:
        return {"access-token": self.access_token, "Content-Type": "application/json", "Accept": "application/json"}

    def _handle(self, resp: httpx.Response) -> dict:
        """Parse a Dhan response, which signals errors in the body, not the status.

        Two Dhan-specific cases the shared parser misses:

        - Dhan returns HTTP 200 with {"errorType", "errorMessage"} for a rejected
          request, expired token included. The shared parser only understands
          HTTP status codes and a `status: "error"` envelope, so the error object
          flowed into the response parsers as if it were data: an unauthenticated
          account reported zero available margin rather than an auth failure.
        - A wrong path answers with a Spring {"status": 404, "error": ...} body
          and a real 404 status. `_handle` looks for the string "error" there, not
          the integer, so a mistyped endpoint returned an empty payload silently.
        """
        if resp.status_code >= 400 and "application/json" not in resp.headers.get(
            "content-type", ""
        ):
            raise BrokerError(
                f"HTTP_{resp.status_code}", f"Non-JSON response: {resp.text[:200]}", self.name
            )
        body = super()._handle(resp)
        if not isinstance(body, dict):
            return body
        # Spring error envelope for an unrouted path.
        if isinstance(body.get("status"), int) and body.get("status") >= 400:
            raise BrokerError(
                f"HTTP_{body['status']}",
                str(body.get("error") or body.get("message") or "Broker error"),
                self.name,
            )
        if "errorType" in body or "errorMessage" in body:
            code = str(body.get("errorCode") or body.get("errorType") or "DHAN_ERROR")
            msg = str(body.get("errorMessage") or "Broker error")
            upper = f"{code} {msg}".upper()
            if "AUTH" in upper or "TOKEN" in upper or "INVALID_ACCESS" in upper:
                raise AuthenticationError(code, msg, self.name)
            if "MARGIN" in upper:
                raise InsufficientMarginError(code, msg, self.name)
            raise OrderRejectedError(code, msg, self.name)
        return body

    async def connect(self) -> bool:
        try:
            await self.get_profile()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    async def is_connected(self) -> bool:
        return self._connected

    async def get_profile(self) -> dict:
        return await self._request("GET", "/v2/profile")

    async def get_funds(self) -> Funds:
        # Dhan exposes limits at /v2/fundlimit. /v2/funds does not exist and
        # answers 404, which used to be parsed as an empty payload and surfaced
        # as zero available margin instead of an error.
        data = await self._request("GET", "/v2/fundlimit")
        eq = data.get("equity", {})
        return Funds(
            equity=float(eq.get("availableMargin", 0)),
            commodity=float(data.get("commodity", {}).get("availableMargin", 0)),
            used_margin=float(eq.get("utilisedMargin", 0)),
            available_cash=float(eq.get("availableMargin", 0)),
        )

    async def get_margin(self) -> Margin:
        data = await self._request("GET", "/v2/fundlimit")
        return Margin(equity=data.get("equity", {}), commodity=data.get("commodity", {}))

    async def get_positions(self) -> list[Position]:
        data = await self._request("GET", "/v2/positions")
        out = []
        for p in data.get("positions", []):
            qty = int(float(p.get("net_qty", 0)))
            side = OrderSide.BUY if qty >= 0 else OrderSide.SELL
            out.append(Position(
                symbol=p.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(p.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if p.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                product=_PRODUCT_MAP.get(p.get("product_type", "INTRADAY"), ProductType.MIS),
                side=side,
                quantity=abs(qty),
                average_price=float(p.get("average_price", 0)),
                last_price=float(p.get("last_price", 0)),
                unrealized_pnl=float(p.get("pnl", 0)) * (1 if side == OrderSide.BUY else -1),
                realized_pnl=0.0,
                value=abs(qty) * float(p.get("last_price", 0)),
            ))
        return out

    async def get_holdings(self) -> list[Holding]:
        data = await self._request("GET", "/v2/holdings")
        out = []
        for h in data.get("holdings", []):
            qty = int(float(h.get("quantity", 0)))
            avg = float(h.get("average_price", 0))
            ltp = float(h.get("last_price", 0))
            out.append(Holding(
                symbol=h.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(h.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY,
                quantity=qty,
                average_price=avg,
                last_price=ltp,
                pnl=(ltp - avg) * qty,
                value=ltp * qty,
                isin=h.get("isin"),
            ))
        return out

    async def get_orders(self) -> list[Order]:
        data = await self._request("GET", "/v2/orders")
        return [self._map_order(o) for o in data.get("data", []) or []]

    def _map_order(self, o: dict) -> Order:
        status = _STATUS_MAP.get((o.get("order_status") or "").upper(), OrderStatus.OPEN)
        filled = int(float(o.get("filled_qty", 0) or 0))
        qty = int(float(o.get("qty", 0)))
        return Order(
            order_id=str(o.get("order_id", "")),
            broker_order_id=str(o.get("order_id", "")),
            symbol=o.get("tradingsymbol", ""),
            exchange=_EXCHANGE_MAP.get(o.get("exchange", ""), Exchange.NSE),
            segment=Segment.EQUITY if o.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
            side=OrderSide.BUY if o.get("transaction_type") == "BUY" else OrderSide.SELL,
            order_type=_ORDER_TYPE_MAP.get(o.get("order_type", "MARKET"), OrderType.MARKET),
            product=_PRODUCT_MAP.get(o.get("product_type", "INTRADAY"), ProductType.MIS),
            quantity=qty,
            price=float(o.get("price", 0)),
            trigger_price=float(o.get("trigger_price", 0)),
            filled_quantity=filled,
            pending_quantity=qty - filled,
            status=status,
            average_price=float(o.get("average_price", 0)),
            timestamp=datetime.now(),
            update_time=datetime.now(),
            tag=o.get("tag"),
            rejection_reason=o.get("error_message"),
        )

    async def get_order_history(self, order_id: str) -> list[Order]:
        data = await self._request("GET", "/v2/orders")
        return [self._map_order(o) for o in data.get("data", []) or [] if str(o.get("order_id", "")) == order_id]

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        data = await self._request("GET", "/v2/trades")
        out = []
        for t in data.get("data", []) or []:
            out.append(Trade(
                trade_id=str(t.get("trade_id", "")),
                order_id=str(t.get("order_id", "")),
                symbol=t.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(t.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if t.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                side=OrderSide.BUY if t.get("transaction_type") == "BUY" else OrderSide.SELL,
                quantity=int(float(t.get("qty", 0))),
                price=float(t.get("price", 0)),
                timestamp=datetime.now(),
                trade_value=int(float(t.get("qty", 0))) * float(t.get("price", 0)),
            ))
        return out

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        errors = self._validate_order_request(request)
        if errors:
            from app.execution.gateway import OrderRejectedError
            raise OrderRejectedError("VALIDATION", "; ".join(errors), self.name)
        body = {
            "transaction_type": request.side.value,
            "exchange": _EXCHANGE_INV.get(request.exchange, "NSE"),
            "symbol": request.symbol,
            "quantity": request.quantity,
            "product_type": _PRODUCT_INV.get(request.product, "INTRADAY"),
            "order_type": _ORDER_INV.get(request.order_type, "MARKET"),
            "validity": request.validity.value,
            "price": request.price,
            "trigger_price": request.trigger_price,
            "tag": request.tag or "strategylab",
        }
        data = await self._request("POST", "/v2/orders", json=body)
        return OrderResponse(
            order_id=str(data.get("order_id", "")),
            broker_order_id=str(data.get("order_id", "")),
            status=OrderStatus.PENDING,
            message="Order placed via Dhan",
        )

    async def modify_order(self, order_id: str, quantity=None, price=None,
                           trigger_price=None, order_type=None) -> OrderResponse:
        body = {"order_id": order_id}
        if price is not None:
            body["price"] = price
        if trigger_price is not None:
            body["trigger_price"] = trigger_price
        if order_type is not None:
            body["order_type"] = _ORDER_INV.get(order_type, "LIMIT")
        data = await self._request("PUT", f"/v2/orders/{order_id}", json=body)
        return OrderResponse(order_id=str(order_id), broker_order_id=str(data.get("order_id", order_id)), status=OrderStatus.PENDING, message="Order modified")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        data = await self._request("DELETE", f"/v2/orders/{order_id}")
        return OrderResponse(order_id=str(order_id), broker_order_id=str(data.get("order_id", order_id)), status=OrderStatus.CANCELLED, message="Order cancelled")

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        return []

    async def search_instruments(self, query: str, exchange=None) -> list[Instrument]:
        return []

    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        symbols = [f"{_EXCHANGE_INV.get(i.exchange, 'NSE')}:{i.symbol}" for i in instruments]
        data = await self._request("POST", "/v2/quotes", json={"symbols": ",".join(symbols)})
        out = {}
        for inst in instruments:
            q = data.get("data", {}).get(f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}", {})
            out[inst.symbol] = {"last_price": float(q.get("last_price", 0)), "bid": 0.0, "ask": 0.0, "volume": int(q.get("volume", 0)), "oi": int(q.get("oi", 0)), "change": 0.0, "change_pct": 0.0}
        return out

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        return {i.symbol: {} for i in instruments}

    async def get_historical_data(self, instrument: Instrument, interval: str, from_date: datetime, to_date: datetime) -> list[dict]:
        return []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        raise NotImplementedError("Use the market-data provider for option chains")
