import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class IngestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=100)
    interval: str = Field(default="5m")
    start: date
    end: date


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    security_id: str
    exchange: str
    segment: str
    exchange_segment: str | None
    symbol: str
    name: str | None
    underlying: str | None
    instrument_type: str | None
    expiry_code: int | None
    expiry: date | None
    strike: float | None
    option_type: str | None
    lot_size: int
    tick_size: float
    status: str
