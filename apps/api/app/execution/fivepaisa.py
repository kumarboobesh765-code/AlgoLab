"""5paisa broker adapter.

Best-effort :class:`BrokerGateway` implementation over the 5paisa OpenAPI
(https://Openapi.5paisa.com). Auth uses the ``Authorization`` / ``Content-Type``
headers; the session token is supplied in config as ``access_token``.
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

_FIVEPAISA_BASE = "https://Openapi.5paisa.com"

_EXCHANGE_MAP = {"N": Exchange.NSE, "B": Exchange.BSE, "NFO": Exchange.NFO, "BFO": Exchange.BFO, "MCX": Exchange.MCX, "CDS": Exchange.NCDEX}
_EXCHANGE_INV = {v: k for k, v in _EXCHANGE_MAP.items()}

_PRODUCT_MAP = {"C": ProductType.CNC, "M": ProductType.MIS, "NRML": ProductType.NRML}
_PRODUCT_INV = {v: k for k, v in _PRODUCT_MAP.items()}

_ORDER_TYPE_MAP = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT, "SL": OrderType.SL, "SLM": OrderType.SL_M}
_ORDER_INV = {v: k for k, v in _ORDER_TYPE_MAP.items()}

_STATUS_MAP = {"pending": OrderStatus.PENDING, "complete": OrderStatus.COMPLETE, "partial": OrderStatus.PARTIAL, "rejected": OrderStatus.REJECTED, "cancelled": OrderStatus.CANCELLED, "expired": OrderStatus.EXPIRED, "open": OrderStatus.OPEN}


class FivePaisaGateway(BaseRestBroker):
    name = "5paisa"
    is_demo = False
    base_url = _FIVEPAISA_BASE

    def __init__(self, config: dict):
        super().__init__(config)
        self.access_token = config.get("access_token", "")
        self.client_id = config.get("client_id", "")

    def auth_headers(self) -> dict:
        return {"Authorization": self.access_token, "Content-Type": "application/json"}

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
        return await self._request("POST", "/VendorsAPI/Service1.svc/v2/Login/GetClientDetails", json={})

    async def get_funds(self) -> Funds:
        data = await self._request("POST", "/VendorsAPI/Service1.svc/v1/Margin/GetMargin", json={})
        cash = float(data.get("EquityMargin", {}).get("AvailableMargin", 0) if isinstance(data, dict) else 0)
        return Funds(equity=cash, commodity=0, used_margin=0, available_cash=cash)

    async def get_margin(self) -> Margin:
        data = await self._request("POST", "/VendorsAPI/Service1.svc/v1/Margin/GetMargin", json={})
        return Margin(equity=data if isinstance(data, dict) else {}, commodity={})

    async def get_positions(self) -> list[Position]:
        data = await self._request("POST", "/VendorsAPI/Service1.svc/v1/NetPositionNetWise", json={})
        out = []
        for p in data.get("NetPositionDetail", []) or []:
            qty = int(float(p.get("NetQty", 0)))
            side = OrderSide.BUY if qty >= 0 else OrderSide.SELL
            out.append(Position(
                symbol=p.get("TradSym", ""),
                exchange=_EXCHANGE_MAP.get(p.get("Exch", ""), Exchange.NSE),
                segment=Segment.EQUITY if p.get("Exch") not in ("NFO", "BFO") else Segment.OPTIONS,
                product=_PRODUCT_MAP.get(p.get("Product", "M"), ProductType.MIS),
                side=side,
                quantity=abs(qty),
                average_price=float(p.get("AvgPrc", 0)),
                last_price=float(p.get("LTP", 0)),
                unrealized_pnl=float(p.get("UpldPnl", 0)) * (1 if side == OrderSide.BUY else -1),
                realized_pnl=0.0,
                value=abs(qty) * float(p.get("LTP", 0)),
            ))
        return out

    async def get_holdings(self) -> list[Holding]:
        data = await self._request("POST", "/VendorsAPI/Service1.svc/v1/Holding/GetHoldings", json={})
        out = []
        for h in data.get("HoldingDetail", []) or []:
            qty = int(float(h.get("Qty", 0)))
            avg = float(h.get("AvgPrice", 0))
            ltp = float(h.get("LTP", 0))
            out.append(Holding(
                symbol=h.get("TradSym", ""),
                exchange=_EXCHANGE_MAP.get(h.get("Exch", ""), Exchange.NSE),
                segment=Segment.EQUITY,
                quantity=qty,
                average_price=avg,
                last_price=ltp,
                pnl=(ltp - avg) * qty,
                value=ltp * qty,
                isin=h.get("ISIN"),
            ))
        return out

    async def get_orders(self) -> list[Order]:
        data = await self._request("POST", "/VendorsAPI/Service1.svc/v1/OrderBook/GetOrderBook", json={})
        out = []
        for o in data.get("OrderBookDetail", []) or []:
            status = _STATUS_MAP.get((o.get("OrderStatus", "") or "").lower(), OrderStatus.OPEN)
            filled = int(float(o.get("FilledQty", 0) or 0))
            qty = int(float(o.get("Qty", 0)))
            out.append(Order(
                order_id=str(o.get("ExchOrderID", "")),
                broker_order_id=str(o.get("ExchOrderID", "")),
                symbol=o.get("TradSym", ""),
                exchange=_EXCHANGE_MAP.get(o.get("Exch", ""), Exchange.NSE),
                segment=Segment.EQUITY if o.get("Exch") not in ("NFO", "BFO") else Segment.OPTIONS,
                side=OrderSide.BUY if o.get("Action", "") == "Buy" else OrderSide.SELL,
                order_type=_ORDER_TYPE_MAP.get((o.get("OrderType", "") or "MARKET").upper(), OrderType.MARKET),
                product=_PRODUCT_MAP.get(o.get("Product", "M"), ProductType.MIS),
                quantity=qty,
                price=float(o.get("Price", 0)),
                trigger_price=float(o.get("TriggerPrice", 0)),
                filled_quantity=filled,
                pending_quantity=qty - filled,
                status=status,
                average_price=float(o.get("AvgPrice", 0)),
                timestamp=datetime.now(),
                update_time=datetime.now(),
                tag=o.get("Tag"),
                rejection_reason=o.get("Reason"),
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
            "Exchange": _EXCHANGE_INV.get(request.exchange, "N"),
            "TradingSymbol": request.symbol,
            "Action": request.side.value,
            "OrderType": _ORDER_INV.get(request.order_type, "MARKET"),
            "Qty": request.quantity,
            "Price": request.price,
            "TriggerPrice": request.trigger_price,
            "Product": _PRODUCT_INV.get(request.product, "M"),
        }
        data = await self._request("POST", "/VendorsAPI/Service1.svc/v1/Order/PlaceOrder", json=body)
        oid = data.get("BrokerOrderID", "") if isinstance(data, dict) else str(data)
        return OrderResponse(order_id=str(oid), broker_order_id=str(oid), status=OrderStatus.PENDING, message="Order placed via 5paisa")

    async def modify_order(self, order_id: str, quantity=None, price=None, trigger_price=None, order_type=None) -> OrderResponse:
        return OrderResponse(order_id=str(order_id), broker_order_id=str(order_id), status=OrderStatus.PENDING, message="Modify not supported")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        body = {"ExchOrderID": order_id}
        await self._request("POST", "/VendorsAPI/Service1.svc/v1/Order/CancelOrder", json=body)
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
