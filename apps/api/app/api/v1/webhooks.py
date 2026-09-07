"""Webhook endpoints — inbound receivers (public) + CRUD (authed)."""

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import Strategy, WebhookDelivery, WebhookEndpoint
from app.schemas.webhook import (
    WebhookDeliveryLog,
    WebhookEndpointCreate,
    WebhookEndpointCreatedOut,
    WebhookEndpointOut,
    WebhookEndpointUpdate,
)
from app.services.webhook_processor import (
    generate_secret,
    generate_slug,
    process_webhook,
    verify_signature,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _endpoint_out(endpoint: WebhookEndpoint, base_url: str | None = None) -> WebhookEndpointOut:
    return WebhookEndpointOut.model_validate(
        {
            "id": str(endpoint.id),
            "user_id": str(endpoint.user_id),
            "strategy_id": str(endpoint.strategy_id) if endpoint.strategy_id else None,
            "provider": endpoint.provider,
            "slug": endpoint.slug,
            "name": endpoint.name,
            "active": endpoint.active,
            "created_at": endpoint.created_at.isoformat() if endpoint.created_at else "",
        }
    )


def _created_out(endpoint: WebhookEndpoint, base_url: str) -> WebhookEndpointCreatedOut:
    base = _endpoint_out(endpoint).model_dump()
    base["secret"] = endpoint.secret
    base["webhook_url"] = f"{base_url.rstrip('/')}/api/v1/webhooks/{endpoint.slug}"
    return WebhookEndpointCreatedOut.model_validate(base)


def _delivery_out(row: WebhookDelivery) -> WebhookDeliveryLog:
    return WebhookDeliveryLog.model_validate(
        {
            "id": str(row.id),
            "endpoint_id": str(row.endpoint_id),
            "received_at": row.received_at.isoformat() if row.received_at else "",
            "action": row.action,
            "status": row.status,
            "response": row.response,
        }
    )


async def _owned_endpoint(
    db: DbSession, current_user: CurrentUser, endpoint_id: uuid.UUID
) -> WebhookEndpoint:
    endpoint = (
        (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.id == endpoint_id,
                    WebhookEndpoint.user_id == current_user.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook endpoint not found")
    return endpoint


# ---------------------------------------------------------------------------
# public inbound receiver (no auth)
# ---------------------------------------------------------------------------

@router.post("/{slug}")
async def receive_webhook(slug: str, request: Request, db: DbSession) -> dict:
    endpoint = (
        (
            await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.slug == slug))
        )
        .scalars()
        .first()
    )
    if endpoint is None or not endpoint.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")

    body = await request.body()
    signature_header = (
        request.headers.get("x-tv-signature")
        or request.headers.get("x-chartink-signature")
        or request.headers.get("x-signature")
        or ""
    )
    if signature_header:
        # Constant-time compare; reject the request if it doesn't match.
        if not verify_signature(endpoint.secret, body, signature_header):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {"raw": payload}
    except Exception:  # noqa: BLE001 — accept arbitrary bodies, log them as text
        try:
            payload = {"raw": body.decode("utf-8", errors="replace")}
        except Exception:  # noqa: BLE001
            payload = {"raw": ""}

    return await process_webhook(db, endpoint, payload)


# ---------------------------------------------------------------------------
# authed CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[WebhookEndpointOut])
async def list_webhooks(db: DbSession, current_user: CurrentUser) -> list[WebhookEndpointOut]:
    rows = (
        (
            await db.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.user_id == current_user.id)
                .order_by(WebhookEndpoint.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_endpoint_out(r) for r in rows]


@router.post(
    "",
    response_model=WebhookEndpointCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    payload: WebhookEndpointCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> WebhookEndpointCreatedOut:
    if payload.strategy_id is not None:
        strategy = await db.get(Strategy, payload.strategy_id)
        if strategy is None or strategy.user_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")

    endpoint = WebhookEndpoint(
        user_id=current_user.id,
        strategy_id=payload.strategy_id,
        provider=payload.provider,
        slug=generate_slug(payload.provider),
        secret=generate_secret(),
        name=payload.name,
        active=True,
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return _created_out(endpoint, str(request.base_url))


@router.get("/{endpoint_id}", response_model=WebhookEndpointOut)
async def get_webhook(
    endpoint_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WebhookEndpointOut:
    return _endpoint_out(await _owned_endpoint(db, current_user, endpoint_id))


@router.patch("/{endpoint_id}", response_model=WebhookEndpointOut)
async def update_webhook(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> WebhookEndpointOut:
    endpoint = await _owned_endpoint(db, current_user, endpoint_id)

    if payload.strategy_id is not None:
        strategy = await db.get(Strategy, payload.strategy_id)
        if strategy is None or strategy.user_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
        endpoint.strategy_id = payload.strategy_id

    if payload.name is not None:
        endpoint.name = payload.name
    if payload.active is not None:
        endpoint.active = payload.active

    await db.commit()
    await db.refresh(endpoint)
    return _endpoint_out(endpoint)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    endpoint_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    endpoint = await _owned_endpoint(db, current_user, endpoint_id)
    await db.delete(endpoint)
    await db.commit()


@router.get("/{endpoint_id}/logs", response_model=list[WebhookDeliveryLog])
async def list_webhook_logs(
    endpoint_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 50,
) -> list[WebhookDeliveryLog]:
    endpoint = await _owned_endpoint(db, current_user, endpoint_id)
    rows = (
        (
            await db.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.endpoint_id == endpoint.id)
                .order_by(WebhookDelivery.received_at.desc())
                .limit(max(1, min(limit, 200)))
            )
        )
        .scalars()
        .all()
    )
    return [_delivery_out(r) for r in rows]
