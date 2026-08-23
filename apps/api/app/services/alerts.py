"""Outbound notifications: Telegram bot and/or generic webhook.

Both channels are optional; with nothing configured every notify call is a
cheap no-op, so engines can fire alerts unconditionally. Delivery is
best-effort — failures are logged and never raised into trading logic.
"""

import asyncio
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("strategylab.alerts")

_background_tasks: set[asyncio.Task] = set()


async def notify(message: str) -> bool:
    """Send message to every configured channel. True if at least one succeeded."""
    settings = get_settings()
    sent = False

    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if token and chat_id:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message},
                )
            if resp.status_code == 200:
                sent = True
            else:
                logger.warning("Telegram returned %s", resp.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram notification failed: %s", exc)

    webhook = settings.ALERT_WEBHOOK_URL
    if webhook:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(webhook, json={"text": message})
            if resp.status_code < 400:
                sent = True
            else:
                logger.warning("Webhook returned %s", resp.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Webhook notification failed: %s", exc)

    return sent


def notify_async(message: str) -> None:
    """Fire-and-forget notify() safe to call from request handlers."""
    task = asyncio.create_task(notify(message))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
