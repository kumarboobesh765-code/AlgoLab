"""Execution algorithms (parent/child order scheduling).

These algorithms split a large parent order into smaller child slices that
are released over time to reduce market impact. The scheduler is *pure*: it
produces a deterministic list of slices given the inputs, so it is fully
unit-testable. The Order Management System is responsible for releasing the
slices whose scheduled time has arrived.

Supported strategies:
- TWAP: equal-quantity slices released at equal time intervals.
- VWAP: quantity weighted by a volume profile across the interval.
- TRANCHE: a fixed number of equal tranches with small time jitter.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.execution.gateway import OrderRequest, OrderSide, OrderType


class ExecutionAlgo(StrEnum):
    TWAP = "TWAP"
    VWAP = "VWAP"
    TRANCHE = "TRANCHE"
    MARKET = "MARKET"


@dataclass
class OrderSlice:
    """A single child order produced by an execution algorithm."""

    slice_id: str
    scheduled_time: datetime
    quantity: int
    side: OrderSide
    order_type: OrderType
    price: float = 0.0
    trigger_price: float = 0.0
    tag: str = ""
    sent: bool = False


def _distribute(total: int, weights: list[float]) -> list[int]:
    """Split `total` quantity across `weights` proportionally, preserving sum."""
    if not weights or total <= 0:
        return [0] * len(weights)
    wsum = sum(weights)
    if wsum <= 0:
        weights = [1.0] * len(weights)
        wsum = sum(weights)
    raw = [total * w / wsum for w in weights]
    floored = [int(math.floor(x)) for x in raw]
    remainder = total - sum(floored)
    # Assign the leftover to the largest fractional parts
    fracs = sorted(
        range(len(raw)),
        key=lambda i: raw[i] - floored[i],
        reverse=True,
    )
    for i in range(remainder):
        floored[fracs[i % len(fracs)]] += 1
    return floored


def _twap_times(start: datetime, end: datetime, n: int) -> list[datetime]:
    if n <= 1:
        return [start]
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


def _validate_window(start: datetime, end: datetime, n: int) -> None:
    if end <= start:
        raise ValueError("end must be after start")
    if n < 1:
        raise ValueError("slice count must be >= 1")


def build_schedule(
    algo: ExecutionAlgo,
    request: OrderRequest,
    start: datetime,
    end: datetime,
    slices: int = 10,
    volume_profile: list[float] | None = None,
    jitter_seconds: int = 0,
    parent_tag: str = "",
) -> list[OrderSlice]:
    """Build a deterministic schedule of child slices for a parent order.

    Args:
        algo: Execution algorithm to use.
        request: The parent order request.
        start: First slice release time.
        end: Last slice release time.
        slices: Number of child slices (ignored for MARKET which emits one).
        volume_profile: Per-slice volume weights for VWAP (length must equal `slices`).
        jitter_seconds: Random +/- jitter applied to each slice time (TRANCHE only).
        parent_tag: Tag propagated to child slices.

    Returns:
        Ordered list of :class:`OrderSlice` (earliest first).
    """
    if algo == ExecutionAlgo.MARKET:
        return [
            OrderSlice(
                slice_id=uuid.uuid4().hex[:12],
                scheduled_time=start,
                quantity=request.quantity,
                side=request.side,
                order_type=request.order_type,
                price=request.price,
                trigger_price=request.trigger_price,
                tag=parent_tag,
            )
        ]

    _validate_window(start, end, slices)

    if algo == ExecutionAlgo.VWAP:
        if volume_profile is not None:
            if len(volume_profile) != slices:
                raise ValueError("volume_profile length must equal slice count")
            weights = list(volume_profile)
        else:
            # Default to a mild U-shaped intraday profile when none supplied
            weights = [1.0 + abs(math.sin(math.pi * (i + 0.5) / slices)) for i in range(slices)]
    else:
        weights = [1.0] * slices

    quantities = _distribute(request.quantity, weights)
    times = _twap_times(start, end, slices)

    out: list[OrderSlice] = []
    rng = _seeded_rng(abs(jitter_seconds))
    for i in range(slices):
        qty = quantities[i]
        if qty <= 0:
            continue
        t = times[i]
        if algo == ExecutionAlgo.TRANCHE and jitter_seconds:
            offset = int((rng.random() * 2 - 1) * jitter_seconds)
            t = t + timedelta(seconds=offset)
        out.append(
            OrderSlice(
                slice_id=uuid.uuid4().hex[:12],
                scheduled_time=t,
                quantity=qty,
                side=request.side,
                order_type=request.order_type,
                price=request.price,
                trigger_price=request.trigger_price,
                tag=f"{parent_tag}:{i+1}/{slices}",
            )
        )
    return out


def pending_slices(schedule: list[OrderSlice], now: datetime) -> list[OrderSlice]:
    """Return slices not yet sent whose scheduled time has arrived."""
    return [s for s in schedule if not s.sent and s.scheduled_time <= now]


def _seeded_rng(seed: int):
    import random

    return random.Random(seed)
