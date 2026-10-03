"""Quant engine endpoints: definition validation, signal preview, multi-symbol scan."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession, ProviderDep
from app.marketdata.base import ProviderError
from app.quant.engine import count_signals, evaluate_definition
from app.quant.indicators import INDICATORS, IndicatorError, compute_indicator
from app.quant.schema import TIMEFRAMES, StrategyDefinition, validate_definition
from app.services.candles import load_candles
from app.services.ingest import resolve_instrument

router = APIRouter(prefix="/quant", tags=["quant"])


def _split_indicator_tokens(indicators: str) -> list[str]:
    """Split a comma-separated overlay list into individual tokens.

    Naive ``split(",")`` breaks multi-parameter indicators: the comma inside
    ``BBANDS:length=20,stddev=2`` looks like a separator, so the tail is
    mistaken for a new indicator.

    The grammar makes this unambiguous. A token is either ``TYPE`` or
    ``TYPE:<positional>`` or ``TYPE:k=v,...``. So a chunk that carries no ``=``
    is always a new token, even if its type is unknown, because an unrecognised
    indicator must surface as its own error rather than being silently absorbed
    into a neighbour's parameter list.

    For a chunk that does carry ``=``, it is a parameter of the current token
    when the key names one of that token's parameters; otherwise it starts a new
    token. Testing against the *current token's* params rather than against all
    indicator names matters: ``STDDEV`` is both a real indicator and a
    parameter of ``BBANDS``, so a global name lookup misreads
    ``BBANDS:length=20,stddev=2`` as two indicators.
    """
    tokens: list[str] = []
    for chunk in indicators.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not tokens:
            tokens.append(chunk)
            continue
        if "=" not in chunk:
            tokens.append(chunk)
            continue
        current_type = tokens[-1].partition(":")[0].strip().upper()
        key = chunk.partition("=")[0].strip().lower()
        params = INDICATORS[current_type].params if current_type in INDICATORS else {}
        if key in params:
            tokens[-1] = f"{tokens[-1]},{chunk}"
        else:
            tokens.append(chunk)
    return tokens


def _parse_indicator_token(token: str) -> tuple[str, dict]:
    """Parse a chart overlay spec like ``SMA:length=20`` or ``RSI:14``.

    Bare ``TYPE`` uses every default. ``TYPE:14`` is shorthand for a single
    ``length``-style positional param. ``TYPE:k=v,k=v`` is explicit and is the
    form the UI emits. Returns (type, params).
    """
    token = token.strip()
    if not token:
        raise IndicatorError("Empty indicator token")
    head, _, tail = token.partition(":")
    ind_type = head.strip().upper()
    spec = INDICATORS.get(ind_type)
    if spec is None:
        raise IndicatorError(f"Unknown indicator type: {ind_type!r}")
    params: dict = {}
    if not tail.strip():
        return ind_type, params
    if "=" in tail:
        for pair in tail.split(","):
            key, _, raw = pair.partition("=")
            key = key.strip()
            if key not in spec.params:
                raise IndicatorError(f"{ind_type}: unknown parameter {key!r}")
            pspec = spec.params[key]
            try:
                params[key] = (
                    int(raw) if pspec.kind == "int"
                    else float(raw) if pspec.kind == "float"
                    else raw.strip().strip("'\"")
                )
            except ValueError as exc:
                raise IndicatorError(f"{ind_type}.{key} is not a valid {pspec.kind}") from exc
        return ind_type, params
    # positional shorthand: first param only
    values = [v.strip() for v in tail.split(",") if v.strip()]
    first = next(iter(spec.params), None)
    if first is None:
        raise IndicatorError(f"{ind_type} takes no parameters")
    pspec = spec.params[first]
    try:
        params[first] = (
            int(values[0]) if pspec.kind == "int"
            else float(values[0]) if pspec.kind == "float"
            else values[0]
        )
    except ValueError as exc:
        raise IndicatorError(f"{ind_type}.{first} is not a valid {pspec.kind}") from exc
    return ind_type, params


def _jsonable(values: list[float]) -> list[float | None]:
    """NaN is not valid JSON; emit null so the client can gap the line."""
    return [None if v != v else v for v in values]


@router.get("/series")
async def indicator_series(
    user: CurrentUser,
    provider: ProviderDep,
    symbol: str = Query(default="NIFTY"),
    interval: str = Query(default="5m"),
    indicators: str = Query(default=""),
    bars: int = Query(default=500, ge=20, le=2000),
) -> dict:
    """Candles plus indicator series, index-aligned, for charting.

    Unlike ``/quant/preview`` (which reports signal counts and the last bar),
    this returns the full computed series so a chart terminal can draw
    overlays that line up exactly with the price bars.

    `indicators` is a comma-separated list of ``TYPE`` or ``TYPE:k=v`` specs.
    """
    tokens = _split_indicator_tokens(indicators)
    end = datetime.now(UTC)
    start = end - timedelta(days=60)
    try:
        candles = await provider.get_historical_data(symbol, interval, start, end)
    except ProviderError:
        raise
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if not candles:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No candles for {symbol} {interval}")
    candles = candles[-bars:]

    series: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for token in tokens:
        try:
            ind_type, params = _parse_indicator_token(token)
            computed = compute_indicator(ind_type, candles, params)
        except IndicatorError as exc:
            errors[token] = str(exc)
            continue
        label = token.strip()
        series[label] = {out: _jsonable(vals) for out, vals in computed.items()}

    return {
        "symbol": symbol,
        "timeframe": interval,
        "provider": provider.name,
        "is_demo": provider.is_demo,
        "bars": len(candles),
        "candles": [
            {
                "time": int(c.timestamp.timestamp()),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "oi": c.oi,
            }
            for c in candles
        ],
        "series": series,
        "errors": errors,
    }


@router.get("/catalog")
async def indicator_catalog(user: CurrentUser) -> dict:
    """Machine-readable catalog of every supported indicator (for builders)."""
    return {
        "timeframes": list(TIMEFRAMES),
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
    }


@router.post("/validate")
async def validate(definition: dict, user: CurrentUser) -> dict:
    """Validate a raw strategy-definition JSON document."""
    errors, warnings = validate_definition(definition)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


@router.post("/preview")
async def preview(
    definition: dict,
    provider: ProviderDep,
    db: DbSession,
    user: CurrentUser,
    bars: int = Query(default=500, ge=50, le=2000),
) -> dict:
    """Evaluate a definition over recent candles and report signals.

    Uses the active market-data provider; with the demo provider this is
    synthetic data and the response is flagged accordingly.
    """
    errors, _ = validate_definition(definition)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Invalid strategy definition", "errors": errors},
        )
    parsed = StrategyDefinition.model_validate(definition)

    instrument = await resolve_instrument(db, parsed.instrument.symbol)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown symbol {parsed.instrument.symbol!r}; sync the instrument master first",
        )

    end = datetime.now(UTC)
    start = end - timedelta(days=30)
    try:
        candles = await provider.get_historical_data(
            parsed.instrument.symbol, parsed.timeframe, start, end
        )
    except ProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Candle fetch failed: {exc}") from exc

    candles = candles[-bars:]
    result = evaluate_definition(parsed, candles)
    entries, exits = count_signals(result)

    last_index = len(candles) - 1
    tail: dict[str, dict[str, float | None]] = {}
    for ind_id, outputs in result.indicator_series.items():
        tail[ind_id] = {
            out: (
                series[last_index] if series[last_index] == series[last_index] else None
            )
            for out, series in outputs.items()
        }

    return {
        "symbol": parsed.instrument.symbol,
        "timeframe": parsed.timeframe,
        "bars_evaluated": len(candles),
        "provider": provider.name,
        "is_demo": provider.is_demo,
        "entry_signals": entries,
        "exit_signals": exits,
        "last_bar_entry_signal": bool(result.entry_signals[last_index]),
        "last_bar_exit_signal": bool(result.exit_signals[last_index]),
        "indicator_tail": tail,
    }

# ---- multi-symbol scanner ----


class ScanRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    definition: dict
    start: datetime | None = None
    end: datetime | None = None


class ScanRow(BaseModel):
    symbol: str
    bars_evaluated: int
    entry_signals: int
    exit_signals: int
    last_bar_entry_signal: bool
    last_close: float | None


class ScanResponse(BaseModel):
    scanned: int
    timeframe: str
    rows: list[ScanRow]
    errors: dict[str, str]


@router.post("/scan", response_model=ScanResponse)
async def scan_symbols(
    payload: ScanRequest,
    db: DbSession,
    user: CurrentUser,
) -> ScanResponse:
    """Run one definition across many stored-candle symbols, ranked by recency of signal.

    Uses only locally stored candles (reproducibility policy) — sync/ingest first.
    """
    errors, _ = validate_definition(payload.definition)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Invalid strategy definition", "errors": errors},
        )
    parsed = StrategyDefinition.model_validate(payload.definition)

    end = payload.end or datetime.now(UTC)
    start = payload.start or end - timedelta(days=30)

    seen = set()
    symbols = [s.upper().strip() for s in payload.symbols if s.strip()]
    deduped = [s for s in symbols if not (s in seen or seen.add(s))]

    rows: list[ScanRow] = []
    symbol_errors: dict[str, str] = {}

    for symbol in deduped[:50]:
        try:
            candles = await load_candles(db, symbol=symbol, interval=parsed.timeframe, start=start, end=end)
            if len(candles) < 5:
                symbol_errors[symbol] = f"no stored candles ({len(candles)})"
                continue
            result = evaluate_definition(parsed, candles)
            entries, exits = count_signals(result)
            rows.append(ScanRow(
                symbol=symbol,
                bars_evaluated=len(candles),
                entry_signals=entries,
                exit_signals=exits,
                last_bar_entry_signal=bool(result.entry_signals[-1]),
                last_close=float(candles[-1].close),
            ))
        except Exception as exc:  # noqa: BLE001 - per-symbol isolation
            symbol_errors[symbol] = str(exc)[:200]

    # Fresh entries on the last bar first, then by total signal count.
    rows.sort(key=lambda r: (not r.last_bar_entry_signal, -r.entry_signals))
    return ScanResponse(
        scanned=len(rows),
        timeframe=parsed.timeframe,
        rows=rows,
        errors=symbol_errors,
    )
