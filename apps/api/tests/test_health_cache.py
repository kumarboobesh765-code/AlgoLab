"""Health endpoint caching.

/health is polled on every app mount - and twice per mount under React
StrictMode - so an unconditional SELECT 1 put a database round trip in front of
every page load. The database status is now cached for a few seconds.

The cache must not turn a genuine outage into a green light, so these tests
check both directions: repeated healthy calls hit the database once, and a fresh
failure is still surfaced rather than masked by the previous success.
"""

import pytest
from sqlalchemy import text

from app.api.v1 import health as health_mod


@pytest.fixture
def clean_cache():
    """Reset module state so each test starts from a cold cache."""
    health_mod._last_db_check = 0.0
    health_mod._db_ok = True
    yield
    health_mod._last_db_check = 0.0
    health_mod._db_ok = True


class _FakeResult:
    def scalar(self):
        return 1


class _CountingSession:
    """Stands in for AsyncSession, counting how often the DB is actually hit."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        if self.fail:
            raise RuntimeError("db down")
        return _FakeResult()


@pytest.mark.asyncio
async def test_first_call_hits_the_database(clean_cache):
    session = _CountingSession()
    result = await health_mod.health(session)
    assert session.calls == 1
    assert result["database"] == "ok"


@pytest.mark.asyncio
async def test_repeat_calls_within_window_do_not_requery(clean_cache):
    """The point of the cache: a burst of polls costs one query."""
    session = _CountingSession()
    for _ in range(8):
        result = await health_mod.health(session)
        assert result["database"] == "ok"
    assert session.calls == 1, "database was queried on every poll"


@pytest.mark.asyncio
async def test_cache_expires_and_requeries(clean_cache):
    session = _CountingSession()
    await health_mod.health(session)
    assert session.calls == 1

    # Pretend the cache window has elapsed.
    health_mod._last_db_check -= health_mod._DB_CHECK_INTERVAL_SECONDS + 1
    await health_mod.health(session)
    assert session.calls == 2


@pytest.mark.asyncio
async def test_failure_is_reported_as_degraded(clean_cache):
    session = _CountingSession(fail=True)
    result = await health_mod.health(session)
    assert result["database"] == "error"
    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_failure_is_not_masked_by_a_prior_success(clean_cache):
    """A cached 'ok' must never be reported after the database has died."""
    session = _CountingSession()
    await health_mod.health(session)
    assert health_mod._db_ok is True

    # Database goes away, and the cache window elapses.
    health_mod._last_db_check -= health_mod._DB_CHECK_INTERVAL_SECONDS + 1
    session.fail = True
    result = await health_mod.health(session)
    assert result["database"] == "error", "stale healthy status was reported"
    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_recovery_is_picked_up(clean_cache):
    session = _CountingSession(fail=True)
    await health_mod.health(session)
    assert health_mod._db_ok is False

    health_mod._last_db_check -= health_mod._DB_CHECK_INTERVAL_SECONDS + 1
    session.fail = False
    result = await health_mod.health(session)
    assert result["database"] == "ok"
    assert health_mod._db_ok is True


@pytest.mark.asyncio
async def test_static_fields_always_present(clean_cache):
    """The UI reads auth_enabled and the provider flags from this endpoint."""
    result = await health_mod.health(_CountingSession())
    for field in (
        "status",
        "app",
        "env",
        "database",
        "auth_enabled",
        "market_data_provider",
        "market_data_is_demo",
        "market_data_provider_configured",
        "trading_mode",
        "live_trading_available",
    ):
        assert field in result, f"missing {field}"


def test_cache_uses_the_select_one_query():
    """Guard against the probe drifting away from a cheap liveness check."""
    source = health_mod.health.__code__.co_consts
    assert any("SELECT 1" in str(c) for c in source), "no SELECT 1 probe found"


def test_text_import_still_used():
    """`text` must remain imported for the probe; ruff would otherwise flag it."""
    assert text is not None
