"""Angel One (SmartAPI) broker adapter.

Best-effort implementation of the :class:`BrokerGateway` interface over the
Angel One SmartAPI REST surface (https://apiconnect.angelone.in). Auth uses a
JWT ``access_token`` (obtained via the SmartAPI login flow) supplied in config.
"""

from datetime import datetime

from app.execution.base_rest import BaseRestBroker
from app.execution.gateway import (
    Exchange,
    Funds,
    Holding,
    Instrument,
    Margin,
    Order,
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

_ANGEL_BASE = "https://apiconnect.angelone.in"

_EXCHANGE_MAP = {
    "NSE": Exchange.NSE,
    "BSE": Exchange.BSE,
    "NFO": Exchange.NFO,
    "BFO": Exchange.BFO,
    "MCX": Exchange.MCX,
    "CDS": Exchange.NCDEX,
}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {"CNC": ProductType.CNC, "MIS": ProductType.MIS, "NRML": ProductType.NRML}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT, "SL": OrderType.SL, "SL-M": OrderType.SL_M}
_ORDER_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "pending": OrderStatus.PENDING,
    "complete": OrderStatus.COMPLETE,
    "partiallyfilled": OrderStatus.PARTIAL,
    "rejected": OrderStatus.REJECTED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
}


class AngelOneGateway(BaseRestBroker):
    name = "angelone"
    is_demo = False
    base_url = _ANGEL_BASE

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.access_token = config.get("access_token", "")

    def auth_headers(self) -> dict:
        return {
            "X-PrivateKey": self.api_key,
            "Authorization": self.access_token,
            "X-SourceType": "WEB",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

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
        return await self._request("POST", "/rest/secure/angelbroking/user/v1/getProfile")

    async def get_funds(self) -> Funds:
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/rms")
        net = float(data.get("data", {}).get("availablecash", 0))
        return Funds(equity=net, commodity=0, used_margin=0, available_cash=net)

    async def get_margin(self) -> Margin:
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/rms")
        return Margin(equity=data.get("data", {}), commodity={})

    async def get_positions(self) -> list[Position]:
        data = await self._request("POST", "/rest/secure/angelbroking/position/v1/details")
        out = []
        for p in data.get("data", {}).get("net", []):
            qty = int(float(p.get("netqty", 0)))
            side = OrderSide.BUY if qty >= 0 else OrderSide.SELL
            out.append(Position(
                symbol=p.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(p.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if p.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                product=_PRODUCT_MAP.get(p.get("producttype", "MIS"), ProductType.MIS),
                side=side,
                quantity=abs(qty),
                average_price=float(p.get("averageprice", 0)),
                last_price=float(p.get("ltp", 0)),
                unrealized_pnl=float(p.get("pnl", 0)) * (1 if side == OrderSide.BUY else -1),
                realized_pnl=0.0,
                value=abs(qty) * float(p.get("ltp", 0)),
            ))
        return out

    async def get_holdings(self) -> list[Holding]:
        data = await self._request("POST", "/rest/secure/angelbroking/portfolio/v1/holdings")
        out = []
        for h in data.get("data", []):
            qty = int(float(h.get("quantity", 0)))
            avg = float(h.get("avgprice", 0))
            ltp = float(h.get("ltp", 0))
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
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/details")
        return [self._map_order(o) for o in data.get("data", []) or []]

    def _map_order(self, o: dict) -> Order:
        status = _STATUS_MAP.get((o.get("status") or "").lower(), OrderStatus.OPEN)
        filled = int(float(o.get("filledshares", 0) or 0))
        qty = int(float(o.get("quantity", 0)))
        return Order(
            order_id=str(o.get("orderid", "")),
            broker_order_id=str(o.get("orderid", "")),
            symbol=o.get("tradingsymbol", ""),
            exchange=_EXCHANGE_MAP.get(o.get("exchange", ""), Exchange.NSE),
            segment=Segment.EQUITY if o.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
            side=OrderSide.BUY if o.get("transactiontype") == "BUY" else OrderSide.SELL,
            order_type=_ORDER_TYPE_MAP.get(o.get("ordertype", "MARKET"), OrderType.MARKET),
            product=_PRODUCT_MAP.get(o.get("producttype", "MIS"), ProductType.MIS),
            quantity=qty,
            price=float(o.get("price", 0)),
            trigger_price=float(o.get("triggerprice", 0)),
            filled_quantity=filled,
            pending_quantity=qty - filled,
            status=status,
            average_price=float(o.get("averageprice", 0)),
            timestamp=datetime.now(),
            update_time=datetime.now(),
            tag=o.get("tag"),
            rejection_reason=o.get("text"),
        )

    async def get_order_history(self, order_id: str) -> list[Order]:
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/details")
        orders = [self._map_order(o) for o in data.get("data", []) or []]
        return [o for o in orders if o.order_id == order_id]

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/tradeBook")
        out = []
        for t in data.get("data", []) or []:
            out.append(Trade(
                trade_id=str(t.get("tradeid", "")),
                order_id=str(t.get("orderid", "")),
                symbol=t.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(t.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if t.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                side=OrderSide.BUY if t.get("transactiontype") == "BUY" else OrderSide.SELL,
                quantity=int(float(t.get("quantity", 0))),
                price=float(t.get("price", 0)),
                timestamp=datetime.now(),
                trade_value=int(float(t.get("quantity", 0))) * float(t.get("price", 0)),
            ))
        return out

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        errors = self._validate_order_request(request)
        if errors:
            from app.execution.gateway import OrderRejectedError
            raise OrderRejectedError("VALIDATION", "; ".join(errors), self.name)
        body = {
            "variety": "NORMAL",
            "tradingsymbol": request.symbol,
            "symboltoken": request.symbol,
            "exchange": _EXCHANGE_INV.get(request.exchange, "NSE"),
            "transactiontype": request.side.value,
            "ordertype": _ORDER_INV.get(request.order_type, "MARKET"),
            "quantity": request.quantity,
            "producttype": _PRODUCT_INV.get(request.product, "MIS"),
            "duration": request.validity.value,
            "price": request.price,
            "triggerprice": request.trigger_price,
            "tag": request.tag or "strategylab",
        }
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/placeOrder", json=body)
        return OrderResponse(
            order_id=str(data.get("data", {}).get("orderid", "")),
            broker_order_id=str(data.get("data", {}).get("orderid", "")),
            status=OrderStatus.PENDING,
            message="Order placed via Angel One",
        )

    async def modify_order(self, order_id: str, quantity=None, price=None,
                           trigger_price=None, order_type=None) -> OrderResponse:
        body = {"orderid": order_id, "variety": "NORMAL", "duration": "DAY"}
        if price is not None:
            body["price"] = price
        if trigger_price is not None:
            body["triggerprice"] = trigger_price
        if order_type is not None:
            body["ordertype"] = _ORDER_INV.get(order_type, "LIMIT")
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/modifyOrder", json=body)
        return OrderResponse(
            order_id=str(order_id),
            broker_order_id=str(data.get("data", {}).get("orderid", order_id)),
            status=OrderStatus.PENDING,
            message="Order modified",
        )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        body = {"orderid": order_id, "variety": "NORMAL"}
        data = await self._request("POST", "/rest/secure/angelbroking/order/v1/cancelOrder", json=body)
        return OrderResponse(
            order_id=str(order_id),
            broker_order_id=str(data.get("data", {}).get("orderid", order_id)),
            status=OrderStatus.CANCELLED,
            message="Order cancelled",
        )

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        # Angel exposes an instrument dump; we return an empty list when not cached.
        return []

    async def search_instruments(self, query: str, exchange=None) -> list[Instrument]:
        return []

    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        symbols = [f"{_EXCHANGE_INV.get(i.exchange, 'NSE')}:{i.symbol}" for i in instruments]
        data = await self._request("POST", "/rest/secure/angelbroking/market/v1/quote", json={"mode": "LTP", "symboltoken": symbols})
        out = {}
        for inst in instruments:
            q = data.get("data", {}).get(f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}", {})
            out[inst.symbol] = {
                "last_price": float(q.get("ltp", 0)),
                "bid": 0.0,
                "ask": 0.0,
                "volume": int(q.get("volume", 0)),
                "oi": int(q.get("oi", 0)),
                "change": 0.0,
                "change_pct": 0.0,
            }
        return out

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        return {i.symbol: {} for i in instruments}

    async def get_historical_data(self, instrument: Instrument, interval: str,
                                  from_date: datetime, to_date: datetime) -> list[dict]:
        return []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        raise NotImplementedError("Use the market-data provider for option chains")
