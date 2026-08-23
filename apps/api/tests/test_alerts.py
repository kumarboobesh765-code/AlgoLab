"""Tests for the alerts service (Telegram + generic webhook, best-effort)."""

import asyncio
from types import SimpleNamespace

from app.services import alerts


def _fake_settings(**overrides) -> SimpleNamespace:
    defaults = {
        "TELEGRAM_BOT_TOKEN": None,
        "TELEGRAM_CHAT_ID": None,
        "ALERT_WEBHOOK_URL": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


class FakeClient:
    calls: list[tuple[str, dict]] = []
    fail_urls: tuple[str, ...] = ()

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url: str, json=None):
        FakeClient.calls.append((url, json or {}))
        if url.startswith(FakeClient.fail_urls):
            raise RuntimeError("connection refused")
        return FakeResponse()


async def test_noop_without_channels(monkeypatch):
    monkeypatch.setattr(alerts, "get_settings", lambda: _fake_settings())
    assert await alerts.notify("hello") is False


async def test_webhook_success(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(alerts, "get_settings", lambda: _fake_settings(ALERT_WEBHOOK_URL="https://hooks.example/x"))
    monkeypatch.setattr(alerts.httpx, "AsyncClient", FakeClient)

    assert await alerts.notify("fill happened") is True
    assert FakeClient.calls[0][0] == "https://hooks.example/x"
    assert FakeClient.calls[0][1] == {"text": "fill happened"}


async def test_telegram_channel(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: _fake_settings(TELEGRAM_BOT_TOKEN="TOK", TELEGRAM_CHAT_ID="42"),
    )
    monkeypatch.setattr(alerts.httpx, "AsyncClient", FakeClient)

    assert await alerts.notify("signal!") is True
    url, payload = FakeClient.calls[0]
    assert "botTOK/sendMessage" in url
    assert payload == {"chat_id": "42", "text": "signal!"}


async def test_failure_is_swallowed_not_raised(monkeypatch):
    FakeClient.calls = []
    FakeClient.fail_urls = ("https://hooks.example/",)
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: _fake_settings(
            ALERT_WEBHOOK_URL="https://hooks.example/dead",
            TELEGRAM_BOT_TOKEN="TOK",
            TELEGRAM_CHAT_ID="42",
        ),
    )
    monkeypatch.setattr(alerts.httpx, "AsyncClient", FakeClient)

    # webhook fails, telegram succeeds -> still reports success
    assert await alerts.notify("mixed") is True
    assert len(FakeClient.calls) == 2

    # both fail -> returns False without raising
    FakeClient.fail_urls = ("https://hooks.example/", "https://api.telegram.org/")
    FakeClient.calls = []
    assert await alerts.notify("all dead") is False


async def test_notify_async_schedules_background_task(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(alerts, "get_settings", lambda: _fake_settings(ALERT_WEBHOOK_URL="https://hooks.example/y"))
    monkeypatch.setattr(alerts.httpx, "AsyncClient", FakeClient)

    alerts.notify_async("background")
    await asyncio.sleep(0.05)
    assert FakeClient.calls and FakeClient.calls[0][1] == {"text": "background"}
