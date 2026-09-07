import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WebhookEndpointCreate(BaseModel):
    strategy_id: uuid.UUID | None = None
    provider: Literal["tradingview", "chartink"]
    name: str = Field(min_length=1, max_length=200)


class WebhookEndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None
    strategy_id: uuid.UUID | None = None


class WebhookEndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    strategy_id: uuid.UUID | None
    provider: str
    slug: str
    name: str
    active: bool
    created_at: str


class WebhookEndpointCreatedOut(WebhookEndpointOut):
    secret: str
    webhook_url: str


class WebhookDeliveryLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    received_at: str
    action: str | None
    status: str
    response: str | None


class TradingViewPayload(BaseModel):
    ticker: str
    action: str
    price: float | None = None
    quantity: int | None = None
    comment: str | None = None


class ChartinkPayload(BaseModel):
    symbol: str
    signal_type: str
    price: float | None = None
    scanner_name: str | None = None
