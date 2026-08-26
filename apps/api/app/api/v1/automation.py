"""Automation loop endpoints — signal evaluation routed into the execution layer."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.services.automation import (
    AutomationError,
    get_automation,
    list_automations,
    run_once,
    start_automation,
    stop_automation,
)

router = APIRouter(prefix="/automation", tags=["automation"])


class AutomationStart(BaseModel):
    strategy_id: uuid.UUID
    broker: str = Field(default="mock", max_length=30)
    mode: str = Field(default="paper", pattern="^(paper|confirm|live)$")


class AutomationRunOut(BaseModel):
    started: bool = False
    state: dict | None = None
    run: dict | None = None


@router.get("")
async def list_all(user: CurrentUser) -> list[dict]:
    return [s.as_dict() for s in list_automations(user.email)]


@router.post("/start")
async def start(payload: AutomationStart, user: CurrentUser):
    try:
        st = start_automation(user.email, payload.strategy_id, broker=payload.broker, mode=payload.mode)
    except AutomationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"started": True, "state": st.as_dict()}


@router.post("/{strategy_id}/stop")
async def stop(strategy_id: uuid.UUID, user: CurrentUser):
    ok = stop_automation(user.email, str(strategy_id))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No automation for that strategy")
    return {"stopped": True}


@router.post("/{strategy_id}/run-once")
async def run_once_endpoint(strategy_id: uuid.UUID, db: DbSession, user: CurrentUser):
    if get_automation(user.email, str(strategy_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Automation not started for this strategy")
    try:
        result = await run_once(db, user.email, strategy_id)
    except AutomationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    st = get_automation(user.email, str(strategy_id))
    return {**result, "state": st.as_dict() if st else None}
