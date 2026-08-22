"""Indicator library.

Pure-Python kernels over OHLCV series. Every indicator:

- takes a list of `Candle` plus validated params,
- returns named output series (lists of float) aligned with the input,
- pads its warm-up region with NaN,
- never mutates input data.

The registry (`INDICATORS`) drives both validation of strategy definitions and
computation, so the schema can never reference an indicator that cannot run.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC

from app.marketdata.base import Candle

NAN = math.nan


class IndicatorError(ValueError):
    """Raised for unknown indicators or invalid parameters."""


# ---------------------------------------------------------------- sources


def _source_series(candles: Sequence[Candle], source: str) -> list[float]:
    if source == "open":
        return [c.open for c in candles]
    if source == "high":
        return [c.high for c in candles]
    if source == "low":
        return [c.low for c in candles]
    if source == "close":
        return [c.close for c in candles]
    if source == "volume":
        return [float(c.volume) for c in candles]
    if source == "hl2":
        return [(c.high + c.low) / 2 for c in candles]
    if source == "hlc3":
        return [(c.high + c.low + c.close) / 3 for c in candles]
    if source == "ohlc4":
        return [(c.open + c.high + c.low + c.close) / 4 for c in candles]
    raise IndicatorError(f"Unknown price source: {source!r}")


SOURCES = ("open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4")


# ---------------------------------------------------------------- registry


@dataclass(frozen=True)
class ParamSpec:
    kind: str  # "int" | "float" | "str"
    default: float | str
    ge: float | None = None
    le: float | None = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class IndicatorSpec:
    type: str
    outputs: tuple[str, ...]
    params: dict[str, ParamSpec]
    description: str = ""


def _spec(
    ind_type: str, outputs: tuple[str, ...], description: str = "", **params: ParamSpec
) -> tuple[str, IndicatorSpec]:
    return ind_type, IndicatorSpec(ind_type, outputs, params, description)


INDICATORS: dict[str, IndicatorSpec] = dict(
    (
        _spec(
            "SMA",
            ("sma",),
            "Simple moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "EMA",
            ("ema",),
            "Exponential moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "WMA",
            ("wma",),
            "Weighted moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "RSI",
            ("rsi",),
            "Relative strength index (Wilder)",
            length=ParamSpec("int", 14, ge=2, le=200),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "MACD",
            ("macd", "signal", "histogram"),
            "MACD line, signal line and histogram",
            fast=ParamSpec("int", 12, ge=1, le=200),
            slow=ParamSpec("int", 26, ge=1, le=400),
            signal=ParamSpec("int", 9, ge=1, le=100),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "BBANDS",
            ("upper", "middle", "lower"),
            "Bollinger bands",
            length=ParamSpec("int", 20, ge=2, le=500),
            stddev=ParamSpec("float", 2.0, ge=0.1, le=10.0),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "ATR",
            ("atr",),
            "Average true range (Wilder)",
            length=ParamSpec("int", 14, ge=1, le=200),
        ),
        _spec(
            "SUPERTREND",
            ("supertrend", "direction"),
            "Supertrend line; direction is +1 (up) / -1 (down)",
            period=ParamSpec("int", 10, ge=1, le=200),
            multiplier=ParamSpec("float", 3.0, ge=0.5, le=20.0),
        ),
        _spec(
            "STOCH",
            ("k", "d"),
            "Stochastic oscillator %K/%D",
            k_length=ParamSpec("int", 14, ge=1, le=200),
            d_length=ParamSpec("int", 3, ge=1, le=100),
        ),
        _spec(
            "ADX",
            ("adx", "plus_di", "minus_di"),
            "Average directional index (Wilder)",
            length=ParamSpec("int", 14, ge=1, le=200),
        ),
        _spec(
            "VWAP",
            ("vwap",),
            "Session-anchored VWAP (resets each IST trading day)",
        ),
        _spec(
            "ROC",
            ("roc",),
            "Rate of change (%)",
            length=ParamSpec("int", 9, ge=1, le=200),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
    )
)


def validate_params(ind_type: str, params: dict) -> dict:
    """Validate user params against the registry; returns full param dict."""
    spec = INDICATORS.get(ind_type)
    if spec is None:
        raise IndicatorError(f"Unknown indicator type: {ind_type!r}")
    unknown = set(params) - set(spec.params)
    if unknown:
        raise IndicatorError(f"{ind_type}: unknown parameter(s) {sorted(unknown)}")
    resolved: dict = {}
    for name, pspec in spec.params.items():
        raw = params.get(name, pspec.default)
        if pspec.kind == "int":
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise IndicatorError(f"{ind_type}.{name} must be an integer")
            value: float | str = raw
        elif pspec.kind == "float":
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise IndicatorError(f"{ind_type}.{name} must be a number")
            value = float(raw)
        else:
            if not isinstance(raw, str):
                raise IndicatorError(f"{ind_type}.{name} must be a string")
            value = raw
        if pspec.choices is not None and value not in pspec.choices:
            raise IndicatorError(f"{ind_type}.{name} must be one of {list(pspec.choices)}")
        if pspec.ge is not None and value < pspec.ge:
            raise IndicatorError(f"{ind_type}.{name} must be >= {pspec.ge}")
        if pspec.le is not None and value > pspec.le:
            raise IndicatorError(f"{ind_type}.{name} must be <= {pspec.le}")
        resolved[name] = value
    if ind_type == "MACD" and resolved["fast"] >= resolved["slow"]:
        raise IndicatorError("MACD.fast must be < MACD.slow")
    return resolved


# ---------------------------------------------------------------- kernels


def _sma(src: Sequence[float], length: int) -> list[float]:
    out = [NAN] * len(src)
    window: list[float] = []
    total = 0.0
    for i, v in enumerate(src):
        window.append(v)
        total += v
        if len(window) > length:
            total -= window.pop(0)
        if len(window) == length:
            out[i] = total / length
    return out


def _ema(src: Sequence[float], length: int) -> list[float]:
    out = [NAN] * len(src)
    if len(src) < length:
        return out
    k = 2.0 / (length + 1)
    prev = sum(src[:length]) / length
    out[length - 1] = prev
    for i in range(length, len(src)):
        prev = src[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _wma(src: Sequence[float], length: int) -> list[float]:
    out = [NAN] * len(src)
    denom = length * (length + 1) / 2
    for i in range(length - 1, len(src)):
        acc = 0.0
        for j in range(length):
            acc += src[i - length + 1 + j] * (j + 1)
        out[i] = acc / denom
    return out


def _wilder(values: Sequence[float], length: int) -> list[float]:
    """Wilder's smoothing (used by RSI/ATR/ADX)."""
    out = [NAN] * len(values)
    if len(values) < length:
        return out
    prev = sum(values[:length]) / length
    out[length - 1] = prev
    for i in range(length, len(values)):
        prev = (prev * (length - 1) + values[i]) / length
        out[i] = prev
    return out


def _true_range(candles: Sequence[Candle]) -> list[float]:
    tr = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        tr.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
    return tr


def _stoch_k(candles: Sequence[Candle], k_length: int) -> list[float]:
    out = [NAN] * len(candles)
    for i in range(k_length - 1, len(candles)):
        window = candles[i - k_length + 1 : i + 1]
        hh = max(c.high for c in window)
        ll = min(c.low for c in window)
        rng = hh - ll
        out[i] = 100.0 * (candles[i].close - ll) / rng if rng > 0 else 50.0
    return out


def _vwap_sessions(candles: Sequence[Candle]) -> list[float]:
    """VWAP anchored to IST trading-day sessions."""
    from datetime import timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    utc = UTC
    out = [NAN] * len(candles)
    cum_pv = cum_v = 0.0
    current_day = None
    for i, c in enumerate(candles):
        ts = c.timestamp if c.timestamp.tzinfo else c.timestamp.replace(tzinfo=utc)
        day = ts.astimezone(ist).date()
        if day != current_day:
            current_day = day
            cum_pv = cum_v = 0.0
        typical = (c.high + c.low + c.close) / 3
        vol = float(c.volume) if c.volume else 1.0
        cum_pv += typical * vol
        cum_v += vol
        out[i] = cum_pv / cum_v if cum_v > 0 else NAN
    return out


_COMPUTERS: dict[str, Callable[..., dict[str, list[float]]]] = {}


def _computer(ind_type: str):
    def register(fn):
        _COMPUTERS[ind_type] = fn
        return fn

    return register


@_computer("SMA")
def _compute_sma(candles, length, source):
    return {"sma": _sma(_source_series(candles, source), length)}


@_computer("EMA")
def _compute_ema(candles, length, source):
    return {"ema": _ema(_source_series(candles, source), length)}


@_computer("WMA")
def _compute_wma(candles, length, source):
    return {"wma": _wma(_source_series(candles, source), length)}


@_computer("RSI")
def _compute_rsi(candles, length, source):
    src = _source_series(candles, source)
    gains, losses = [0.0], [0.0]
    for i in range(1, len(src)):
        change = src[i] - src[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = _wilder(gains, length)
    avg_loss = _wilder(losses, length)
    out = [NAN] * len(src)
    for i in range(len(src)):
        if math.isnan(avg_loss[i]):
            continue
        if avg_loss[i] == 0:
            out[i] = 100.0
        elif avg_gain[i] == 0:
            out[i] = 0.0
        else:
            rs = avg_gain[i] / avg_loss[i]
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return {"rsi": out}


@_computer("MACD")
def _compute_macd(candles, fast, slow, signal, source):
    src = _source_series(candles, source)
    ema_fast = _ema(src, fast)
    ema_slow = _ema(src, slow)
    macd = [
        f - s if not (math.isnan(f) or math.isnan(s)) else NAN
        for f, s in zip(ema_fast, ema_slow, strict=True)
    ]
    first_valid = next((i for i, v in enumerate(macd) if not math.isnan(v)), len(macd))
    sig = [NAN] * len(macd)
    if first_valid < len(macd):
        compact = macd[first_valid:]
        ema_sig = _ema(compact, signal)
        sig[first_valid:] = ema_sig
    hist = [
        m - s if not (math.isnan(m) or math.isnan(s)) else NAN
        for m, s in zip(macd, sig, strict=True)
    ]
    return {"macd": macd, "signal": sig, "histogram": hist}


@_computer("BBANDS")
def _compute_bbands(candles, length, stddev, source):
    src = _source_series(candles, source)
    middle = _sma(src, length)
    upper, lower = [NAN] * len(src), [NAN] * len(src)
    for i in range(length - 1, len(src)):
        window = src[i - length + 1 : i + 1]
        mean = middle[i]
        variance = sum((v - mean) ** 2 for v in window) / length
        sd = math.sqrt(variance)
        upper[i] = mean + stddev * sd
        lower[i] = mean - stddev * sd
    return {"upper": upper, "middle": middle, "lower": lower}


@_computer("ATR")
def _compute_atr(candles, length):
    return {"atr": _wilder(_true_range(candles), length)}


@_computer("SUPERTREND")
def _compute_supertrend(candles, period, multiplier):
    atr = _wilder(_true_range(candles), period)
    n = len(candles)
    line = [NAN] * n
    direction = [NAN] * n
    upper_band = lower_band = None
    prev_dir = 1
    started = False
    for i in range(n):
        if math.isnan(atr[i]):
            continue
        mid = (candles[i].high + candles[i].low) / 2
        ub = mid + multiplier * atr[i]
        lb = mid - multiplier * atr[i]
        if not started:
            started = True
            upper_band, lower_band = ub, lb
            prev_dir = 1 if candles[i].close >= mid else -1
        else:
            ub = ub if ub < upper_band or candles[i - 1].close > upper_band else upper_band
            lb = lb if lb > lower_band or candles[i - 1].close < lower_band else lower_band
            if prev_dir == 1:
                direction_i = -1 if candles[i].close < lb else 1
            else:
                direction_i = 1 if candles[i].close > ub else -1
            upper_band, lower_band = ub, lb
            prev_dir = direction_i
        line[i] = lb if prev_dir == 1 else ub
        direction[i] = float(prev_dir)
    return {"supertrend": line, "direction": direction}


@_computer("STOCH")
def _compute_stoch(candles, k_length, d_length):
    k = _stoch_k(candles, k_length)
    first_valid = next((i for i, v in enumerate(k) if not math.isnan(v)), len(k))
    d = [NAN] * len(k)
    if first_valid < len(k):
        compact = k[first_valid:]
        sma_d = _sma(compact, d_length)
        d[first_valid:] = sma_d
    return {"k": k, "d": d}


@_computer("ADX")
def _compute_adx(candles, length):
    n = len(candles)
    plus_dm, minus_dm = [0.0], [0.0]
    for i in range(1, n):
        up = candles[i].high - candles[i - 1].high
        down = candles[i - 1].low - candles[i].low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr = _true_range(candles)
    atr = _wilder(tr, length)
    pdi_series = _wilder(plus_dm, length)
    mdi_series = _wilder(minus_dm, length)
    dx = [NAN] * n
    for i in range(n):
        if math.isnan(atr[i]) or atr[i] == 0:
            continue
        pdi = 100.0 * pdi_series[i] / atr[i]
        mdi = 100.0 * mdi_series[i] / atr[i]
        denom = pdi + mdi
        dx[i] = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0
    first_valid = next((i for i, v in enumerate(dx) if not math.isnan(v)), n)
    adx = [NAN] * n
    if first_valid < n:
        adx[first_valid:] = _wilder(dx[first_valid:], length)
    plus_di = [
        100.0 * p / a if not (math.isnan(a) or a == 0) else NAN
        for p, a in zip(pdi_series, atr, strict=True)
    ]
    minus_di = [
        100.0 * m / a if not (math.isnan(a) or a == 0) else NAN
        for m, a in zip(mdi_series, atr, strict=True)
    ]
    return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}


@_computer("VWAP")
def _compute_vwap(candles):
    return {"vwap": _vwap_sessions(candles)}


@_computer("ROC")
def _compute_roc(candles, length, source):
    src = _source_series(candles, source)
    out = [NAN] * len(src)
    for i in range(length, len(src)):
        base = src[i - length]
        out[i] = 100.0 * (src[i] - base) / base if base != 0 else NAN
    return {"roc": out}


def compute_indicator(
    ind_type: str, candles: Sequence[Candle], params: dict | None = None
) -> dict[str, list[float]]:
    """Validate params and compute all outputs for the given indicator."""
    resolved = validate_params(ind_type, params or {})
    computer = _COMPUTERS.get(ind_type)
    if computer is None:
        raise IndicatorError(f"No implementation registered for {ind_type!r}")
    if not candles:
        raise IndicatorError("Cannot compute indicators on an empty candle series")
    return computer(candles, **resolved)
