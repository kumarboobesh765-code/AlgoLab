"""ICICI Direct (Breeze Connect) broker adapter.

Best-effort :class:`BrokerGateway` implementation over the Breeze Connect REST
API (https://api.icicidirect.com). Auth uses the ``X-Breeze-Connect-*`` headers.
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

_ICICI_BASE = "https://api.icicidirect.com"

_EXCHANGE_MAP = {"NSE": Exchange.NSE, "BSE": Exchange.BSE, "NFO": Exchange.NFO, "BFO": Exchange.BFO, "MCX": Exchange.MCX, "CDS": Exchange.NCDEX}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {"CNC": ProductType.CNC, "MIS": ProductType.MIS, "NRML": ProductType.NRML}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT, "STOPLOSS": OrderType.SL, "STOPLOSSMARKET": OrderType.SL_M}
_ORDER_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {"pending": OrderStatus.PENDING, "complete": OrderStatus.COMPLETE, "partial": OrderStatus.PARTIAL, "rejected": OrderStatus.REJECTED, "cancelled": OrderStatus.CANCELLED, "expired": OrderStatus.EXPIRED, "open": OrderStatus.OPEN}


class IciciGateway(BaseRestBroker):
    name = "icici"
    is_demo = False
    base_url = _ICICI_BASE

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.user_email = config.get("user_email", "")
        self.session_token = config.get("access_token", "")

    def auth_headers(self) -> dict:
        return {
            "X-Breeze-Connect-APIKey": self.api_key,
            "X-Breeze-Connect-UserEmail": self.user_email,
            "X-Breeze-Connect-SessionToken": self.session_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
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
        return await self._request("GET", "/api/v1/customerdetails")

    async def get_funds(self) -> Funds:
        data = await self._request("GET", "/api/v1/funds")
        cash = float(data.get("Success", {}).get("availablelimit", 0) if isinstance(data, dict) else 0)
        return Funds(equity=cash, commodity=0, used_margin=0, available_cash=cash)

    async def get_margin(self) -> Margin:
        data = await self._request("GET", "/api/v1/funds")
        return Margin(equity=data if isinstance(data, dict) else {}, commodity={})

    async def get_positions(self) -> list[Position]:
        data = await self._request("GET", "/api/v1/portfolio/positionsholdings")
        out = []
        for p in data.get("Success", {}).get("Position", []) or []:
            qty = int(float(p.get("quantity", 0)))
            side = OrderSide.BUY if p.get("action", "") == "Buy" else OrderSide.SELL
            out.append(Position(
                symbol=p.get("stockcode", ""),
                exchange=_EXCHANGE_MAP.get(p.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if p.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                product=_PRODUCT_MAP.get(p.get("producttype", "MIS"), ProductType.MIS),
                side=side,
                quantity=abs(qty),
                average_price=float(p.get("avgprice", 0)),
                last_price=float(p.get("ltp", 0)),
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                value=abs(qty) * float(p.get("ltp", 0)),
            ))
        return out

    async def get_holdings(self) -> list[Holding]:
        data = await self._request("GET", "/api/v1/portfolio/positionsholdings")
        out = []
        for h in data.get("Success", {}).get("Holding", []) or []:
            qty = int(float(h.get("quantity", 0)))
            avg = float(h.get("costprice", 0))
            ltp = float(h.get("ltp", 0))
            out.append(Holding(
                symbol=h.get("stockcode", ""),
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
        data = await self._request("GET", "/api/v1/orderbook")
        out = []
        for o in data.get("Success", []) or []:
            status = _STATUS_MAP.get((o.get("orderstatus") or "").lower(), OrderStatus.OPEN)
            filled = int(float(o.get("filledquantity", 0) or 0))
            qty = int(float(o.get("quantity", 0)))
            out.append(Order(
                order_id=str(o.get("orderid", "")),
                broker_order_id=str(o.get("orderid", "")),
                symbol=o.get("stockcode", ""),
                exchange=_EXCHANGE_MAP.get(o.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if o.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                side=OrderSide.BUY if o.get("action", "") == "Buy" else OrderSide.SELL,
                order_type=_ORDER_TYPE_MAP.get((o.get("ordertype") or "MARKET").upper(), OrderType.MARKET),
                product=_PRODUCT_MAP.get(o.get("producttype", "MIS"), ProductType.MIS),
                quantity=qty,
                price=float(o.get("rate", 0)),
                trigger_price=0.0,
                filled_quantity=filled,
                pending_quantity=qty - filled,
                status=status,
                average_price=float(o.get("averageprice", 0)),
                timestamp=datetime.now(),
                update_time=datetime.now(),
                tag=o.get("tag"),
                rejection_reason=o.get("remark"),
            ))
        return out

    async def get_order_history(self, order_id: str) -> list[Order]:
        orders = await self.get_orders()
        return [o for o in orders if o.order_id == order_id]

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        return []

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        errors = self._validate_order_request(request)
        if errors:
            from app.execution.gateway import OrderRejectedError
            raise OrderRejectedError("VALIDATION", "; ".join(errors), self.name)
        body = {
            "stockcode": request.symbol,
            "exchange": _EXCHANGE_INV.get(request.exchange, "NSE"),
            "action": request.side.value,
            "quantity": request.quantity,
            "price": request.price,
            "product": _PRODUCT_INV.get(request.product, "MIS"),
            "ordertype": _ORDER_INV.get(request.order_type, "MARKET"),
        }
        data = await self._request("POST", "/api/v1/orders", json=body)
        oid = data.get("Success", "") if isinstance(data, dict) else str(data)
        return OrderResponse(order_id=str(oid), broker_order_id=str(oid), status=OrderStatus.PENDING, message="Order placed via ICICI")

    async def modify_order(self, order_id: str, quantity=None, price=None, trigger_price=None, order_type=None) -> OrderResponse:
        return OrderResponse(order_id=str(order_id), broker_order_id=str(order_id), status=OrderStatus.PENDING, message="Modify not supported by Breeze")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        body = {"orderid": order_id}
        await self._request("POST", "/api/v1/orders/cancel", json=body)
        return OrderResponse(order_id=str(order_id), broker_order_id=str(order_id), status=OrderStatus.CANCELLED, message="Order cancelled")

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        return []

    async def search_instruments(self, query: str, exchange=None) -> list[Instrument]:
        return []

    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        out = {}
        for inst in instruments:
            out[inst.symbol] = {"last_price": 0.0, "bid": 0.0, "ask": 0.0, "volume": 0, "oi": 0, "change": 0.0, "change_pct": 0.0}
        return out

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        return {i.symbol: {} for i in instruments}

    async def get_historical_data(self, instrument: Instrument, interval: str, from_date: datetime, to_date: datetime) -> list[dict]:
        return []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        raise NotImplementedError("Use the market-data provider for option chains")
