from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "StrategyLab API"
    APP_ENV: str = "development"  # development | production | test

    # PostgreSQL (TimescaleDB) in docker; SQLite fallback for local dev without infra.
    DATABASE_URL: str = "sqlite+aiosqlite:///./strategylab.db"

    REDIS_URL: str | None = None

    JWT_SECRET: str = "dev-insecure-secret-change-me-in-production-0123456789"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # demo until Dhan credentials are configured
    MARKET_DATA_PROVIDER: str = "demo"

    # DhanHQ v2 (Phase 2 adapter)
    DHAN_CLIENT_ID: str | None = None
    DHAN_ACCESS_TOKEN: str | None = None
    DHAN_BASE_URL: str = "https://api.dhan.co/v2"
    DHAN_MASTER_CSV_URL: str = "https://images.dhan.co/api-data/api-scrip-master.csv"
    DHAN_RATE_LIMIT_PER_SEC: float = 4.0

    # Ingestion guards
    INGEST_MAX_DAYS: int = 90

    # Option-chain cache
    OPTION_CHAIN_CACHE_TTL: int = 20

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
