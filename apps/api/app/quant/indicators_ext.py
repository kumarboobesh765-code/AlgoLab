"""Extended indicator library.

Clean-room implementations of the standard technical-analysis families that
`indicators.py` does not cover: adaptive/advanced moving averages, momentum
oscillators, volatility channels, volume studies and rolling statistics.

Registration contract is identical to `app.quant.indicators`:

- every indicator is declared in `EXTENDED_SPECS` via `_spec(...)`, and
- every kernel is attached with `@_computer(...)`.

`indicators.py` imports this module at the bottom so the two registries merge
before any strategy validation runs. Kernels are pure functions over `Candle`
sequences: they never mutate input and pad warm-up regions with NaN, exactly
like the core library.
"""

import math
from collections.abc import Sequence

from app.marketdata.base import Candle
from app.quant.indicators import (
    NAN,
    SOURCES,
    IndicatorError,
    ParamSpec,
    _computer,
    _ema,
    _sma,
    _source_series,
    _spec,
    _true_range,
    _wilder,
    _wma,
)

# ---------------------------------------------------------------- helpers


def _rolling_max(src: Sequence[float], length: int) -> list[float]:
    out = [NAN] * len(src)
    for i in range(length - 1, len(src)):
        out[i] = max(src[i - length + 1 : i + 1])
    return out


def _rolling_min(src: Sequence[float], length: int) -> list[float]:
    out = [NAN] * len(src)
    for i in range(length - 1, len(src)):
        out[i] = min(src[i - length + 1 : i + 1])
    return out


def _rolling_stddev(src: Sequence[float], length: int) -> list[float]:
    """Population standard deviation over a trailing window."""
    out = [NAN] * len(src)
    for i in range(length - 1, len(src)):
        window = src[i - length + 1 : i + 1]
        mean = sum(window) / length
        var = sum((v - mean) ** 2 for v in window) / length
        out[i] = math.sqrt(var)
    return out


def _typical(candles: Sequence[Candle]) -> list[float]:
    return [(c.high + c.low + c.close) / 3 for c in candles]


def _safe_div(num: float, den: float) -> float:
    return num / den if den not in (0, NAN) and not math.isnan(den) else NAN


def _linreg(src: Sequence[float], length: int) -> tuple[list[float], list[float], list[float]]:
    """Rolling ordinary-least-squares fit over x = 0..length-1.

    Returns (value, slope, intercept) where `value` is the fitted series
    evaluated at the window's right edge (x = length-1).
    """
    n = len(src)
    value = [NAN] * n
    slope = [NAN] * n
    intercept = [NAN] * n
    sum_x = length * (length - 1) / 2.0
    sum_xx = (length - 1) * length * (2 * length - 1) / 6.0
    denom = length * sum_xx - sum_x * sum_x
    if denom == 0:
        return value, slope, intercept
    for i in range(length - 1, n):
        window = src[i - length + 1 : i + 1]
        sum_y = sum(window)
        sum_xy = sum(j * y for j, y in enumerate(window))
        sxy = (length * sum_xy - sum_x * sum_y) / denom
        b = (sum_y - sxy * sum_x) / length
        slope[i] = sxy
        intercept[i] = b
        value[i] = b + sxy * (length - 1)
    return value, slope, intercept


def _ema_over(src: Sequence[float], length: int) -> list[float]:
    """EMA that tolerates a NaN warm-up prefix.

    `_ema` seeds from `sum(src[:length])`, so feeding it a series whose warm-up
    is NaN poisons the accumulator permanently. Composites (DEMA/TEMA/ZEMA/T3/
    TRIX/TSI) chain EMAs over already-NaN-padded output, so they must compact
    to the first finite index, seed there, and re-expand. This matches how the
    core MACD kernel seeds its signal EMA.
    """
    out = [NAN] * len(src)
    start = next((i for i, v in enumerate(src) if not math.isnan(v)), len(src))
    if start >= len(src):
        return out
    out[start:] = _ema(src[start:], length)
    return out


# ---------------------------------------------------------------- registry

EXTENDED_SPECS = dict(
    (
        # --- moving averages
        _spec(
            "SMMA",
            ("smma",),
            "Smoothed (Wilder's) moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "DEMA",
            ("dema",),
            "Double exponential moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "TEMA",
            ("tema",),
            "Triple exponential moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "ZEMA",
            ("zema",),
            "Zero-lag exponential moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "HMA",
            ("hma",),
            "Hull moving average",
            length=ParamSpec("int", 20, ge=2, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "VWMA",
            ("vwma",),
            "Volume-weighted moving average",
            length=ParamSpec("int", 20, ge=1, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "ALMA",
            ("alma",),
            "Arnaud Legoux moving average",
            length=ParamSpec("int", 9, ge=2, le=200),
            offset=ParamSpec("float", 0.85, ge=0.0, le=1.0),
            sigma=ParamSpec("float", 6.0, ge=0.1, le=50.0),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "KAMA",
            ("kama",),
            "Kaufman's adaptive moving average",
            length=ParamSpec("int", 10, ge=2, le=200),
            fast=ParamSpec("int", 2, ge=1, le=100),
            slow=ParamSpec("int", 30, ge=2, le=400),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "T3",
            ("t3",),
            "Tillson T3 moving average",
            length=ParamSpec("int", 5, ge=1, le=200),
            vfactor=ParamSpec("float", 0.7, ge=0.0, le=1.0),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        # --- momentum
        _spec(
            "MOM",
            ("mom",),
            "Momentum (close minus close N bars ago)",
            length=ParamSpec("int", 10, ge=1, le=200),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "CCI",
            ("cci",),
            "Commodity channel index",
            length=ParamSpec("int", 20, ge=2, le=200),
            source=ParamSpec("str", "hlc3", choices=SOURCES),
        ),
        _spec(
            "WILLR",
            ("willr",),
            "Williams %R",
            length=ParamSpec("int", 14, ge=1, le=200),
        ),
        _spec(
            "MFI",
            ("mfi",),
            "Money flow index",
            length=ParamSpec("int", 14, ge=2, le=200),
        ),
        _spec(
            "TRIX",
            ("trix",),
            "Triple-smoothed rate of change (%)",
            length=ParamSpec("int", 15, ge=1, le=200),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "TSI",
            ("tsi",),
            "True strength index",
            long=ParamSpec("int", 25, ge=2, le=200),
            short=ParamSpec("int", 13, ge=1, le=100),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "ULTOSC",
            ("ultosc",),
            "Ultimate oscillator",
            fast=ParamSpec("int", 7, ge=1, le=100),
            medium=ParamSpec("int", 14, ge=1, le=100),
            slow=ParamSpec("int", 28, ge=1, le=200),
        ),
        _spec(
            "CMO",
            ("cmo",),
            "Chande momentum oscillator",
            length=ParamSpec("int", 14, ge=1, le=200),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "PPO",
            ("ppo", "signal", "histogram"),
            "Percentage price oscillator",
            fast=ParamSpec("int", 12, ge=1, le=200),
            slow=ParamSpec("int", 26, ge=2, le=400),
            signal=ParamSpec("int", 9, ge=1, le=100),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "AO",
            ("ao",),
            "Awesome oscillator (SMA(5) - SMA(34) of hl2)",
            fast=ParamSpec("int", 5, ge=1, le=100),
            slow=ParamSpec("int", 34, ge=2, le=200),
        ),
        _spec(
            "AROON",
            ("up", "down", "oscillator"),
            "Aroon up/down/oscillator",
            length=ParamSpec("int", 14, ge=1, le=200),
        ),
        _spec(
            "DPO",
            ("dpo",),
            "Detrended price oscillator",
            length=ParamSpec("int", 20, ge=2, le=200),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "STOCHRSI",
            ("k", "d"),
            "Stochastic RSI",
            rsi_length=ParamSpec("int", 14, ge=2, le=200),
            stoch_length=ParamSpec("int", 14, ge=1, le=200),
            d_length=ParamSpec("int", 3, ge=1, le=100),
        ),
        # --- volatility
        _spec(
            "NATR",
            ("natr",),
            "Normalized average true range (%)",
            length=ParamSpec("int", 14, ge=1, le=200),
        ),
        _spec(
            "STDDEV",
            ("stddev",),
            "Rolling population standard deviation",
            length=ParamSpec("int", 20, ge=2, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "DONCHIAN",
            ("upper", "middle", "lower"),
            "Donchian channel",
            length=ParamSpec("int", 20, ge=1, le=500),
        ),
        _spec(
            "KC",
            ("upper", "middle", "lower"),
            "Keltner channel",
            length=ParamSpec("int", 20, ge=2, le=500),
            multiplier=ParamSpec("float", 2.0, ge=0.1, le=10.0),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        _spec(
            "HV",
            ("hv",),
            "Historical volatility, annualised (%)",
            length=ParamSpec("int", 20, ge=2, le=500),
            periods_per_year=ParamSpec("int", 252, ge=1, le=100000),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
        # --- volume
        _spec(
            "OBV",
            ("obv",),
            "On balance volume",
        ),
        _spec(
            "AD",
            ("ad",),
            "Accumulation/distribution",
        ),
        _spec(
            "PVT",
            ("pvt",),
            "Price volume trend",
        ),
        _spec(
            "CMF",
            ("cmf",),
            "Chaikin money flow",
            length=ParamSpec("int", 20, ge=1, le=200),
        ),
        _spec(
            "EOM",
            ("eom",),
            "Ease of movement",
            length=ParamSpec("int", 14, ge=1, le=200),
            divisor=ParamSpec("int", 10000, ge=1, le=100000000),
        ),
        _spec(
            "EFI",
            ("efi",),
            "Elder force index",
            length=ParamSpec("int", 13, ge=1, le=200),
        ),
        _spec(
            "NVI",
            ("nvi",),
            "Negative volume index (smoothed)",
            length=ParamSpec("int", 100, ge=1, le=1000),
        ),
        # --- statistics
        _spec(
            "LINEARREG",
            ("value", "slope", "intercept"),
            "Rolling linear regression value/slope/intercept",
            length=ParamSpec("int", 14, ge=2, le=500),
            source=ParamSpec("str", "close", choices=SOURCES),
        ),
    )
)

# ---------------------------------------------------------------- moving averages


@_computer("SMMA")
def _compute_smma(candles, length, source):
    return {"smma": _wilder(_source_series(candles, source), length)}


@_computer("DEMA")
def _compute_dema(candles, length, source):
    src = _source_series(candles, source)
    e1 = _ema(src, length)
    e2 = _ema_over(e1, length)
    return {"dema": [a * 2 - b for a, b in zip(e1, e2, strict=True)]}


@_computer("TEMA")
def _compute_tema(candles, length, source):
    src = _source_series(candles, source)
    e1 = _ema(src, length)
    e2 = _ema_over(e1, length)
    e3 = _ema_over(e2, length)
    return {
        "tema": [
            3 * a - 3 * b + c for a, b, c in zip(e1, e2, e3, strict=True)
        ]
    }


@_computer("ZEMA")
def _compute_zema(candles, length, source):
    src = _source_series(candles, source)
    e1 = _ema(src, length)
    e2 = _ema_over(e1, length)
    return {"zema": [2 * a - b for a, b in zip(e1, e2, strict=True)]}


@_computer("HMA")
def _compute_hma(candles, length, source):
    src = _source_series(candles, source)
    half = max(1, int(round(length / 2)))
    root = max(1, int(round(math.sqrt(length))))
    w_half = _wma(src, half)
    w_full = _wma(src, length)
    raw = [2 * h - f for h, f in zip(w_half, w_full, strict=True)]
    return {"hma": _wma(raw, root)}


@_computer("VWMA")
def _compute_vwma(candles, length, source):
    src = _source_series(candles, source)
    vols = [float(c.volume) if c.volume else 1.0 for c in candles]
    out = [NAN] * len(src)
    for i in range(length - 1, len(src)):
        pv = 0.0
        vv = 0.0
        for j in range(i - length + 1, i + 1):
            pv += src[j] * vols[j]
            vv += vols[j]
        out[i] = _safe_div(pv, vv)
    return {"vwma": out}


@_computer("ALMA")
def _compute_alma(candles, length, offset, sigma, source):
    src = _source_series(candles, source)
    if offset <= 0.0:
        raise IndicatorError("ALMA.offset must be > 0")
    m = offset * (length - 1)
    s = length / offset
    weights = [
        math.exp(-(((i - m) ** 2) / (2.0 * s * s))) for i in range(length)
    ]
    norm = sum(weights)
    out = [NAN] * len(src)
    for i in range(length - 1, len(src)):
        acc = 0.0
        for j in range(length):
            acc += weights[j] * src[i - length + 1 + j]
        out[i] = _safe_div(acc, norm)
    return {"alma": out}


@_computer("KAMA")
def _compute_kama(candles, length, fast, slow, source):
    src = _source_series(candles, source)
    n = len(src)
    out = [NAN] * n
    if n < length:
        return {"kama": out}
    sc_fast = 2.0 / (fast + 1)
    sc_slow = 2.0 / (slow + 1)
    prev = src[0]
    started = False
    for i in range(length, n):
        change = abs(src[i] - src[i - length])
        volatility = 0.0
        for j in range(i - length + 1, i + 1):
            volatility += abs(src[j] - src[j - 1])
        er = _safe_div(change, volatility)
        if math.isnan(er):
            er = 0.0
        er = min(1.0, max(0.0, er))
        sc = (er * (sc_fast - sc_slow) + sc_slow) ** 2
        if not started:
            # seed with a simple average of the first `length` bars
            prev = sum(src[: length + 1]) / (length + 1)
            started = True
            out[i] = prev
            continue
        prev = prev + sc * (src[i] - prev)
        out[i] = prev
    return {"kama": out}


@_computer("T3")
def _compute_t3(candles, length, vfactor, source):
    """Tillson T3: six cascaded EMAs combined by the classic cubic weights.

    The weights must sum to 1 so that a flat input maps to that same flat
    level (unity DC gain). c4 carries the leading 1 for exactly that reason.
    """
    src = _source_series(candles, source)
    v = vfactor
    e1 = _ema(src, length)
    e2 = _ema_over(e1, length)
    e3 = _ema_over(e2, length)
    e4 = _ema_over(e3, length)
    e5 = _ema_over(e4, length)
    e6 = _ema_over(e5, length)
    c1 = -(v**3)
    c2 = 3 * v * v + 3 * v**3
    c3 = -(6 * v * v + 3 * v + 3 * v**3)
    c4 = 1 + 3 * v + 3 * v * v + v**3
    return {
        "t3": [
            c1 * a + c2 * b + c3 * c + c4 * d
            for a, b, c, d in zip(e6, e5, e4, e3, strict=True)
        ]
    }


# ---------------------------------------------------------------- momentum


@_computer("MOM")
def _compute_mom(candles, length, source):
    src = _source_series(candles, source)
    out = [NAN] * len(src)
    for i in range(length, len(src)):
        out[i] = src[i] - src[i - length]
    return {"mom": out}


@_computer("CCI")
def _compute_cci(candles, length, source):
    src = _source_series(candles, source)
    ma = _sma(src, length)
    out = [NAN] * len(src)
    for i in range(length - 1, len(src)):
        window = src[i - length + 1 : i + 1]
        mean_dev = sum(abs(v - ma[i]) for v in window) / length
        out[i] = _safe_div(src[i] - ma[i], 0.015 * mean_dev)
    return {"cci": out}


@_computer("WILLR")
def _compute_willr(candles, length):
    n = len(candles)
    hh = _rolling_max([c.high for c in candles], length)
    ll = _rolling_min([c.low for c in candles], length)
    out = [NAN] * n
    for i in range(length - 1, n):
        rng = hh[i] - ll[i]
        out[i] = -100.0 * _safe_div(hh[i] - candles[i].close, rng)
    return {"willr": out}


@_computer("MFI")
def _compute_mfi(candles, length):
    tp = _typical(candles)
    n = len(candles)
    out = [NAN] * n
    # window covers tp deltas [i-length+1 .. i]; each delta spans two bars
    for i in range(length, n):
        pos = neg = 0.0
        for j in range(i - length + 1, i + 1):
            flow = tp[j] * float(candles[j].volume or 0.0)
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        if pos + neg == 0:
            out[i] = 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + _safe_div(pos, neg))
    return {"mfi": out}


@_computer("TRIX")
def _compute_trix(candles, length, source):
    src = _source_series(candles, source)
    e1 = _ema(src, length)
    e2 = _ema_over(e1, length)
    e3 = _ema_over(e2, length)
    out = [NAN] * len(e3)
    for i in range(1, len(e3)):
        if math.isnan(e3[i]) or math.isnan(e3[i - 1]) or e3[i - 1] == 0:
            continue
        out[i] = 100.0 * (e3[i] - e3[i - 1]) / e3[i - 1]
    return {"trix": out}


@_computer("TSI")
def _compute_tsi(candles, long, short, source):
    src = _source_series(candles, source)
    n = len(src)
    changes = [0.0] + [src[i] - src[i - 1] for i in range(1, n)]
    abs_changes = [abs(c) for c in changes]
    # double-smoothed: ema(long) then ema(short)
    num = _ema_over(_ema(changes, long), short)
    den = _ema_over(_ema(abs_changes, long), short)
    out = [NAN] * n
    for i in range(n):
        if math.isnan(num[i]) or math.isnan(den[i]):
            continue
        out[i] = 100.0 * _safe_div(num[i], den[i])
    return {"tsi": out}


@_computer("ULTOSC")
def _compute_ultosc(candles, fast, medium, slow):
    n = len(candles)
    out = [NAN] * n
    for i in range(1, n):

        def avg(period):
            bp = tr = 0.0
            for j in range(i - period + 1, i + 1):
                if j < 1:
                    continue
                pc = candles[j - 1].close
                bp += candles[j].close - min(candles[j].low, pc)
                tr += max(candles[j].high, pc) - min(candles[j].low, pc)
            return bp / period, tr / period

        bp1, tr1 = avg(fast)
        bp2, tr2 = avg(medium)
        bp3, tr3 = avg(slow)
        denom = 4 * tr1 + 2 * tr2 + tr3
        numer = 4 * bp1 + 2 * bp2 + bp3
        out[i] = 100.0 * _safe_div(numer, denom)
    return {"ultosc": out}


@_computer("CMO")
def _compute_cmo(candles, length, source):
    src = _source_series(candles, source)
    n = len(src)
    out = [NAN] * n
    for i in range(length, n):
        up = down = 0.0
        for j in range(i - length + 1, i + 1):
            diff = src[j] - src[j - 1]
            if diff > 0:
                up += diff
            else:
                down -= diff
        out[i] = 100.0 * _safe_div(up - down, up + down)
    return {"cmo": out}


@_computer("PPO")
def _compute_ppo(candles, fast, slow, signal, source):
    src = _source_series(candles, source)
    ef = _ema(src, fast)
    es = _ema(src, slow)
    ppo = [
        100.0 * _safe_div(f - s, s) for f, s in zip(ef, es, strict=True)
    ]
    first_valid = next((i for i, v in enumerate(ppo) if not math.isnan(v)), len(ppo))
    sig = [NAN] * len(ppo)
    if first_valid < len(ppo):
        sig[first_valid:] = _ema_over(ppo[first_valid:], signal)
    hist = [
        p - s if not (math.isnan(p) or math.isnan(s)) else NAN
        for p, s in zip(ppo, sig, strict=True)
    ]
    return {"ppo": ppo, "signal": sig, "histogram": hist}


@_computer("AO")
def _compute_ao(candles, fast, slow):
    hl2 = [(c.high + c.low) / 2 for c in candles]
    f = _sma(hl2, fast)
    s = _sma(hl2, slow)
    return {"ao": [a - b if not (math.isnan(a) or math.isnan(b)) else NAN for a, b in zip(f, s, strict=True)]}


@_computer("AROON")
def _compute_aroon(candles, length):
    n = len(candles)
    up = down = osc = [NAN] * n
    for i in range(length, n):
        window = candles[i - length : i + 1]
        highs = [c.high for c in window]
        lows = [c.low for c in window]
        hh = max(highs)
        ll = min(lows)
        bars_since_high = length - highs.index(hh)
        bars_since_low = length - lows.index(ll)
        up[i] = 100.0 * (length - bars_since_high) / length
        down[i] = 100.0 * (length - bars_since_low) / length
        osc[i] = up[i] - down[i]
    return {"up": up, "down": down, "oscillator": osc}


@_computer("DPO")
def _compute_dpo(candles, length, source):
    src = _source_series(candles, source)
    ma = _sma(src, length)
    displacement = length // 2 + 1
    out = [NAN] * len(src)
    for i in range(displacement, len(src)):
        if math.isnan(ma[i]):
            continue
        out[i] = src[i - displacement] - ma[i]
    return {"dpo": out}


@_computer("STOCHRSI")
def _compute_stochrsi(candles, rsi_length, stoch_length, d_length):
    src = [c.close for c in candles]
    n = len(src)
    gains, losses = [0.0], [0.0]
    for i in range(1, n):
        change = src[i] - src[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = _wilder(gains, rsi_length)
    avg_loss = _wilder(losses, rsi_length)
    rsi = [NAN] * n
    for i in range(n):
        if math.isnan(avg_loss[i]):
            continue
        if avg_loss[i] == 0:
            rsi[i] = 100.0
        elif avg_gain[i] == 0:
            rsi[i] = 0.0
        else:
            rsi[i] = 100.0 - 100.0 / (1.0 + _safe_div(avg_gain[i], avg_loss[i]))
    k = [NAN] * n
    for i in range(stoch_length - 1, n):
        window = rsi[i - stoch_length + 1 : i + 1]
        if any(math.isnan(v) for v in window):
            continue
        hh = max(window)
        ll = min(window)
        k[i] = 100.0 * _safe_div(rsi[i] - ll, hh - ll)
    first_valid = next((i for i, v in enumerate(k) if not math.isnan(v)), n)
    d = [NAN] * n
    if first_valid < n:
        d[first_valid:] = _sma(k[first_valid:], d_length)
    return {"k": k, "d": d}


# ---------------------------------------------------------------- volatility


@_computer("NATR")
def _compute_natr(candles, length):
    atr = _wilder(_true_range(candles), length)
    out = [NAN] * len(candles)
    for i, c in enumerate(candles):
        if math.isnan(atr[i]) or c.close == 0:
            continue
        out[i] = 100.0 * atr[i] / c.close
    return {"natr": out}


@_computer("STDDEV")
def _compute_stddev(candles, length, source):
    return {"stddev": _rolling_stddev(_source_series(candles, source), length)}


@_computer("DONCHIAN")
def _compute_donchian(candles, length):
    upper = _rolling_max([c.high for c in candles], length)
    lower = _rolling_min([c.low for c in candles], length)
    middle = [
        (u + lo) / 2 if not (math.isnan(u) or math.isnan(lo)) else NAN
        for u, lo in zip(upper, lower, strict=True)
    ]
    return {"upper": upper, "middle": middle, "lower": lower}


@_computer("KC")
def _compute_kc(candles, length, multiplier, source):
    src = _source_series(candles, source)
    mid = _ema(src, length)
    rng = _wilder(_true_range(candles), length)
    n = len(src)
    upper = [NAN] * n
    lower = [NAN] * n
    for i in range(n):
        if math.isnan(mid[i]) or math.isnan(rng[i]):
            continue
        upper[i] = mid[i] + multiplier * rng[i]
        lower[i] = mid[i] - multiplier * rng[i]
    return {"upper": upper, "middle": mid, "lower": lower}


@_computer("HV")
def _compute_hv(candles, length, periods_per_year, source):
    src = _source_series(candles, source)
    n = len(src)
    rets = [0.0] + [
        math.log(src[i] / src[i - 1]) if src[i - 1] > 0 and src[i] > 0 else NAN
        for i in range(1, n)
    ]
    out = [NAN] * n
    for i in range(length, n):
        window = rets[i - length + 1 : i + 1]
        if any(math.isnan(v) for v in window):
            continue
        mean = sum(window) / length
        var = sum((v - mean) ** 2 for v in window) / length
        out[i] = math.sqrt(var) * math.sqrt(periods_per_year) * 100.0
    return {"hv": out}


# ---------------------------------------------------------------- volume


@_computer("OBV")
def _compute_obv(candles):
    n = len(candles)
    out = [0.0] * n
    for i in range(1, n):
        vol = float(candles[i].volume or 0.0)
        if candles[i].close > candles[i - 1].close:
            out[i] = out[i - 1] + vol
        elif candles[i].close < candles[i - 1].close:
            out[i] = out[i - 1] - vol
        else:
            out[i] = out[i - 1]
    return {"obv": out}


def _mfm(c: Candle) -> float:
    rng = c.high - c.low
    if rng == 0:
        return 0.0
    return ((c.close - c.low) - (c.high - c.close)) / rng


@_computer("AD")
def _compute_ad(candles):
    n = len(candles)
    out = [0.0] * n
    for i in range(n):
        mfv = _mfm(candles[i]) * float(candles[i].volume or 0.0)
        out[i] = (out[i - 1] if i else 0.0) + mfv
    return {"ad": out}


@_computer("PVT")
def _compute_pvt(candles):
    n = len(candles)
    out = [0.0] * n
    for i in range(1, n):
        prev = candles[i - 1].close
        out[i] = out[i - 1] + (
            float(candles[i].volume or 0.0) * ((candles[i].close - prev) / prev)
            if prev
            else 0.0
        )
    return {"pvt": out}


@_computer("CMF")
def _compute_cmf(candles, length):
    n = len(candles)
    out = [NAN] * n
    for i in range(length - 1, n):
        mf_sum = 0.0
        vol_sum = 0.0
        for j in range(i - length + 1, i + 1):
            mf_sum += _mfm(candles[j]) * float(candles[j].volume or 0.0)
            vol_sum += float(candles[j].volume or 0.0)
        out[i] = _safe_div(mf_sum, vol_sum)
    return {"cmf": out}


@_computer("EOM")
def _compute_eom(candles, length, divisor):
    n = len(candles)
    out = [NAN] * n
    for i in range(length, n):
        window = candles[i - length : i + 1]
        hi = max(c.high for c in window)
        lo = min(c.low for c in window)
        rng = hi - lo
        if rng == 0:
            continue
        vol_sum = sum(float(c.volume or 0.0) for c in window)
        box_ratio = (vol_sum / divisor) / rng
        out[i] = box_ratio * (candles[i].close - candles[i - length].close)
    return {"eom": out}


@_computer("EFI")
def _compute_efi(candles, length):
    n = len(candles)
    raw = [0.0] * n
    for i in range(1, n):
        raw[i] = (candles[i].close - candles[i - 1].close) * float(candles[i].volume or 0.0)
    return {"efi": _ema(raw, length)}


@_computer("NVI")
def _compute_nvi(candles, length):
    n = len(candles)
    out = [1000.0] * n
    for i in range(1, n):
        prev_v = float(candles[i - 1].volume or 0.0)
        cur_v = float(candles[i].volume or 0.0)
        prev_c = candles[i - 1].close
        cur_c = candles[i].close
        if cur_v < prev_v and prev_c > 0:
            out[i] = out[i - 1] * (cur_c / prev_c)
        else:
            out[i] = out[i - 1]
    return {"nvi": _sma(out, length)}


# ---------------------------------------------------------------- statistics


@_computer("LINEARREG")
def _compute_linearreg(candles, length, source):
    value, slope, intercept = _linreg(_source_series(candles, source), length)
    return {"value": value, "slope": slope, "intercept": intercept}


def register_all() -> int:
    """No-op hook.

    Specs are merged by the caller; kernels are attached by the `@_computer`
    decorator as this module is imported. Kept as an explicit seam so callers
    read as `merge specs -> register kernels` and so a future refactor has a
    single place to hang registration.
    """
    return len(EXTENDED_SPECS)
