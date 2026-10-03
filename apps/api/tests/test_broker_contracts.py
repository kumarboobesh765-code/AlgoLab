"""Broker gateway contract tests.

The seven real adapters are registered but were never exercised, so a signature
drift or an unimplemented abstract method would only surface against a live
broker at 9am. These tests hold every registered gateway to the same contract:

- it can be constructed from a config dict
- it implements every abstract method of BrokerGateway
- it reports a broker name and demo/unsupported state sanely
- its error types carry the broker name

They run offline with no credentials and no network: construction and metadata
must not require a session.
"""

import inspect

import pytest

from app.execution import _BROKER_REGISTRY, get_broker_gateway, list_brokers
from app.execution.gateway import BrokerGateway

REAL_BROKERS = [
    name for name in list_brokers() if name not in ("mock",)
]

# Every abstract method of BrokerGateway. Derived from the ABC rather than
# hardcoded, so adding a method to the interface automatically extends the
# contract instead of silently going untested.
REQUIRED_METHODS = sorted(BrokerGateway.__abstractmethods__)


# --- registry ---------------------------------------------------------------


def test_registry_has_the_expected_brokers():
    names = set(list_brokers())
    assert {
        "mock", "zerodha", "upstox", "angelone", "dhan", "fyers", "icici", "5paisa"
    } <= names


def test_seven_real_brokers_registered():
    assert len(REAL_BROKERS) == 7


def test_unknown_broker_raises_with_available_list():
    with pytest.raises(ValueError) as exc:
        get_broker_gateway("not_a_broker", {})
    # The error should help a user fix a typo, not just say no.
    for name in list_brokers():
        assert name in str(exc.value)


def test_broker_lookup_is_case_insensitive():
    assert isinstance(get_broker_gateway("ZERODHA", {}), BrokerGateway)


def test_contract_covers_the_whole_interface():
    """If this drifts from the ABC the rest of the file stops proving anything."""
    assert "place_order" in REQUIRED_METHODS
    assert "get_option_chain" in REQUIRED_METHODS
    assert len(REQUIRED_METHODS) >= 20


def test_register_broker_is_additive():
    """A new adapter must be pluggable without editing the registry."""

    class Custom(BrokerGateway):
        def __init__(self, config):
            self.name = "custom"

        async def connect(self):
            return True

        async def disconnect(self):
            return True

        async def is_connected(self):
            return True

        async def get_profile(self):
            return {}

        async def get_funds(self):
            return None

        async def get_margin(self):
            return None

        async def get_positions(self):
            return []

        async def get_holdings(self):
            return []

        async def get_orders(self):
            return []

        async def get_order_history(self, order_id):
            return []

        async def get_trades(self, from_date=None, to_date=None):
            return []

        async def place_order(self, request):
            return None

        async def modify_order(self, order_id, quantity=None, price=None):
            return None

        async def cancel_order(self, order_id):
            return None

        async def get_instruments(self, exchange=None):
            return []

        async def search_instruments(self, query, exchange=None):
            return []

        async def get_quote(self, instruments):
            return {}

        async def get_ohlc(self, instruments):
            return {}

        async def get_historical_data(self, instrument, interval, start, end):
            return []

        async def get_option_chain(self, underlying, expiry=None):
            return {}

    from app.execution import register_broker

    register_broker("contract-test-temp", Custom)
    try:
        assert "contract-test-temp" in list_brokers()
        assert isinstance(get_broker_gateway("contract-test-temp", {}), Custom)
    finally:
        _BROKER_REGISTRY.pop("contract-test-temp", None)


# --- contract ---------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_BROKER_REGISTRY))
def test_gateway_constructs_without_credentials(name):
    """Construction must not require a live session or throw on empty config."""
    gw = get_broker_gateway(name, {})
    assert gw is not None
    assert isinstance(getattr(gw, "name", None), str)
    assert gw.name


@pytest.mark.parametrize("name", sorted(_BROKER_REGISTRY))
def test_no_unimplemented_abstract_methods(name):
    """A broker left half-implemented must fail here, not at order time."""
    cls = _BROKER_REGISTRY[name]
    assert not inspect.isabstract(cls), f"{name} still has abstract methods"
    missing = getattr(cls, "__abstractmethods__", frozenset())
    assert not missing, f"{name} missing: {sorted(missing)}"


@pytest.mark.parametrize("name", sorted(_BROKER_REGISTRY))
def test_required_methods_exist(name):
    cls = _BROKER_REGISTRY[name]
    for method in REQUIRED_METHODS:
        assert hasattr(cls, method), f"{name} lacks {method}"
        assert callable(getattr(cls, method)), f"{name}.{method} not callable"


@pytest.mark.parametrize("name", sorted(_BROKER_REGISTRY))
def test_required_methods_are_async(name):
    """A sync place_order would silently return a coroutine to every caller."""
    cls = _BROKER_REGISTRY[name]
    for method in REQUIRED_METHODS:
        fn = getattr(cls, method)
        assert inspect.iscoroutinefunction(fn), f"{name}.{method} must be async"


@pytest.mark.parametrize("name", sorted(_BROKER_REGISTRY))
def test_optional_composite_helpers_present(name):
    """Basket/OCO/bracket and streaming are part of the platform surface."""
    cls = _BROKER_REGISTRY[name]
    for method in (
        "place_basket_order",
        "place_oco_order",
        "place_bracket_order",
        "get_margins",
        "subscribe_ticks",
        "unsubscribe_ticks",
        "subscribe_order_updates",
    ):
        assert hasattr(cls, method), f"{name} lacks {method}"


# --- error contract ---------------------------------------------------------


def test_broker_errors_carry_the_broker_name():
    from app.execution.gateway import (
        AuthenticationError,
        BrokerError,
        InsufficientMarginError,
        OrderRejectedError,
        RateLimitError,
    )

    err = BrokerError("E42", "bad request", "zerodha")
    assert "zerodha" in str(err)
    assert err.broker == "zerodha"
    assert err.code == "E42"

    for cls in (
        AuthenticationError,
        RateLimitError,
        InsufficientMarginError,
        OrderRejectedError,
    ):
        # Subclasses inherit BrokerError's (code, message, broker) signature,
        # which is how every adapter raises them.
        exc = cls("E1", "something went wrong", "dhan")
        assert isinstance(exc, BrokerError), f"{cls.__name__} must extend BrokerError"
        assert "dhan" in str(exc), f"{cls.__name__} lost the broker name"
        assert exc.broker == "dhan"


def test_mock_gateway_is_demo():
    """Live trading must be gated on the demo flag, so it must be trustworthy."""
    from app.execution.gateway import MockGateway

    gw = MockGateway({})
    assert getattr(gw, "is_demo", False) is True


@pytest.mark.asyncio
async def test_mock_gateway_order_lifecycle():
    """The reference implementation the other adapters are compared against."""
    from app.execution.gateway import (
        Exchange,
        MockGateway,
        OrderRequest,
        OrderSide,
        OrderType,
        Segment,
    )

    gw = MockGateway({})
    assert await gw.connect() is True

    req = OrderRequest(
        symbol="NIFTY",
        exchange=Exchange.NSE,
        segment=Segment.EQUITY,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
    )
    placed = await gw.place_order(req)
    assert placed is not None
    assert placed.order_id

    assert await gw.get_orders() is not None
    assert await gw.get_positions() is not None
    assert await gw.get_funds() is not None

    cancelled = await gw.cancel_order(placed.order_id)
    assert cancelled is not None
