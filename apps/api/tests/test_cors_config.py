"""CORS origin configuration.

CORS_ORIGINS was a list[str] field with a single hardcoded localhost entry.
Pydantic-settings parses list fields from JSON, so operators setting a plain
comma-separated value in .env hit a startup parse error, and the default silently
refused every origin except localhost:3000. Running the web app on any other
port - or a LAN address - failed every API call with no useful signal.

Now it is a comma-separated string parsed by a property, matching the existing
EXECUTION_IP_WHITELIST pattern, and the effective list is reported by /health.
"""

import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


# --- parsing ----------------------------------------------------------------


def test_default_includes_both_localhost_forms():
    """127.0.0.1 and localhost are different origins to a browser."""
    origins = _settings().cors_origins
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_comma_separated_values_are_split():
    settings = _settings(CORS_ORIGINS="http://localhost:3000,http://10.0.0.5:3000")
    assert settings.cors_origins == ["http://localhost:3000", "http://10.0.0.5:3000"]


def test_whitespace_is_trimmed():
    settings = _settings(CORS_ORIGINS=" http://a.test , http://b.test ")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_blank_entries_are_dropped():
    settings = _settings(CORS_ORIGINS="http://a.test, ,http://b.test,")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_single_origin_yields_single_entry():
    assert _settings(CORS_ORIGINS="https://app.example.com").cors_origins == [
        "https://app.example.com"
    ]


def test_plain_string_does_not_crash_startup():
    """The regression: a bare comma-separated value used to fail to parse."""
    settings = _settings(CORS_ORIGINS="http://localhost:3000,http://localhost:3100")
    assert len(settings.cors_origins) == 2


def test_multiple_origins_are_all_returned():
    """The other half of the gap: only one origin used to be permitted."""
    value = ",".join(f"http://host{i}:3000" for i in range(5))
    assert len(_settings(CORS_ORIGINS=value).cors_origins) == 5


# --- integration ------------------------------------------------------------


def test_health_reports_the_effective_origins():
    """So a browser CORS failure can be diagnosed without reading API config."""
    import asyncio

    from app.api.v1 import health as health_mod

    health_mod._last_db_check = 0.0
    health_mod._db_ok = True

    class _S:
        async def execute(self, stmt):
            class R:
                def scalar(self):
                    return 1

            return R()

    result = asyncio.run(health_mod.health(_S()))
    assert isinstance(result["allowed_origins"], list)
    assert result["allowed_origins"]


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_default_origins_are_the_usual_local_dev_servers(origin):
    assert origin in _settings().cors_origins
