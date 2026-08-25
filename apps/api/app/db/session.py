from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_session_factory = None


def normalize_database_url(url: str) -> str:
    """Translate libpq-style PostgreSQL URLs for SQLAlchemy's asyncpg dialect.

    Accepts ``postgresql://...?sslmode=require&channel_binding=require`` (the
    format Neon/Supabase hand out) and converts it to
    ``postgresql+asyncpg://...`` with asyncpg-compatible connect args.
    Non-postgres URLs (e.g. SQLite) pass through untouched.
    """
    if not url.startswith("postgresql://"):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    # libpq-only knob; asyncpg negotiates channel binding automatically.
    query.pop("channel_binding", None)
    query.pop("ssl", None)
    if sslmode and sslmode != "prefer":
        query["ssl"] = sslmode
    # Pooled endpoints sit behind PgBouncer transaction pooling — server-side
    # prepared statements must be disabled or connections go stale.
    if "-pooler." in (parts.hostname or ""):
        query["prepared_statement_cache_size"] = "0"
    return urlunsplit(
        ("postgresql+asyncpg", parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            normalize_database_url(get_settings().DATABASE_URL),
            future=True,
            pool_pre_ping=True,  # cloud DBs drop idle connections
        )
    return _engine


def reset_engine():
    """Drop cached engine/session factory (used after settings changes, in tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db():
    """FastAPI dependency yielding an async database session."""
    async with get_session_factory()() as session:
        yield session
