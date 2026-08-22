import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

STRATEGY_TYPES = ("intraday", "btst", "positional")
STRATEGY_STATUSES = ("draft", "backtested", "paper_ready", "running", "paused", "stopped", "archived")


class StrategyBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    exchange: str = "NSE"
    underlying: str = "NIFTY"
    instrument: str = "options"
    strategy_type: str = "intraday"
    tags: list[str] = Field(default_factory=list)


class StrategyCreate(StrategyBase):
    definition: dict[str, Any] | None = None


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    exchange: str | None = None
    underlying: str | None = None
    instrument: str | None = None
    strategy_type: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    definition: dict[str, Any] | None = None


class StrategyOut(StrategyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    current_version: int
    definition: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    version_number: int
    definition: dict[str, Any] | None
    changelog: str | None
    created_at: datetime


class VersionCreate(BaseModel):
    changelog: str | None = None
