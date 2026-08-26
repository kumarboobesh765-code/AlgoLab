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

    # False (default): single-user local mode — every request maps to a shared
    # local account and the UI never shows the login screen. Set AUTH_ENABLED=true
    # for multi-user deployments (register/login required).
    AUTH_ENABLED: bool = False

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

    # AI Builder: any OpenAI-compatible API. No key -> deterministic rule-based parser.
    AI_API_KEY: str | None = None
    AI_BASE_URL: str = "https://api.openai.com/v1"
    AI_MODEL: str = "gpt-4o-mini"

    # Alerts: Telegram bot and/or generic webhook. Both unset -> notifications disabled.
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    ALERT_WEBHOOK_URL: str | None = None

    # Background scheduler that auto-ticks running forward tests.
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SEC: int = 60

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # SEBI retail-algo framework: broker APIs must only be reachable from
    # static IPs whitelisted with the broker. Comma-separated; empty disables
    # the check (development). Example: "203.0.113.7,198.51.100.42"
    EXECUTION_IP_WHITELIST: str = ""

    @property
    def execution_ip_whitelist(self) -> list[str]:
        return [ip.strip() for ip in self.EXECUTION_IP_WHITELIST.split(",") if ip.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
