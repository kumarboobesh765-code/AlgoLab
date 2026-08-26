"""Fyers broker adapter.

Best-effort :class:`BrokerGateway` implementation over the Fyers v3 API
(https://api.fyers.in). Auth uses a ``Bearer`` ``access_token`` header.
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

_FYERS_BASE = "https://api.fyers.in"

_EXCHANGE_MAP = {"NSE": Exchange.NSE, "BSE": Exchange.BSE, "NFO": Exchange.NFO, "BFO": Exchange.BFO, "MCX": Exchange.MCX, "CDS": Exchange.NCDEX}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {"CNC": ProductType.CNC, "INTRADAY": ProductType.MIS, "MARGIN": ProductType.MIS, "NRML": ProductType.NRML}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT, "SL": OrderType.SL, "SL-M": OrderType.SL_M}
_ORDER_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {"PENDING": OrderStatus.PENDING, "COMPLETED": OrderStatus.COMPLETE, "PARTIALLY_FILLED": OrderStatus.PARTIAL, "CANCELED": OrderStatus.CANCELLED, "REJECTED": OrderStatus.REJECTED, "EXPIRED": OrderStatus.EXPIRED, "OPEN": OrderStatus.OPEN}


class FyersGateway(BaseRestBroker):
    name = "fyers"
    is_demo = False
    base_url = _FYERS_BASE

    def __init__(self, config: dict):
        super().__init__(config)
        self.access_token = config.get("access_token", "")

    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

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
        return await self._request("GET", "/api/v3/profile")

    async def get_funds(self) -> Funds:
        data = await self._request("GET", "/api/v3/funds")
        cash = float(data.get("fund_limit", {}).get("cash", 0))
        return Funds(equity=cash, commodity=0, used_margin=float(data.get("fund_limit", {}).get("utilized", 0)), available_cash=cash)

    async def get_margin(self) -> Margin:
        data = await self._request("GET", "/api/v3/funds")
        return Margin(equity=data.get("fund_limit", {}), commodity={})

    async def get_positions(self) -> list[Position]:
        data = await self._request("GET", "/api/v3/positions")
        out = []
        for p in data.get("net_positions", []):
            qty = int(float(p.get("net_qty", 0)))
            side = OrderSide.BUY if qty >= 0 else OrderSide.SELL
            out.append(Position(
                symbol=p.get("symbol", "").split(":")[-1],
                exchange=_EXCHANGE_MAP.get(p.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if p.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                product=_PRODUCT_MAP.get(p.get("product_type", "INTRADAY"), ProductType.MIS),
                side=side,
                quantity=abs(qty),
                average_price=float(p.get("avg_price", 0)),
                last_price=float(p.get("ltp", 0)),
                unrealized_pnl=float(p.get("pnl", 0)) * (1 if side == OrderSide.BUY else -1),
                realized_pnl=0.0,
                value=abs(qty) * float(p.get("ltp", 0)),
            ))
        return out

    async def get_holdings(self) -> list[Holding]:
        data = await self._request("GET", "/api/v3/holdings")
        out = []
        for h in data.get("holdings", []):
            qty = int(float(h.get("quantity", 0)))
            avg = float(h.get("cost_price", 0))
            ltp = float(h.get("market_price", 0))
            out.append(Holding(
                symbol=h.get("symbol", "").split(":")[-1],
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
        data = await self._request("GET", "/api/v3/orders")
        return [self._map_order(o) for o in data.get("orderbook", []) or []]

    def _map_order(self, o: dict) -> Order:
        status = _STATUS_MAP.get((o.get("status") or "").upper(), OrderStatus.OPEN)
        filled = int(float(o.get("filled_qty", 0) or 0))
        qty = int(float(o.get("qty", 0)))
        sym = o.get("symbol", "")
        return Order(
            order_id=str(o.get("id", "")),
            broker_order_id=str(o.get("id", "")),
            symbol=sym.split(":")[-1],
            exchange=_EXCHANGE_MAP.get(sym.split(":")[0] if ":" in sym else "NSE", Exchange.NSE),
            segment=Segment.EQUITY,
            side=OrderSide.BUY if o.get("side") == 1 else OrderSide.SELL,
            order_type=_ORDER_TYPE_MAP.get(o.get("type", "MARKET"), OrderType.MARKET),
            product=_PRODUCT_MAP.get(o.get("productType", "INTRADAY"), ProductType.MIS),
            quantity=qty,
            price=float(o.get("limitPrice", 0)),
            trigger_price=float(o.get("stopPrice", 0)),
            filled_quantity=filled,
            pending_quantity=qty - filled,
            status=status,
            average_price=float(o.get("avgFillPrice", 0)),
            timestamp=datetime.now(),
            update_time=datetime.now(),
            tag=o.get("tag"),
            rejection_reason=o.get("message"),
        )

    async def get_order_history(self, order_id: str) -> list[Order]:
        data = await self._request("GET", "/api/v3/orders")
        return [self._map_order(o) for o in data.get("orderbook", []) or [] if str(o.get("id", "")) == order_id]

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        data = await self._request("GET", "/api/v3/trades")
        out = []
        for t in data.get("tradebook", []) or []:
            sym = t.get("symbol", "")
            out.append(Trade(
                trade_id=str(t.get("id", "")),
                order_id=str(t.get("orderId", "")),
                symbol=sym.split(":")[-1],
                exchange=_EXCHANGE_MAP.get(sym.split(":")[0] if ":" in sym else "NSE", Exchange.NSE),
                segment=Segment.EQUITY,
                side=OrderSide.BUY if t.get("side") == 1 else OrderSide.SELL,
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
            "symbol": f"{_EXCHANGE_INV.get(request.exchange, 'NSE')}:{request.symbol}",
            "qty": request.quantity,
            "type": _ORDER_INV.get(request.order_type, "MARKET"),
            "side": 1 if request.side == OrderSide.BUY else -1,
            "productType": _PRODUCT_INV.get(request.product, "INTRADAY"),
            "validity": request.validity.value,
            "limitPrice": request.price,
            "stopPrice": request.trigger_price,
            "tag": request.tag or "strategylab",
        }
        data = await self._request("POST", "/api/v3/orders", json=body)
        return OrderResponse(order_id=str(data.get("id", "")), broker_order_id=str(data.get("id", "")), status=OrderStatus.PENDING, message="Order placed via Fyers")

    async def modify_order(self, order_id: str, quantity=None, price=None, trigger_price=None, order_type=None) -> OrderResponse:
        body = {"id": order_id}
        if price is not None:
            body["limitPrice"] = price
        if trigger_price is not None:
            body["stopPrice"] = trigger_price
        if order_type is not None:
            body["type"] = _ORDER_INV.get(order_type, "LIMIT")
        data = await self._request("PUT", f"/api/v3/orders/{order_id}", json=body)
        return OrderResponse(order_id=str(order_id), broker_order_id=str(data.get("id", order_id)), status=OrderStatus.PENDING, message="Order modified")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        data = await self._request("DELETE", f"/api/v3/orders/{order_id}")
        return OrderResponse(order_id=str(order_id), broker_order_id=str(data.get("id", order_id)), status=OrderStatus.CANCELLED, message="Order cancelled")

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        return []

    async def search_instruments(self, query: str, exchange=None) -> list[Instrument]:
        return []

    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        symbols = [f"{_EXCHANGE_INV.get(i.exchange, 'NSE')}:{i.symbol}" for i in instruments]
        data = await self._request("GET", f"/api/v3/quotes?symbols={','.join(symbols)}")
        out = {}
        for inst in instruments:
            key = f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}"
            q = data.get("d", {}).get(key, data.get(key, {}))
            out[inst.symbol] = {"last_price": float((q.get("v") or {}).get("lp", 0)), "bid": 0.0, "ask": 0.0, "volume": int(q.get("v", {}).get("v", 0)), "oi": 0, "change": 0.0, "change_pct": 0.0}
        return out

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        return {i.symbol: {} for i in instruments}

    async def get_historical_data(self, instrument: Instrument, interval: str, from_date: datetime, to_date: datetime) -> list[dict]:
        return []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        raise NotImplementedError("Use the market-data provider for option chains")
