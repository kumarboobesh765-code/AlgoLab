from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.deps import DbSession, get_provider_instance
from app.marketdata.base import ProviderError

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(db: DbSession) -> dict:
    """Liveness/readiness probe. Reports infra + provider status honestly."""
    settings = get_settings()

    database_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

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
        "market_data_provider": provider_name,
        "market_data_is_demo": is_demo,
        "market_data_provider_configured": provider_configured,
        "trading_mode": "paper_only",
        "live_trading_available": False,
    }
