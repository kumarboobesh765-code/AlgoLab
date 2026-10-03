"""WebSocket market-data streaming.

Clients subscribe over a single socket and receive JSON tick frames:

    -> {"action": "subscribe",   "symbols": ["NIFTY"], "interval": "1m"}
    <- {"type": "tick", "instrument_id": "NIFTY", "last_price": 23860.12,
        "candle": {"time": 1770000000, "open":..., "high":..., "low":...,
                   "close":..., "volume":...}}
    <- {"type": "subscribed", "symbols": [...], "provider": "demo", "is_demo": true}
    <- {"type": "error", "message": "..."}

Subscription is reference-free: a client owns only its own socket, so two
browsers watching NIFTY never share a task and one disconnecting cannot tear
down the other's stream. Providers without a live feed raise
NotImplementedError and the socket says so once rather than dropping silently.
"""

import asyncio
import contextlib
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.marketdata.factory import get_provider

router = APIRouter(tags=["stream"])

# Bound a single fan-out so one client's flood cannot grow memory unbounded.
MAX_SYMBOLS = 20
MAX_QUEUE = 256


def _token_from(websocket: WebSocket) -> str | None:
    """Pull a bearer token from the handshake.

    Browsers cannot set headers on a WebSocket, so the token may arrive either as
    a query parameter or in the Authorization header (which non-browser clients
    and the MCP layer do send).
    """
    header = websocket.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return websocket.query_params.get("token")


def _authorised(websocket: WebSocket) -> bool:
    """Whether this socket may open, matching the REST auth convention.

    When AUTH_ENABLED is false the whole platform runs unauthenticated for local
    research, and the socket follows that setting rather than inventing a
    stricter rule the REST API does not enforce. When auth is on, an invalid or
    missing token closes the socket instead of streaming anonymously.
    """
    if not get_settings().AUTH_ENABLED:
        return True
    token = _token_from(websocket)
    if not token:
        return False
    subject = decode_access_token(token)
    if subject is None:
        return False
    try:
        uuid.UUID(subject)
    except ValueError:
        return False
    return True


def _tick_payload(tick) -> dict:
    c = tick.candle
    return {
        "type": "tick",
        "instrument_id": tick.instrument_id,
        "last_price": tick.last_price,
        "ts": tick.timestamp.isoformat(),
        "candle": {
            "time": int(c.timestamp.timestamp()),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        },
    }


@router.websocket("/ws/market")
async def market_stream(websocket: WebSocket) -> None:
    # Reject before accept so the handshake fails outright rather than opening a
    # socket that then silently refuses to send anything.
    if not _authorised(websocket):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    provider = get_provider()

    queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
    task: asyncio.Task | None = None
    sender: asyncio.Task | None = None
    symbols: list[str] = []
    interval = "1m"

    async def pump() -> None:
        """Drain the provider stream into the queue, dropping on overflow.

        A slow client must not stall the provider, so when the queue is full we
        discard the oldest frame: stale prices are worse than a gap, and the
        candle is self-contained so the next frame re-syncs the view.
        """
        async for tick in provider.stream_ticks(symbols, interval):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            await queue.put(tick)

    async def forward() -> None:
        """Push queued ticks to the client without waiting for client input.

        A streaming socket is push-driven: the client subscribes once and then
        receives frames on its own cadence, so the sender must not be gated on
        the next inbound message.
        """
        while True:
            tick = await queue.get()
            await websocket.send_text(json.dumps(_tick_payload(tick)))

    async def start_stream() -> None:
        nonlocal task, sender
        await stop_stream()
        sender = asyncio.create_task(forward())
        task = asyncio.create_task(pump())

    async def stop_stream() -> None:
        nonlocal task, sender
        for t in (task, sender):
            if t is None:
                continue
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        task = None
        sender = None

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "provider": provider.name,
                    "is_demo": provider.is_demo,
                    "supports_streaming": await provider.supports_streaming(),
                }
            )
        )

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "invalid JSON"})
                )
                continue

            action = str(msg.get("action", "")).lower()

            if action == "subscribe":
                requested = msg.get("symbols") or []
                if isinstance(requested, str):
                    requested = [requested]
                clean = [str(s).strip().upper() for s in requested if str(s).strip()]
                if not clean:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "symbols required"})
                    )
                    continue
                if len(clean) > MAX_SYMBOLS:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"at most {MAX_SYMBOLS} symbols per subscription",
                            }
                        )
                    )
                    continue
                symbols = clean
                interval = str(msg.get("interval") or "1m")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "subscribed",
                            "symbols": symbols,
                            "interval": interval,
                            "provider": provider.name,
                            "is_demo": provider.is_demo,
                        }
                    )
                )
                try:
                    await start_stream()
                except NotImplementedError:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"{provider.name} has no live feed; "
                                "use the stored-candle scheduler instead",
                            }
                        )
                    )

            elif action == "unsubscribe":
                await stop_stream()
                symbols = []
                await websocket.send_text(json.dumps({"type": "unsubscribed"}))

            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            else:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"unknown action {action!r}; "
                            "expected subscribe | unsubscribe | ping",
                        }
                    )
                )

    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Socket closed underneath us during a send; normal on abrupt disconnect.
        pass
    finally:
        await stop_stream()
        with contextlib.suppress(RuntimeError):
            await websocket.close()
