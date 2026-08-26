"""Quant engine endpoints: definition validation, signal preview, multi-symbol scan."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession, ProviderDep
from app.marketdata.base import ProviderError
from app.quant.engine import count_signals, evaluate_definition
from app.quant.indicators import INDICATORS
from app.quant.schema import TIMEFRAMES, StrategyDefinition, validate_definition
from app.services.candles import load_candles
from app.services.ingest import resolve_instrument

router = APIRouter(prefix="/quant", tags=["quant"])


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
