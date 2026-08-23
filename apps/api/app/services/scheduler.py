"""Background scheduler: auto-ticks all running forward tests.

A single asyncio loop started from the FastAPI lifespan. Every interval it
opens a short-lived DB session, finds running forward-test runs and executes
the exact same tick logic as the manual HTTP endpoint. Runs that have no new
stored candles are cheap no-ops (the tick reports 0 bars).

Disabled automatically in tests (APP_ENV=test) and via SCHEDULER_ENABLED.
"""

import asyncio
import logging

from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import ForwardTestRun

logger = logging.getLogger("strategylab.scheduler")

_task: asyncio.Task | None = None


async def _tick_all_running() -> tuple[int, int]:
    """Tick every running forward test. Returns (ticked, processed_bars)."""
    from app.api.v1.forward_tests import execute_tick

    ticked = 0
    bars = 0
    async with get_session_factory()() as db:
        result = await db.execute(
            select(ForwardTestRun).where(ForwardTestRun.status == "running")
        )
        runs = list(result.scalars().all())
        for run in runs:
            try:
                tick = await execute_tick(db, run)
                ticked += 1
                bars += tick.bars_processed
            except Exception as exc:  # noqa: BLE001 - one bad run must not kill the loop
                logger.warning("Auto-tick failed for run %s: %s", run.id, exc)
        await db.commit()
    return ticked, bars


async def _loop() -> None:
    settings = get_settings()
    while True:
        try:
            ticked, bars = await _tick_all_running()
            if ticked or bars:
                logger.info("scheduler: %d run(s) ticked, %d new bar(s)", ticked, bars)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler iteration failed")
        await asyncio.sleep(settings.SCHEDULER_INTERVAL_SEC)


def start_scheduler(app: FastAPI) -> asyncio.Task | None:
    settings = get_settings()
    if not settings.SCHEDULER_ENABLED or settings.APP_ENV == "test":
        return None
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="forward-test-scheduler")
        logger.info(
            "scheduler started — auto-ticking running forward tests every %ss",
            settings.SCHEDULER_INTERVAL_SEC,
        )
    app.state.scheduler_task = _task
    return _task


async def stop_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
