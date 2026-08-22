import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType

# Strategy statuses (Phase 1 foundation): draft -> backtested -> paper_ready -> running/paused/stopped/archived
STRATEGY_STATUSES = ("draft", "backtested", "paper_ready", "running", "paused", "stopped", "archived")


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    exchange: Mapped[str] = mapped_column(String(20), default="NSE", nullable=False)
    underlying: Mapped[str] = mapped_column(String(50), default="NIFTY", nullable=False)
    instrument: Mapped[str] = mapped_column(String(50), default="options", nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(20), default="intraday", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    tags: Mapped[list] = mapped_column(JSONType, default=list)
    # Canonical Strategy Definition JSON (schema ships in Phase 3).
    definition: Mapped[dict | None] = mapped_column(JSONType)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StrategyVersion(Base):
    """Immutable snapshot of a strategy definition at a point in time."""

    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version_number", name="uq_strategy_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict | None] = mapped_column(JSONType)
    changelog: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
