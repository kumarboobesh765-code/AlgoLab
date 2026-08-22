import importlib

from app.core.config import get_settings
from app.marketdata.base import MarketDataProvider, ProviderError

_PROVIDERS: dict[str, str] = {
    "demo": "app.marketdata.demo:DemoProvider",
    "dhan": "app.marketdata.dhan:DhanProvider",
}


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def get_provider() -> MarketDataProvider:
    """Return the configured market-data provider instance."""
    settings = get_settings()
    target = _PROVIDERS.get(settings.MARKET_DATA_PROVIDER)
    if target is None:
        raise ProviderError(
            f"Unknown MARKET_DATA_PROVIDER '{settings.MARKET_DATA_PROVIDER}'. "
            f"Available: {available_providers()}"
        )
    module_path, class_name = target.split(":")
    provider_cls = getattr(importlib.import_module(module_path), class_name)
    return provider_cls()
