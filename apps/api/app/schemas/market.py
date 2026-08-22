from datetime import datetime

from pydantic import BaseModel


class CandleOut(BaseModel):
    timestamp: datetime
    instrument_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    oi: float | None = None


class InstrumentOut(BaseModel):
    symbol: str
    name: str
    exchange: str
    segment: str  # index | equity | futures | options
    base_price: float
    lot_size: int
    strike_step: int


class OptionChainRow(BaseModel):
    strike: int
    call_ltp: float
    put_ltp: float
    call_iv: float
    put_iv: float
    call_oi: float
    put_oi: float
    call_volume: float
    put_volume: float
    call_delta: float
    put_delta: float


class OptionChainOut(BaseModel):
    underlying: str
    spot: float
    expiry: str
    strikes: list[OptionChainRow]
    provider: str
    is_demo: bool
