"""OHLCV candle tables.

Four identical tables per spec §35 (index/equity/futures/options candles).
On PostgreSQL+TimescaleDB they become hypertables on `time` (see migration
0002); on SQLite dev they are plain tables. Timestamps are stored timezone-aware,
normalized to UTC before insert.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _build_candle_model(table_name: str, class_name: str) -> type[Any]:
    annotations: dict[str, Any] = {
        "instrument_id": Mapped[str],
        "interval": Mapped[str],
        "time": Mapped[datetime],
        "open": Mapped[float],
        "high": Mapped[float],
        "low": Mapped[float],
        "close": Mapped[float],
        "volume": Mapped[int],
        "oi": Mapped[int | None],
    }
    attrs: dict[str, Any] = {
        "__tablename__": table_name,
        "__annotations__": annotations,
        "instrument_id": mapped_column(String(50), primary_key=True),
        "interval": mapped_column(String(5), primary_key=True),
        "time": mapped_column(DateTime(timezone=True), primary_key=True),
        "open": mapped_column(Float, nullable=False),
        "high": mapped_column(Float, nullable=False),
        "low": mapped_column(Float, nullable=False),
        "close": mapped_column(Float, nullable=False),
        "volume": mapped_column(BigInteger, default=0),
        "oi": mapped_column(BigInteger, nullable=True),
    }
    return type(class_name, (Base,), attrs)


IndexCandle = _build_candle_model("index_candles", "IndexCandle")
EquityCandle = _build_candle_model("equity_candles", "EquityCandle")
FuturesCandle = _build_candle_model("futures_candles", "FuturesCandle")
OptionsCandle = _build_candle_model("options_candles", "OptionsCandle")

CANDLE_MODELS_BY_SEGMENT: dict[str, Any] = {
    "index": IndexCandle,
    "equity": EquityCandle,
    "futures": FuturesCandle,
    "options": OptionsCandle,
}
