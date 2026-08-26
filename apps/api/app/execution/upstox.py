"""Upstox (v2 API) broker adapter.

Implements the :class:`BrokerGateway` interface over the Upstox REST API
(https://api.upstox.com/v2). Auth uses a bearer access token obtained via the
Upstox OAuth flow and supplied in config under ``access_token``.
"""

import json
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

_UPSTOX_BASE = "https://api.upstox.com/v2"

_EXCHANGE_MAP = {
    "NSE": Exchange.NSE,
    "BSE": Exchange.BSE,
    "NFO": Exchange.NFO,
    "BFO": Exchange.BFO,
    "MCX": Exchange.MCX,
    "CDS": Exchange.NCDEX,
}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {"INTRADAY": ProductType.MIS, "DELIVERY": ProductType.CNC, "NORMAL": ProductType.NRML}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {
    "MARKET": OrderType.MARKET,
    "LIMIT": OrderType.LIMIT,
    "SL": OrderType.SL,
    "SL-M": OrderType.SL_M,
}
_ORDER_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "pending": OrderStatus.PENDING,
    "complete": OrderStatus.COMPLETE,
    "partial": OrderStatus.PARTIAL,
    "rejected": OrderStatus.REJECTED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
}


class UpstoxGateway(BaseRestBroker):
    name = "upstox"
    is_demo = False
    base_url = _UPSTOX_BASE

    def __init__(self, config: dict):
        super().__init__(config)
        self.access_token = config.get("access_token", "")

    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}

    # -- lifecycle -----------------------------------------------------------

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
        return await self._request("GET", "/user/profile")

    async def get_funds(self) -> Funds:
        data = await self._request("GET", "/user/get-funds-and-margin")
        equity = data.get("equity", {})
        return Funds(
            equity=float(equity.get("available_margin", 0)),
            commodity=float(data.get("commodity", {}).get("available_margin", 0)),
            used_margin=float(equity.get("used_margin", 0)),
            available_cash=float(equity.get("available_cash", 0)),
        )

    async def get_margin(self) -> Margin:
        data = await self._request("GET", "/user/get-funds-and-margin")
        return Margin(equity=data.get("equity", {}), commodity=data.get("commodity", {}))

    async def get_positions(self) -> list[Position]:
        data = await self._request("GET", "/portfolio/positions")
        out = []
        for p in data.get("net_positions", []):
            qty = int(float(p.get("quantity", 0)))
            side = OrderSide.BUY if qty >= 0 else OrderSide.SELL
            out.append(Position(
                symbol=p.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(p.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if p.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                product=_PRODUCT_MAP.get(p.get("product", "INTRADAY"), ProductType.MIS),
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
        data = await self._request("GET", "/portfolio/holdings")
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
        data = await self._request("GET", "/order/history")
        return [self._map_order(o) for o in data.get("data", [])]

    def _map_order(self, o: dict) -> Order:
        status = _STATUS_MAP.get((o.get("status") or "").lower(), OrderStatus.OPEN)
        filled = int(float(o.get("filled_quantity", 0)))
        qty = int(float(o.get("quantity", 0)))
        return Order(
            order_id=str(o.get("order_id", "")),
            broker_order_id=str(o.get("order_id", "")),
            symbol=o.get("tradingsymbol", ""),
            exchange=_EXCHANGE_MAP.get(o.get("exchange", ""), Exchange.NSE),
            segment=Segment.EQUITY if o.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
            side=OrderSide.BUY if o.get("transaction_type") == "BUY" else OrderSide.SELL,
            order_type=_ORDER_TYPE_MAP.get(o.get("order_type", "MARKET"), OrderType.MARKET),
            product=_PRODUCT_MAP.get(o.get("product", "INTRADAY"), ProductType.MIS),
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
        data = await self._request("GET", f"/order/details/{order_id}")
        orders = data if isinstance(data, list) else [data]
        return [self._map_order(o) for o in orders]

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        data = await self._request("GET", "/order/trades")
        out = []
        for t in data.get("data", []):
            out.append(Trade(
                trade_id=str(t.get("trade_id", "")),
                order_id=str(t.get("order_id", "")),
                symbol=t.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(t.get("exchange", ""), Exchange.NSE),
                segment=Segment.EQUITY if t.get("exchange") not in ("NFO", "BFO") else Segment.OPTIONS,
                side=OrderSide.BUY if t.get("transaction_type") == "BUY" else OrderSide.SELL,
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
            "symbol": request.symbol,
            "exchange": _EXCHANGE_INV.get(request.exchange, "NSE"),
            "transaction_type": request.side.value,
            "order_type": _ORDER_INV.get(request.order_type, "MARKET"),
            "quantity": request.quantity,
            "product": _PRODUCT_INV.get(request.product, "INTRADAY"),
            "validity": request.validity.value,
            "tag": request.tag or "strategylab",
        }
        if request.order_type in (OrderType.LIMIT, OrderType.SL):
            body["price"] = request.price
        if request.order_type in (OrderType.SL, OrderType.SL_M):
            body["trigger_price"] = request.trigger_price
        data = await self._request("POST", "/order/place", json=body)
        return OrderResponse(
            order_id=str(data.get("order_id", "")),
            broker_order_id=str(data.get("order_id", "")),
            status=OrderStatus.PENDING,
            message="Order placed via Upstox",
        )

    async def modify_order(self, order_id: str, quantity=None, price=None,
                           trigger_price=None, order_type=None) -> OrderResponse:
        body = {}
        if quantity is not None:
            body["quantity"] = quantity
        if price is not None:
            body["price"] = price
        if trigger_price is not None:
            body["trigger_price"] = trigger_price
        if order_type is not None:
            body["order_type"] = _ORDER_INV.get(order_type, "LIMIT")
        data = await self._request("PUT", f"/order/modify/{order_id}", json=body)
        return OrderResponse(
            order_id=str(order_id),
            broker_order_id=str(data.get("order_id", order_id)),
            status=OrderStatus.PENDING,
            message="Order modified",
        )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        data = await self._request("DELETE", f"/order/cancel/{order_id}")
        return OrderResponse(
            order_id=str(order_id),
            broker_order_id=str(data.get("order_id", order_id)),
            status=OrderStatus.CANCELLED,
            message="Order cancelled",
        )

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        params = {"exchange": _EXCHANGE_INV.get(exchange)} if exchange else None
        data = await self._request("GET", "/market-data/instruments", params=params)
        out = []
        for row in data.get("data", []):
            seg = Segment.OPTIONS if row.get("instrument_type") in ("CE", "PE") else (
                Segment.FUTURES if row.get("instrument_type") in ("FUT", "FUTIDX") else Segment.EQUITY)
            out.append(Instrument(
                symbol=row.get("tradingsymbol", ""),
                exchange=_EXCHANGE_MAP.get(row.get("exchange", ""), Exchange.NSE),
                segment=seg,
                security_id=str(row.get("instrument_key", "")),
                token=str(row.get("exchange_token", "")),
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
        data = await self._request("GET", "/market-quote/quotes", params={"symbol": ",".join(symbols)})
        out = {}
        for inst in instruments:
            q = data.get("data", {}).get(f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}", {})
            ltpc = q.get("last_price", 0)
            out[inst.symbol] = {
                "last_price": float(ltpc),
                "bid": float(q.get("depth", {}).get("buy", [{}])[0].get("price", 0)) if q.get("depth") else 0.0,
                "ask": float(q.get("depth", {}).get("sell", [{}])[0].get("price", 0)) if q.get("depth") else 0.0,
                "volume": int(q.get("volume", 0)),
                "oi": int(q.get("oi", 0)),
                "change": float(q.get("net_change", 0)),
                "change_pct": 0.0,
            }
        return out

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        symbols = [f"{_EXCHANGE_INV.get(i.exchange, 'NSE')}:{i.symbol}" for i in instruments]
        data = await self._request("GET", "/market-quote/ohlc", params={"symbol": ",".join(symbols), "interval": "day"})
        out = {}
        for inst in instruments:
            key = f"{_EXCHANGE_INV.get(inst.exchange, 'NSE')}:{inst.symbol}"
            out[inst.symbol] = data.get("data", {}).get(key, {}).get("ohlc", {})
        return out

    async def get_historical_data(self, instrument: Instrument, interval: str,
                                  from_date: datetime, to_date: datetime) -> list[dict]:
        params = {
            "instrument_key": instrument.security_id,
            "interval": interval,
            "to_date": to_date.strftime("%Y-%m-%d"),
            "from_date": from_date.strftime("%Y-%m-%d"),
        }
        data = await self._request("GET", "/historical-candle", params=params)
        return data.get("candles", []) if data else []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        raise NotImplementedError("Use the market-data provider for option chains")

    # -- WebSocket live streaming --------------------------------------------

    async def subscribe_ticks(self, instruments: list[Instrument], callback) -> bool:
        """Stream live ticks via the Upstox WebSocket feed (JSON mode)."""
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("websockets package required for live streaming") from exc
        keys = [i.security_id for i in instruments if i.security_id]
        url = f"wss://ws.upstox.com/feed/api/v2/stream?access_token={self.access_token}"
        async with websockets.connect(url) as ws:
            if keys:
                await ws.send(json.dumps({"guid": "strategylab", "method": "sub", "data": {"instrumentKeys": keys}}))
            async for raw in ws:
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    await callback(payload)
        return True

    async def subscribe_order_updates(self, callback) -> bool:
        """Placeholder for Upstox order-update streaming."""
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("websockets package required for live streaming") from exc
        url = f"wss://ws.upstox.com/feed/api/v2/stream?access_token={self.access_token}"
        async with websockets.connect(url) as ws:
            async for raw in ws:
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                await callback(payload)
        return True
