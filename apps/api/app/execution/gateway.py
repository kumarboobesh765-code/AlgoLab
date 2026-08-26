"""Execution gateway abstraction.

Provides a unified interface for all supported Indian brokers.
Each broker implements the BrokerGateway abstract base class.

Supported brokers:
- Zerodha (Kite Connect)
- Upstox (Upstox API v2/v3)
- Angel One (SmartAPI)
- ICICI Direct (Breeze API)
- 5paisa
- Dhan (DhanHQ)
- Kotak Securities (Neo API)
- HDFC Securities
- AliceBlue (Aliceblue API)
- Fyers (Fyers API)
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class OrderSide(StrEnum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"           # Stop Loss
    SL_M = "SL-M"       # Stop Loss Market


class OrderStatus(StrEnum):
    """Order status enumeration."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ProductType(StrEnum):
    """Product type enumeration."""
    CNC = "CNC"         # Cash and Carry (delivery)
    MIS = "MIS"         # Margin Intraday Square-off
    NRML = "NRML"       # Normal (carry forward for F&O)
    CO = "CO"           # Cover Order
    BO = "BO"           # Bracket Order


class Validity(StrEnum):
    """Order validity enumeration."""
    DAY = "DAY"
    IOC = "IOC"         # Immediate or Cancel


class Exchange(StrEnum):
    """Exchange enumeration."""
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"         # NSE F&O
    BFO = "BFO"         # BSE F&O
    MCX = "MCX"
    NCDEX = "NCDEX"


class Segment(StrEnum):
    """Market segment enumeration."""
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"


@dataclass(frozen=True)
class Instrument:
    """Unified instrument representation."""
    symbol: str
    exchange: Exchange
    segment: Segment
    security_id: str          # Broker-specific security ID
    token: str                # Exchange token
    name: str
    expiry: datetime | None = None
    strike: float | None = None
    option_type: str | None = None  # CE/PE
    lot_size: int = 1
    tick_size: float = 0.05


@dataclass(frozen=True)
class OrderRequest:
    """Order placement request."""
    symbol: str
    exchange: Exchange
    segment: Segment
    side: OrderSide
    order_type: OrderType
    quantity: int
    product: ProductType = ProductType.MIS
    validity: Validity = Validity.DAY
    price: float = 0.0
    trigger_price: float = 0.0
    disclosed_quantity: int = 0
    tag: str | None = None  # User-defined tag for identification
    is_amo: bool = False       # After Market Order
    algo_id: str | None = None  # SEBI/clearing-corpus algo registration ID


@dataclass(frozen=True)
class OrderResponse:
    """Order placement response."""
    order_id: str               # Broker's order ID
    broker_order_id: str        # Internal tracking ID
    status: OrderStatus
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class Order:
    """Order details."""
    order_id: str
    broker_order_id: str
    symbol: str
    exchange: Exchange
    segment: Segment
    side: OrderSide
    order_type: OrderType
    product: ProductType
    quantity: int
    price: float
    trigger_price: float
    filled_quantity: int
    pending_quantity: int
    status: OrderStatus
    average_price: float
    timestamp: datetime
    update_time: datetime
    tag: str | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class Position:
    """Position details."""
    symbol: str
    exchange: Exchange
    segment: Segment
    product: ProductType
    side: OrderSide
    quantity: int
    average_price: float
    last_price: float
    unrealized_pnl: float
    realized_pnl: float
    value: float
    multiplier: float = 1.0


@dataclass(frozen=True)
class Holding:
    """Holdings (delivery) details."""
    symbol: str
    exchange: Exchange
    segment: Segment
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    value: float
    isin: str | None = None


@dataclass(frozen=True)
class Margin:
    """Margin details."""
    equity: dict = field(default_factory=dict)      # Available, used, etc.
    commodity: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Funds:
    """Funds/ledger details."""
    equity: float
    commodity: float
    used_margin: float
    available_cash: float
    collateral: float = 0.0


@dataclass(frozen=True)
class Trade:
    """Trade/execution details."""
    trade_id: str
    order_id: str
    symbol: str
    exchange: Exchange
    segment: Segment
    side: OrderSide
    quantity: int
    price: float
    timestamp: datetime
    trade_value: float


class BrokerError(Exception):
    """Broker-specific error."""
    def __init__(self, code: str, message: str, broker: str):
        self.code = code
        self.message = message
        self.broker = broker
        super().__init__(f"[{broker}] {code}: {message}")


class AuthenticationError(BrokerError):
    """Authentication/token error."""
    pass


class RateLimitError(BrokerError):
    """Rate limit exceeded."""
    pass


class InsufficientMarginError(BrokerError):
    """Insufficient margin for order."""
    pass


class OrderRejectedError(BrokerError):
    """Order rejected by broker."""
    pass


class BrokerGateway(ABC):
    """Abstract base class for all broker gateways.

    Each broker must implement this interface to provide a unified
    order management, position tracking, and market data interface.
    """

    name: str = "base"
    is_demo: bool = False
    supports_websocket: bool = False

    def __init__(self, config: dict):
        """Initialize broker gateway with configuration.

        Args:
            config: Broker-specific configuration dict containing:
                - api_key: API key
                - api_secret: API secret
                - access_token: Access token (for session-based auth)
                - redirect_url: OAuth redirect URL
                - other broker-specific params
        """
        self.config = config
        self._connected = False
        self._session = None

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection and authenticate with broker.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from broker."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connected to broker."""
        pass

    @abstractmethod
    async def get_profile(self) -> dict:
        """Get user profile information."""
        pass

    @abstractmethod
    async def get_funds(self) -> Funds:
        """Get available funds/margin."""
        pass

    @abstractmethod
    async def get_margin(self) -> Margin:
        """Get margin details."""
        pass

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        pass

    @abstractmethod
    async def get_holdings(self) -> list[Holding]:
        """Get all holdings (delivery)."""
        pass

    @abstractmethod
    async def get_orders(self) -> list[Order]:
        """Get all orders for the day."""
        pass

    @abstractmethod
    async def get_order_history(self, order_id: str) -> list[Order]:
        """Get order history for a specific order."""
        pass

    @abstractmethod
    async def get_trades(self, from_date: datetime | None = None, to_date: datetime | None = None) -> list[Trade]:
        """Get trade history."""
        pass

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order.

        Args:
            request: Order placement request

        Returns:
            OrderResponse with broker order ID and status

        Raises:
            OrderRejectedError: If order is rejected
            InsufficientMarginError: If insufficient margin
            AuthenticationError: If token expired
            RateLimitError: If rate limited
        """
        pass

    @abstractmethod
    async def modify_order(self, order_id: str, quantity: int | None = None,
                          price: float | None = None, trigger_price: float | None = None,
                          order_type: OrderType | None = None) -> OrderResponse:
        """Modify an existing order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an existing order."""
        pass

    @abstractmethod
    async def get_instruments(self, exchange: Exchange | None = None) -> list[Instrument]:
        """Get instrument master from broker."""
        pass

    @abstractmethod
    async def search_instruments(self, query: str, exchange: Exchange | None = None) -> list[Instrument]:
        """Search instruments by symbol/name."""
        pass

    @abstractmethod
    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        """Get live quotes for instruments.

        Returns:
            Dict mapping instrument symbol to quote data with:
            - last_price, bid, ask, bid_qty, ask_qty, volume, oi, change, change_pct
        """
        pass

    @abstractmethod
    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        """Get OHLC data for instruments."""
        pass

    @abstractmethod
    async def get_historical_data(self, instrument: Instrument,
                                  interval: str, from_date: datetime, to_date: datetime) -> list[dict]:
        """Get historical candle data."""
        pass

    @abstractmethod
    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        """Get option chain for underlying."""
        pass

    # Optional advanced features

    async def place_basket_order(self, orders: list[OrderRequest]) -> list[OrderResponse]:
        """Place multiple orders as a basket (if supported).

        Default implementation places orders sequentially.
        """
        responses = []
        for order in orders:
            try:
                resp = await self.place_order(order)
                responses.append(resp)
            except Exception as e:
                responses.append(OrderResponse(
                    order_id="",
                    broker_order_id="",
                    status=OrderStatus.REJECTED,
                    message=str(e)
                ))
        return responses

    async def place_oco_order(self, entry: OrderRequest, target: OrderRequest, stop_loss: OrderRequest) -> list[OrderResponse]:
        """Place OCO (One Cancels Other) order - target and stop loss.

        Default implementation: places entry, then on fill places target and SL.
        """
        raise NotImplementedError("OCO orders not implemented for this broker")

    async def place_bracket_order(self, entry: OrderRequest, target_price: float, stop_loss_price: float,
                                  trailing_stop: float | None = None) -> list[OrderResponse]:
        """Place bracket order with entry, target, and stop loss.

        Default implementation: places entry, then on fill places target and SL.
        """
        raise NotImplementedError("Bracket orders not implemented for this broker")

    async def get_margins(self, instruments: list[Instrument], side: OrderSide,
                          quantity: int, product: ProductType) -> dict:
        """Get margin required for positions."""
        raise NotImplementedError("Margin calculation not implemented for this broker")

    # WebSocket support (optional)

    async def subscribe_ticks(self, instruments: list[Instrument], callback) -> bool:
        """Subscribe to live tick data via WebSocket.

        Args:
            instruments: List of instruments to subscribe
            callback: Async function to call with tick data

        Returns:
            True if subscription successful
        """
        raise NotImplementedError("WebSocket not implemented for this broker")

    async def unsubscribe_ticks(self, instruments: list[Instrument]) -> bool:
        """Unsubscribe from tick data."""
        raise NotImplementedError("WebSocket not implemented for this broker")

    async def subscribe_order_updates(self, callback) -> bool:
        """Subscribe to order updates via WebSocket."""
        raise NotImplementedError("WebSocket not implemented for this broker")

    # Helper methods

    def _generate_order_id(self) -> str:
        """Generate unique internal order ID."""
        return f"{self.name}_{uuid.uuid4().hex[:12]}"

    def _validate_order_request(self, request: OrderRequest) -> list[str]:
        """Validate order request. Returns list of errors."""
        errors = []
        if request.quantity <= 0:
            errors.append("Quantity must be positive")
        if request.order_type in (OrderType.LIMIT, OrderType.SL) and request.price <= 0:
            errors.append(f"Price required for {request.order_type.value} orders")
        if request.order_type in (OrderType.SL, OrderType.SL_M) and request.trigger_price <= 0:
            errors.append(f"Trigger price required for {request.order_type.value} orders")
        return errors


class MockGateway(BrokerGateway):
    """Mock broker gateway for testing without real broker connection."""

    name = "mock"
    is_demo = True

    def __init__(self, config: dict):
        super().__init__(config)
        self._orders: dict[str, Order] = {}
        self._positions: list[Position] = []
        self._holds: list[Holding] = []
        self._order_counter = 0

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def get_profile(self) -> dict:
        return {"user_id": "MOCK001", "name": "Mock User", "email": "mock@example.com"}

    async def get_funds(self) -> Funds:
        return Funds(equity=1000000, commodity=0, used_margin=0, available_cash=1000000)

    async def get_margin(self) -> Margin:
        return Margin()

    async def get_positions(self) -> list[Position]:
        return self._positions

    async def get_holdings(self) -> list[Holding]:
        return self._holds

    async def get_orders(self) -> list[Order]:
        return list(self._orders.values())

    async def get_order_history(self, order_id: str) -> list[Order]:
        for o in self._orders.values():
            if o.order_id == order_id or o.broker_order_id == order_id:
                return [o]
        return []

    async def get_trades(self, from_date=None, to_date=None) -> list[Trade]:
        return []

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        errors = self._validate_order_request(request)
        if errors:
            return OrderResponse(
                order_id="",
                broker_order_id="",
                status=OrderStatus.REJECTED,
                message="; ".join(errors)
            )

        self._order_counter += 1
        order_id = f"MOCK{self._order_counter:06d}"
        broker_id = self._generate_order_id()

        order = Order(
            order_id=order_id,
            broker_order_id=broker_id,
            symbol=request.symbol,
            exchange=request.exchange,
            segment=request.segment,
            side=request.side,
            order_type=request.order_type,
            product=request.product,
            quantity=request.quantity,
            price=request.price,
            trigger_price=request.trigger_price,
            filled_quantity=request.quantity if request.order_type == OrderType.MARKET else 0,
            pending_quantity=request.quantity,
            status=OrderStatus.COMPLETE if request.order_type == OrderType.MARKET else OrderStatus.OPEN,
            average_price=request.price if request.order_type == OrderType.MARKET else 0,
            timestamp=datetime.now(),
            update_time=datetime.now(),
            tag=request.tag
        )

        self._orders[order_id] = order

        return OrderResponse(
            order_id=order_id,
            broker_order_id=broker_id,
            status=order.status,
            message="Order placed successfully (mock)"
        )

    async def modify_order(self, order_id: str, quantity=None, price=None,
                          trigger_price=None, order_type=None) -> OrderResponse:
        order = self._orders.get(order_id)
        if not order:
            return OrderResponse(order_id="", broker_order_id="", status=OrderStatus.REJECTED, message="Order not found")

        # In mock, just return success
        return OrderResponse(order_id=order_id, broker_order_id=order.broker_order_id, status=OrderStatus.OPEN, message="Modified")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        order = self._orders.get(order_id)
        if not order:
            return OrderResponse(order_id="", broker_order_id="", status=OrderStatus.REJECTED, message="Order not found")

        return OrderResponse(order_id=order_id, broker_order_id=order.broker_order_id, status=OrderStatus.CANCELLED, message="Cancelled")

    async def get_instruments(self, exchange=None) -> list[Instrument]:
        return [
            Instrument(symbol="NIFTY", exchange=Exchange.NSE, segment=Segment.EQUITY,
                      security_id="NIFTY", token="256265", name="NIFTY 50", lot_size=50),
            Instrument(symbol="BANKNIFTY", exchange=Exchange.NSE, segment=Segment.EQUITY,
                      security_id="BANKNIFTY", token="260105", name="NIFTY BANK", lot_size=25),
        ]

    async def search_instruments(self, query: str, exchange=None) -> list[Instrument]:
        return [inst for inst in await self.get_instruments(exchange) if query.upper() in inst.symbol.upper()]

    async def get_quote(self, instruments: list[Instrument]) -> dict[str, dict]:
        return {inst.symbol: {"last_price": 22000.0, "change": 100.0, "change_pct": 0.45, "volume": 10000, "oi": 50000} for inst in instruments}

    async def get_ohlc(self, instruments: list[Instrument]) -> dict[str, dict]:
        return {inst.symbol: {"open": 21900, "high": 22100, "low": 21850, "close": 22000} for inst in instruments}

    async def get_historical_data(self, instrument: Instrument, interval: str, from_date: datetime, to_date: datetime) -> list[dict]:
        return []

    async def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict:
        return {"underlying": underlying, "expiry": expiry or "2024-12-26", "spot": 22000, "strikes": []}
