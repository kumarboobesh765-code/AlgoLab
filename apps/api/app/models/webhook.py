import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEndpoint(Base):
    """A user-owned webhook receiver (TradingView, Chartink, ...).

    Each endpoint exposes a public URL ``/api/v1/webhooks/{slug}`` that an
    external alert system (e.g. TradingView alert, Chartink scanner) can
    POST to without authentication. The secret is used to verify HMAC
    signatures when the provider supports it.
    """

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("strategies.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # tradingview | chartink
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebhookDelivery(Base):
    """Audit row for every inbound webhook POST.

    The body is preserved as a JSON string so that debugging tooling can show
    the exact payload even when parsing fails.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True, nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str | None] = mapped_column(String(20))  # buy | sell | trigger | unknown
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | error | skipped
    response: Mapped[str | None] = mapped_column(Text)
    forward_test_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
