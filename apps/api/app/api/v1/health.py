import time

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.deps import DbSession, get_provider_instance
from app.marketdata.base import ProviderError

router = APIRouter(tags=["system"])

# The database check is cached for a few seconds. /health is polled on every app
# mount - and twice per mount under React StrictMode - so an unconditional
# SELECT 1 put a database round trip in front of every page load for a value
# that cannot meaningfully change faster than this.
_DB_CHECK_INTERVAL_SECONDS = 5.0
_last_db_check = 0.0
_db_ok = True


@router.get("/health")
async def health(db: DbSession) -> dict:
    """Liveness/readiness probe. Reports infra + provider status honestly."""
    global _last_db_check, _db_ok

    settings = get_settings()

    now = time.monotonic()
    if now - _last_db_check > _DB_CHECK_INTERVAL_SECONDS:
        _last_db_check = now
        try:
            await db.execute(text("SELECT 1"))
            _db_ok = True
        except Exception:
            _db_ok = False
    database_status = "ok" if _db_ok else "error"

    provider_configured = True
    provider_name = settings.MARKET_DATA_PROVIDER
    is_demo = provider_name == "demo"
    try:
        provider = get_provider_instance()
        provider_name = provider.name
        is_demo = provider.is_demo
    except ProviderError:
        provider_configured = False

    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "database": database_status,
        "auth_enabled": settings.AUTH_ENABLED,
        "market_data_provider": provider_name,
        "market_data_is_demo": is_demo,
        "market_data_provider_configured": provider_configured,
        # Surfaced so a CORS failure is diagnosable from the browser console
        # rather than requiring someone to read the API's config.
        "allowed_origins": settings.cors_origins,
        "trading_mode": "paper_only",
        "live_trading_available": False,
    }
