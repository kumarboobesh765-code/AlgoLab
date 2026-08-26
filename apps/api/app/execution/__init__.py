"""Execution gateway package."""

from app.execution.angelone import AngelOneGateway
from app.execution.dhan import DhanGateway
from app.execution.fivepaisa import FivePaisaGateway
from app.execution.fyers import FyersGateway
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
    MockGateway,
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
    Validity,
)
from app.execution.icici import IciciGateway
from app.execution.upstox import UpstoxGateway
from app.execution.zerodha import ZerodhaGateway

__all__ = [
    "BrokerGateway",
    "MockGateway",
    "ZerodhaGateway",
    "UpstoxGateway",
    "AngelOneGateway",
    "DhanGateway",
    "FyersGateway",
    "IciciGateway",
    "FivePaisaGateway",
    "Instrument",
    "OrderRequest",
    "OrderResponse",
    "Order",
    "Position",
    "Holding",
    "Margin",
    "Funds",
    "Trade",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "ProductType",
    "Validity",
    "Exchange",
    "Segment",
    "BrokerError",
    "AuthenticationError",
    "RateLimitError",
    "InsufficientMarginError",
    "OrderRejectedError",
]

# Broker registry
_BROKER_REGISTRY: dict[str, type[BrokerGateway]] = {
    "mock": MockGateway,
    "zerodha": ZerodhaGateway,
    "upstox": UpstoxGateway,
    "angelone": AngelOneGateway,
    "dhan": DhanGateway,
    "fyers": FyersGateway,
    "icici": IciciGateway,
    "5paisa": FivePaisaGateway,
}


def register_broker(name: str, gateway_class: type[BrokerGateway]) -> None:
    """Register a broker gateway implementation."""
    _BROKER_REGISTRY[name.lower()] = gateway_class


def get_broker_gateway(name: str, config: dict) -> BrokerGateway:
    """Create broker gateway instance.

    Args:
        name: Broker name (e.g., "zerodha", "upstox", "angelone", "mock")
        config: Broker configuration dict

    Returns:
        BrokerGateway instance

    Raises:
        ValueError: If broker not registered
    """
    gateway_class = _BROKER_REGISTRY.get(name.lower())
    if not gateway_class:
        available = ", ".join(_BROKER_REGISTRY.keys())
        raise ValueError(f"Unknown broker: {name}. Available: {available}")
    return gateway_class(config)


def list_brokers() -> list[str]:
    """List all registered brokers."""
    return list(_BROKER_REGISTRY.keys())
