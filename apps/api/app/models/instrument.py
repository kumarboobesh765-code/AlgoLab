import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InstrumentMaster(Base):
    """Authoritative internal instrument mapping (spec §34).

    Populated from the active provider's instrument master (Dhan scrip master
    CSV, or the demo index list). `segment` is our normalized kind
    (index/equity/futures/options); `exchange_segment` keeps the provider's raw
    enum (e.g. NSE_FNO, IDX_I) needed for API calls.
    """

    __tablename__ = "instrument_master"
    __table_args__ = (
        UniqueConstraint("exchange", "segment", "security_id", name="uq_instrument_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    security_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    segment: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange_segment: Mapped[str | None] = mapped_column(String(20))
    symbol: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    underlying: Mapped[str | None] = mapped_column(String(100), index=True)
    instrument_type: Mapped[str | None] = mapped_column(String(20))
    expiry_code: Mapped[int | None] = mapped_column(Integer)
    expiry: Mapped[date | None] = mapped_column(Date, index=True)
    strike: Mapped[float | None] = mapped_column(Float)
    option_type: Mapped[str | None] = mapped_column(String(4))
    lot_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tick_size: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
