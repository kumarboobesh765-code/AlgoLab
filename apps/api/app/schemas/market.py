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
    """Provider instrument record.

    Core identity fields are required; everything else varies by adapter
    (demo vs Dhan) so they are optional to keep validation lossless.
    """

    symbol: str
    name: str
    exchange: str
    segment: str  # index | equity | futures | options
    security_id: str | None = None
    exchange_segment: str | None = None
    underlying: str | None = None
    instrument_type: str | None = None
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None
    strike_step: int | None = None
    base_price: float | None = None
    expiry_code: int | None = None
    status: str | None = None


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
