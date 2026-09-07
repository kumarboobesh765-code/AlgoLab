"""Process inbound webhooks: parse payloads, find/create a forward test, tick it.

Webhooks are a thin entry point. The expensive work (parsing the provider's
schema, validating the HMAC signature, picking a forward test, running the
paper engine) lives here so that the route handler stays focused on HTTP
plumbing and audit logging.
"""

import hmac
import json
import secrets
import string
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.forward_tests import execute_tick
from app.models import (
    ForwardTestRun,
    PaperAccount,
    Strategy,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.schemas.paper import TickResult

_TRIGGER_ACTIONS = {"buy", "sell", "trigger", "exit", "entry", "long", "short"}


def generate_slug(provider: str) -> str:
    alphabet = string.ascii_letters + string.digits
    rand = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{provider}_{rand}"


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def parse_action(provider: str, payload: dict) -> str:
    if provider == "tradingview":
        raw = str(payload.get("action") or payload.get("side") or "").strip().lower()
    elif provider == "chartink":
        raw = str(payload.get("signal_type") or payload.get("signal") or "").strip().lower()
    else:
        raw = str(payload.get("action") or "").strip().lower()
    if not raw:
        return "unknown"
    if raw in {"buy", "long", "entry", "entry_long", "go_long"}:
        return "buy"
    if raw in {"sell", "short", "exit", "entry_short", "go_short"}:
        return "sell"
    if raw in {"trigger", "alert"}:
        return "trigger"
    return "unknown"


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """HMAC-SHA256 with constant-time compare; TradingView & Chartink compatible."""
    if not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    return hmac.compare_digest(digest, signature.strip().lower())


async def find_or_create_forward_test(
    db: AsyncSession, strategy: Strategy
) -> ForwardTestRun:
    """Return the strategy's running test, creating one if needed.

    Webhook triggers can fire any time — we don't want a missing forward test
    to silently drop the alert. If the user has no running test, spin one up
    against their first active paper account.
    """
    existing = (
        (
            await db.execute(
                select(ForwardTestRun).where(
                    ForwardTestRun.strategy_id == strategy.id,
                    ForwardTestRun.status == "running",
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    account = (
        (
            await db.execute(
                select(PaperAccount)
                .where(PaperAccount.user_id == strategy.user_id, PaperAccount.status == "active")
                .order_by(PaperAccount.created_at.asc())
            )
        )
        .scalars()
        .first()
    )
    if account is None:
        raise ValueError("No active paper account to host the forward test")

    run = ForwardTestRun(
        user_id=strategy.user_id,
        strategy_id=strategy.id,
        account_id=account.id,
        version_number=strategy.current_version,
        status="running",
        last_message="auto-created by webhook",
    )
    strategy.status = "running"
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def process_webhook(
    db: AsyncSession,
    endpoint: WebhookEndpoint,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Parse, dispatch, audit. Always writes a WebhookDelivery row."""
    action = parse_action(endpoint.provider, payload)

    log = WebhookDelivery(
        endpoint_id=endpoint.id,
        payload=json.dumps(payload, default=str),
        action=action,
        status="success",
    )

    if endpoint.strategy_id is None:
        log.status = "skipped"
        log.response = "no strategy bound to this endpoint"
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return {"ok": True, "skipped": True, "message": log.response, "delivery_id": str(log.id)}

    if action not in _TRIGGER_ACTIONS:
        log.status = "skipped"
        log.response = f"action '{action}' is not a trigger; logged but no tick"
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return {"ok": True, "skipped": True, "message": log.response, "delivery_id": str(log.id)}

    strategy = await db.get(Strategy, endpoint.strategy_id)
    if strategy is None or not strategy.definition:
        log.status = "error"
        log.response = "strategy missing or has no definition"
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return {"ok": False, "message": log.response, "delivery_id": str(log.id)}

    try:
        run = await find_or_create_forward_test(db, strategy)
        result: TickResult = await execute_tick(db, run)
    except Exception as exc:  # noqa: BLE001 — record the failure in the audit log
        log.status = "error"
        log.response = f"tick failed: {exc!s}"[:2000]
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return {"ok": False, "message": log.response, "delivery_id": str(log.id)}

    log.forward_test_id = run.id
    log.response = result.message or f"processed {result.bars_processed} bars"
    log.status = "success"
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return {
        "ok": True,
        "action": action,
        "forward_test_id": str(run.id),
        "fills": len(result.fills),
        "bars_processed": result.bars_processed,
        "message": result.message,
        "delivery_id": str(log.id),
    }


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()
