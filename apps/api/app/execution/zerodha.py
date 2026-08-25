"""Zerodha (Kite Connect v3) broker adapter.

Implements the :class:`BrokerGateway` interface using the public Kite Connect
REST API (https://api.kite.trade). WebSocket streaming and bracket/cover orders
are noted where not uniformly supported; everything else maps 1:1.

Authentication: the adapter expects an ``access_token`` in config (obtained
out-of-band via the Kite login flow). ``connect()`` validates the token.
"""

from datetime import datetime

import httpx

from app.execution.gateway import (
    AuthenticationError,
    BrokerError,
    BrokerGateway,
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
    RateLimitError,
    Segment,
    Trade,
)

_KITE_BASE = "https://api.kite.trade"

_EXCHANGE_MAP = {
    "NSE": Exchange.NSE,
    "BSE": Exchange.BSE,
    "NFO": Exchange.NFO,
    "BFO": Exchange.BFO,
    "MCX": Exchange.MCX,
    "CDS": Exchange.NCDEX,
}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {
    "CNC": ProductType.CNC,
    "MIS": ProductType.MIS,
    "NRML": ProductType.NRML,
}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {
    "MARKET": OrderType.MARKET,
    "LIMIT": OrderType.LIMIT,
    "SL": OrderType.SL,
    "SL-M": OrderType.SL_M,
}
_ORDER_TYPE_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {
    "OPEN": OrderStatus.OPEN,
    "PENDING": OrderStatus.PENDING,
    "COMPLETE": OrderStatus.COMPLETE,
    "PARTIAL": OrderStatus.PARTIAL,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.EXPIRED,
}


class ZerodhaGateway(BrokerGateway):
    name = "zerodha"
    is_demo = False
    supports_websocket = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.access_token = config.get("access_token", "")
        self._client = httpx.AsyncClient(timeout=15.0)

    def _headers(self) -> dict:
        return {"Authorization": f"token {self.api_key}:{self.access_token}", "X-Kite-Version": "3"}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._client.get(f"{_KITE_BASE}{path}", params=params, headers=self._headers())
        return self._handle(resp)

    async def _post(self, path: str, data: dict) -> dict:
        resp = await self._client.post(f"{_KITE_BASE}{path}", data=data, headers=self._headers())
        return self._handle(resp)

    async def _put(self, path: str, data: dict) -> dict:
        resp = await self._client.put(f"{_KITE_BASE}{path}", data=data, headers=self._headers())
        return self._handle(resp)

    async def _delete(self, path: str, data: dict) -> dict:
        resp = await self._client.delete(f"{_KITE_BASE}{path}", data=data, headers=self._headers())
        return self._handle(resp)

    def _handle(self, resp: httpx.Response) -> dict:
        if resp.status_code == 403 or resp.status_code == 401:
            raise AuthenticationError("AUTH", "Invalid/expired Kite access token", self.name)
        if resp.status_code == 429:
            raise RateLimitError("RATE", "Kite rate limit exceeded", self.name)
        try:
            body = resp.json()
        except Exception as exc:
            raise BrokerError("PARSE", f"Non-JSON response: {resp.text}", self.name) from exc
        if not body.get("status") == "success":
            msg = body.get("message", "Kite error")
            code = str(body.get("code", "ERR"))
            if code in ("NO_MARGIN", "INSUFFICIENT_MARGIN"):
                raise InsufficientMarginError(code, msg, self.name)
            if code in ("ORDER_REJECTED", "VALIDATION_ERROR"):
                raise OrderRejectedError(code, msg, self.name)
            raise BrokerError(code, msg, self.name)
        return body["data"]

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> bool:
        try:
            await self.get_profile()
            self._connected = True
            return True
        except AuthenticationError:
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        await self._client.aclose()
        self._connected = False
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def get_profile(self) -> dict:
        return await self._get("/user/profile")

    async def get_funds(self) -> Funds:
        data = await self._get("/user/margins")
        eq = data.get("equity", {})
        return Funds(
            equity=float(eq.get("net", 0)),
            commodity=float(data.get("commodity", {}).get("net", 0)),
            used_margin=float(eq.get("utilised", {}).get("total", 0)),
            available_cash=float(eq.get("available", {}).get("cash", 0)),
            collateral=float(eq.get("available", {}).get("collateral", 0)),
        )

    async def get_margin(self) -> Margin:
        data = await self._get("/user/margins")
        return Margin(equity=data.get("equity", {}), commodity=data.get("commodity", {}))

    async def get_positions(self) -> list[Position]:
        data = await self._get("/portfolio/positions")
        out = []
        for p in data.get("net", []):
            out.append(self._map_position(p))
        return out

    def _map_position(self, p: dict) -> Position:
        side = OrderSide.BUY if p.get("quantity", 0) >= 0 else OrderSide.SELL
        qty = abs(int(p.get("quantity", 0)))
        avg = float(p.get("average_price", 0))
        ltp = float(p.get("last_price", 0))
        pnl = float(p.get("pnl", 0))
        return Position(
            symbol=p.get("tradingsymbol", ""),
            exchange=_EXCHANGE_MAP.get(p.get("exchange", ""), Exchange.NSE),
            segment=Segment.EQUITY if p.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
            product=_PRODUCT_MAP.get(p.get("product", "MIS"), ProductType.MIS),
            side=side,
            quantity=qty,
            average_price=avg,
            last_price=ltp,
            unrealized_pnl=pnl if side == OrderSide.BUY else -pnl,
            realized_pnl=0.0,
            value=qty * ltp,
        )

    async def get_holdings(self) -> list[Holding]:
        data = await self._get("/portfolio/holdings")
        out = []
        for h in data.get("holdings", []):
            qty = int(h.get("quantity", 0))
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
        data = await self._get("/orders")
        return [self._map_order(o) for o in data]

    def _map_order(self, o: dict) -> Order:
        status = _STATUS_MAP.get(o.get("status", ""), OrderStatus.OPEN)
        filled = int(o.get("filled_quantity", 0))
        qty = int(o.get("quantity", 0))
        return Order(
            order_id=str(o.get("order_id", "")),
            broker_order_id=str(o.get("order_id", "")),
            symbol=o.get("tradingsymbol", ""),
            exchange=_EXCHANGE_MAP.get(o.get("exchange", ""), Exchange.NSE),
            segment=Segment.EQUITY if o.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
            side=OrderSide.BUY if o.get("transaction_type") == "BUY" else OrderSide.SELL,
            order_type=_ORDER_TYPE_MAP.get(o.get("order_type", "MARKET"), OrderType.MARKET),
            product=_PRODUCT_MAP.get(o.get("product", "MIS"), ProductType.MIS),
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
            rejection_reason=o.get("status_message"),
        )

    async def get_order_history(self, order_id: str) -> list[Order]:
        data = await self._get(f"/orders/{order_id}")
        return [self._map_order(o) for o in data]

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        data = await self._get("/trades")
        out = []
        for t in data:
            out.append(Trade(
                trade_id=str(t.get("trade_id", "")),
                order_id=str(t.get("order_id", "")),
                symbol=t.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(t.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if t.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                side=OrderSide.BUY if t.get("transaction_type") == "BUY" else OrderSide.SELL,
                quantity=int(t.get("quantity", 0)),
                price=float(t.get("average_price", 0)),
                timestamp=datetime.now(),
                trade_value=int(t.get("quantity", 0)) * float(t.get("average_price", 0)),
            ))
        return out

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        errors = self._validate_order_request(request)
        if errors:
            raise OrderRejectedError("VALIDATION", "; ".join(errors), self.name)
        variety = "amo" if request.is_amo else "regular"
        otype = _ORDER_TYPE_INV.get(request.order_type, "MARKET")
        data = {
            "tradingsymbol": request.symbol,
            "exchange": _EXCHANGE_INV.get(request.exchange, "NSE"),
            "transaction_type": request.side.value,
            "order_type": otype,
            "quantity": request.quantity,
            "product": _PRODUCT_INV.get(request.product, "MIS"),
            "validity": request.validity.value,
            "tag": request.tag or "strategylab",
        }
        if request.order_type in (OrderType.LIMIT, OrderType.SL):
            data["price"] = request.price
        if request.order_type in (OrderType.SL, OrderType.SL_M):
            data["trigger_price"] = request.trigger_price
        if request.disclosed_quantity:
            data["disclosed_quantity"] = request.disclosed_quantity
        resp = await self._post(f"/orders/{variety}/{otype}", data)
        return OrderResponse(
            order_id=str(resp.get("order_id", "")),
            broker_order_id=str(resp.get("order_id", "")),
            status=OrderStatus.PENDING,
            message="Order placed via Kite",
        )

    async def modify_order(self, order_id: str, quantity=None, price=None,
                           trigger_price=None, order_type=None) -> OrderResponse:
        variety = "regular"
        data = {}
        if quantity is not None:
            data["quantity"] = quantity
        if price is not None:
            data["price"] = price
        if trigger_price is not None:
            data["trigger_price"] = trigger_price
        if order_type is not None:
            data["order_type"] = _ORDER_TYPE_INV.get(order_type, "LIMIT")
        otype = _ORDER_TYPE_INV.get(order_type, "LIMIT") if order_type else "LIMIT"
        resp = await self._put(f"/orders/{variety}/{order_id}", data)
        return OrderResponse(
            order_id=str(order_id),
            broker_order_id=str(resp.get("order_id", order_id)),
            status=OrderStatus.PENDING,
            message="Order modified",
        )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        variety = "regular"
        resp = await self._delete(f"/orders/{variety}/{order_id}", {})
        return OrderResponse(
            order_id=str(order_id),
            broker_order_id=str(resp.get("order_id", order_id)),
            status=OrderStatus.CANCELLED,
            message="Order cancelled",
        )

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        params = {"exchange": _EXCHANGE_INV.get(exchange)} if exchange else None
        data = await self._get("/instruments", params)
        out = []
        for row in data or []:
            exch = _EXCHANGE_MAP.get(row.get("exchange", ""), Exchange.NSE)
            seg = Segment.OPTIONS if row.get("instrument_type") in ("CE", "PE") else (
                Segment.FUTURES if row.get("instrument_type") in ("FUT", "FUTIDX") else Segment.EQUITY)
            out.append(Instrument(
                symbol=row.get("tradingsymbol", ""),
                exchange=exch,
                segment=seg,
                security_id=str(row.get("instrument_token", "")),
                token=str(row.get("instrument_token", "")),
                name=row.get("name", ""),
                expiry=datetime.fromisoformat(row["expiry"]) if row.get("expiry") else None,
                strike=float(row["strike"]) if row.get("strike") else None,
                option_type=row.get("instrument_type") if row.get("instrument_type") in ("CE", "PE") else None,
                lot_size=int(row.get("lot_size", 1)),
                tick_size=float(row.get("tick_size", 0.05)),
            ))
        return out

    async def search_instruments(self, query: str, exchange=None) -> list[Instrument]:
        all_inst = await self.get_instruments(exchange)
        q = query.upper()
        return [i for i in all_inst if q in i.symbol.upper()]

    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        symbols = [f"{_EXCHANGE_INV.get(i.exchange, 'NSE')}:{i.symbol}" for i in instruments]
        data = await self._get("/quote", params={"i": ",".join(symbols)})
        out = {}
        for inst in instruments:
            key = f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}"
            q = data.get(key, {})
            out[inst.symbol] = {
                "last_price": float(q.get("last_price", 0)),
                "bid": float(q.get("depth", {}).get("buy", [{}])[0].get("price", 0)) if q.get("depth") else 0.0,
                "ask": float(q.get("depth", {}).get("sell", [{}])[0].get("price", 0)) if q.get("depth") else 0.0,
                "volume": int(q.get("volume", 0)),
                "oi": int(q.get("oi", 0)),
                "change": float(q.get("net_change", 0)),
                "change_pct": float(q.get("ohlc", {}).get("close", 0) and 0),
            }
        return out

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        symbols = [f"{_EXCHANGE_INV.get(i.exchange, 'NSE')}:{i.symbol}" for i in instruments]
        data = await self._get("/quote/ohlc", params={"i": ",".join(symbols)})
        out = {}
        for inst in instruments:
            key = f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}"
            q = data.get(key, {}).get("ohlc", {})
            out[inst.symbol] = q
        return out

    async def get_historical_data(self, instrument: Instrument, interval: str,
                                  from_date: datetime, to_date: datetime) -> list[dict]:
        token = instrument.token
        f = from_date.strftime("%Y-%m-%d+%H:%M:%S")
        t = to_date.strftime("%Y-%m-%d+%H:%M:%S")
        data = await self._get(f"/instruments/historical/{token}/{interval}", params={"from": f, "to": t})
        return data.get("candles", []) if data else []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        raise NotImplementedError("Use the market-data provider for option chains; broker chains are not normalised")
