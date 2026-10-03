"""MCP server exposing StrategyLab to AI agents and assistants.

Runs as a separate process over stdio (the usual desktop-agent transport) or
streamable HTTP:

    uv run python -m app.mcp_server                      # stdio
    uv run python -m app.mcp_server --transport http    # streamable HTTP :8765

Tools are thin adapters over the same services the HTTP API uses, so an agent
sees identical data and identical numbers. Nothing here bypasses the engines:
indicators go through `compute_indicator`, backtests through the real backtest
service, pricing through `app.options.greeks`.

This module is import-safe and has no side effects at import time so tests can
import and call the underlying functions directly. The transport only starts
under `main()`.
"""

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from mcp.server.mcpserver import MCPServer

from app.db.session import get_session_factory
from app.marketdata.factory import get_provider
from app.quant.indicators import INDICATORS, IndicatorError, compute_indicator
from app.quant.schema import TIMEFRAMES

SERVER_NAME = "strategylab"
INSTRUCTIONS = (
    "StrategyLab trading research server. Use get_candles for price history, "
    "compute_indicators for technical overlays, option_chain for live strikes "
    "and greeks, basket_payoff for multi-leg payoffs, and run_backtest to test "
    "a strategy over stored history."
)


def _fmt(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


async def _fetch_candles(symbol: str, interval: str, bars: int):
    """Provider candles for the trailing `bars`, oldest first."""
    provider = get_provider()
    step = {
        "1m": 2, "5m": 10, "15m": 30, "30m": 60, "1h": 180, "1d": 1440,
    }.get(interval, 10)
    minutes = max(bars, 50) * step
    end = datetime.now(UTC)
    start = end - timedelta(minutes=minutes)
    candles = await provider.get_historical_data(symbol, interval, start, end)
    return provider, candles[-bars:]


def _parse_indicator_token(token: str) -> tuple[str, dict]:
    """Same token grammar as GET /quant/series: `SMA`, `RSI:14`, `BBANDS:length=20,stddev=2`."""
    from app.api.v1.quant import _parse_indicator_token as parse

    return parse(token)


def _split_indicator_tokens(indicators: str) -> list[str]:
    """Reuse the HTTP splitter so multi-parameter tokens survive."""
    from app.api.v1.quant import _split_indicator_tokens as split

    return split(indicators)


server = MCPServer(name=SERVER_NAME, instructions=INSTRUCTIONS)


@server.tool(
    name="list_indicators",
    title="List technical indicators",
    description=(
        "Every supported indicator with its outputs and parameters. Call this "
        "first to build valid compute_indicators tokens."
    ),
)
async def list_indicators() -> str:
    return json.dumps(
        {
            "timeframes": list(TIMEFRAMES),
            "count": len(INDICATORS),
            "indicators": [
                {
                    "type": spec.type,
                    "description": spec.description,
                    "outputs": list(spec.outputs),
                    "params": {
                        name: {
                            "kind": p.kind,
                            "default": p.default,
                            **({"ge": p.ge} if p.ge is not None else {}),
                            **({"le": p.le} if p.le is not None else {}),
                            **({"choices": list(p.choices)} if p.choices else {}),
                        }
                        for name, p in spec.params.items()
                    },
                }
                for spec in INDICATORS.values()
            ],
        },
        indent=None,
    )


@server.tool(
    name="get_candles",
    title="Get price candles",
    description=(
        "OHLCV candles for a symbol and timeframe, oldest first. Uses the "
        "configured market-data provider; the response is flagged is_demo when "
        "synthetic data is in use."
    ),
)
async def get_candles(
    symbol: str = "NIFTY",
    interval: str = "5m",
    bars: int = 200,
) -> str:
    if interval not in TIMEFRAMES:
        return json.dumps({"error": f"Unknown interval {interval!r}; expected one of {list(TIMEFRAMES)}"})
    if not 1 <= bars <= 2000:
        return json.dumps({"error": "bars must be between 1 and 2000"})
    provider, candles = await _fetch_candles(symbol, interval, bars)
    if not candles:
        return json.dumps({"error": f"No candles available for {symbol} {interval}"})
    return json.dumps(
        {
            "symbol": symbol,
            "interval": interval,
            "provider": provider.name,
            "is_demo": provider.is_demo,
            "bars": len(candles),
            "candles": [
                {
                    "time": int(c.timestamp.timestamp()),
                    "open": _fmt(c.open),
                    "high": _fmt(c.high),
                    "low": _fmt(c.low),
                    "close": _fmt(c.close),
                    "volume": _fmt(c.volume, 0),
                    "oi": _fmt(c.oi, 0),
                }
                for c in candles
            ],
        }
    )


@server.tool(
    name="compute_indicators",
    title="Compute indicator overlays",
    description=(
        "Compute indicators over recent candles. `indicators` is a comma "
        "separated list using TYPE, TYPE:14, or TYPE:length=20,stddev=2. "
        "Returns series index-aligned with the candles; null marks warm-up."
    ),
)
async def compute_indicators(
    symbol: str = "NIFTY",
    interval: str = "5m",
    indicators: str = "SMA:20,EMA:50,RSI:14",
    bars: int = 200,
) -> str:
    if interval not in TIMEFRAMES:
        return json.dumps({"error": f"Unknown interval {interval!r}"})
    provider, candles = await _fetch_candles(symbol, interval, bars)
    if not candles:
        return json.dumps({"error": f"No candles available for {symbol} {interval}"})
    series: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for token in _split_indicator_tokens(indicators):
        try:
            ind_type, params = _parse_indicator_token(token)
            computed = compute_indicator(ind_type, candles, params)
        except IndicatorError as exc:
            errors[token] = str(exc)
            continue
        series[token] = {
            out: [_fmt(v, 4) if v == v else None for v in vals]
            for out, vals in computed.items()
        }
    # include the closes so the caller can align the series to price
    return json.dumps(
        {
            "symbol": symbol,
            "interval": interval,
            "provider": provider.name,
            "is_demo": provider.is_demo,
            "bars": len(candles),
            "times": [int(c.timestamp.timestamp()) for c in candles],
            "close": [_fmt(c.close) for c in candles],
            "series": series,
            "errors": errors,
        }
    )


@server.tool(
    name="option_chain",
    title="Fetch option chain",
    description="Live option chain for an underlying, with per-strike greeks and OI.",
)
async def option_chain(underlying: str = "NIFTY", expiry: str | None = None) -> str:
    provider = get_provider()
    try:
        chain = await provider.get_option_chain(underlying, expiry)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent as data
        return json.dumps({"error": f"Option chain failed: {exc}"})
    chain.setdefault("provider", provider.name)
    chain.setdefault("is_demo", provider.is_demo)
    return json.dumps(chain)


@server.tool(
    name="basket_payoff",
    title="Price a multi-leg basket",
    description=(
        "Combined premium, greeks and expiry payoff for a basket of option legs. "
        "Each leg is {action: buy|sell, option_type: CE|PE, strike, premium, "
        "quantity}. Useful for straddles, strangles and custom spreads."
    ),
)
async def basket_payoff(
    legs: str,
    spot: float = 22000.0,
    days_to_expiry: int = 7,
    volatility: float = 16.0,
) -> str:
    from app.schemas.basket import BasketPayoffRequest

    try:
        payload = json.loads(legs) if isinstance(legs, str) else legs
        request = BasketPayoffRequest.model_validate(
            {
                "spot": spot,
                "days_to_expiry": days_to_expiry,
                "volatility": volatility,
                "legs": payload,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"Invalid basket: {exc}"})
    from app.options.basket import compute_basket_payoff

    result = compute_basket_payoff(request)
    return result.model_dump_json()


@server.tool(
    name="list_strategies",
    title="List saved strategies",
    description="Saved strategies with their underlying, timeframe and status.",
)
async def list_strategies(limit: int = 25) -> str:
    from sqlalchemy import select

    from app.models import Strategy

    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                select(Strategy)
                .order_by(Strategy.updated_at.desc())
                .limit(max(1, min(limit, 200)))
            )
        ).scalars().all()
        return json.dumps(
            {
                "count": len(rows),
                "strategies": [
                    {
                        "id": str(s.id),
                        "name": s.name,
                        "underlying": s.underlying,
                        "status": s.status,
                        "description": s.description,
                    }
                    for s in rows
                ],
            }
        )


@server.tool(
    name="get_strategy",
    title="Get one strategy definition",
    description="Full JSON strategy definition, the same payload the backtester consumes.",
)
async def get_strategy(strategy_id: str) -> str:
    import uuid

    from sqlalchemy import select

    from app.models import Strategy

    try:
        sid = uuid.UUID(strategy_id)
    except ValueError:
        return json.dumps({"error": "strategy_id must be a UUID"})
    factory = get_session_factory()
    async with factory() as session:
        s = (await session.execute(select(Strategy).where(Strategy.id == sid))).scalars().first()
        if s is None:
            return json.dumps({"error": f"No strategy {strategy_id}"})
        return json.dumps(
            {
                "id": str(s.id),
                "name": s.name,
                "underlying": s.underlying,
                "status": s.status,
                "definition": s.definition,
            }
        )


@server.tool(
    name="health",
    title="Server health",
    description="Confirms the server is up and reports the active market-data provider.",
)
async def health() -> str:
    provider = get_provider()
    return json.dumps(
        {
            "status": "ok",
            "server": SERVER_NAME,
            "provider": provider.name,
            "is_demo": provider.is_demo,
            "indicators": len(INDICATORS),
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="StrategyLab MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="stdio for desktop agents; streamable-http to expose over HTTP",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        server.run(transport="stdio")
        return 0
    server.run(transport=args.transport, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
