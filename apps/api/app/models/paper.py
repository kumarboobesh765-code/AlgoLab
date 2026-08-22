import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaperAccount(Base):
    """Virtual (paper) trading account. Never connected to real money."""

    __tablename__ = "paper_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperPosition(Base):
    """A virtual position opened by a forward test (or manually later)."""

    __tablename__ = "paper_positions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # long | short
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    trail_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    trailed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # bool
    extreme: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))  # trailing anchor
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False, index=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(String(20))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperOrder(Base):
    """Immutable record of every virtual fill."""

    __tablename__ = "paper_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("strategies.id", ondelete="SET NULL"), index=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    side: Mapped[str] = mapped_column(String(5), nullable=False)  # BUY | SELL
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    filled_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)  # entry | exit_signal | ...
    signal_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ForwardTestRun(Base):
    """A strategy running against a paper account on live-ingested candles."""

    __tablename__ = "forward_test_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False, index=True)
    # Idempotency: ticks only process candles strictly after this bar.
    last_bar_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Carried signal: decided at the last processed bar's close, filled at the next bar's open.
    pending_action: Mapped[str | None] = mapped_column(String(12))  # entry_long | entry_short | exit
    last_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
