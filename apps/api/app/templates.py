"""Pre-built strategy catalog ("Explore") — Indian-market reference algos.

Each entry is a complete canonical definition plus presentation metadata
(category, complexity, min capital). Read-only reference data.

Definitions are built through small helpers so every entry stays valid
against the canonical schema (v1).
"""

from typing import Any


def _cond(
    left: dict[str, Any],
    op: str,
    right: dict[str, Any],
) -> dict[str, Any]:
    return {"left": left, "op": op, "right": right}


def _price(which: str = "close") -> dict[str, Any]:
    return {"kind": "price", "price": which}


def _const(v: float) -> dict[str, Any]:
    return {"kind": "constant", "value": v}


def _ind(ref: str) -> dict[str, Any]:
    return {"kind": "indicator", "ref": ref}


def _var(name: str) -> dict[str, Any]:
    return {"kind": "variable", "name": name}


def _group(*conditions: dict[str, Any], logic: str = "ALL") -> dict[str, Any]:
    return {"logic": logic, "conditions": list(conditions)}


def _indicator_algo(
    *,
    timeframe: str,
    indicators: list[dict],
    entry: list[dict],
    exit_: list[dict] | None,
    quantity: int = 10,
    direction: str = "long_only",
    risk: dict | None = None,
    variables: list[dict] | None = None,
) -> dict:
    d: dict[str, Any] = {
        "version": 1,
        "timeframe": timeframe,
        "instrument": {"symbol": "NIFTY"},
        "indicators": indicators,
        "entry": _group(*entry),
        "position": {"quantity_type": "fixed", "quantity": quantity, "direction": direction},
    }
    if exit_:
        d["exit"] = _group(*exit_)
    if risk:
        d["risk"] = risk
    if variables:
        d["variables"] = variables
    return d


def _legs(
    *legs: tuple[str, str, int, int],
    underlying: str = "NIFTY",
) -> dict:
    """Legs spec: (action, option_type, strike_offset, lots)."""
    return {
        "version": 1,
        "timeframe": "1d",
        "builder": "legs",
        "instrument": {"symbol": underlying, "exchange": "NSE", "segment": "options"},
        "legs": [
            {"action": a, "option_type": ot, "strike_offset": off, "lots": lots}
            for (a, ot, off, lots) in legs
        ],
        "entry": _group(_cond(_price(), "GT", _const(0))),
        "exit": _group(_cond(_price(), "GT", _const(0))),
        "position": {"quantity_type": "fixed", "quantity": 1, "direction": "long_only"},
    }


def _algo(
    id: str,
    name: str,
    category: str,
    description: str,
    tags: list[str],
    complexity: str,
    min_capital: int,
    underlying: str,
    definition: dict,
) -> dict:
    return {
        "id": id,
        "name": name,
        "category": category,
        "description": description,
        "tags": tags,
        "complexity": complexity,
        "min_capital": min_capital,
        "underlying": underlying,
        "definition": definition,
    }


# ---------------------------------------------------------------- categories

CATEGORIES = [
    {"id": "all", "label": "All", "description": "Every prebuilt algo"},
    {"id": "option-buying", "label": "Option Buying", "description": "Debit spreads & long gamma plays"},
    {"id": "option-selling", "label": "Option Selling", "description": "Theta harvesting with defined risk"},
    {"id": "credit-spread", "label": "Credit Spread", "description": "Range-bound premium collection"},
    {"id": "short-straddle", "label": "Short Straddle", "description": "ATM volatility selling"},
    {"id": "short-strangle", "label": "Short Strangle", "description": "OTM wings, wider breakevens"},
    {"id": "expiry-day", "label": "Expiry Day", "description": "Weekly expiry special situations"},
    {"id": "intraday", "label": "Intraday", "description": "5m–15m index scalping systems"},
    {"id": "swing", "label": "Swing", "description": "Daily-timeframe trend riding"},
]

# ---------------------------------------------------------------- catalog

CATALOG: list[dict] = [
    # ---------------- intraday (index scalping systems) ----------------
    _algo(
        "ema-crossover-9-21", "EMA Crossover 9/21", "intraday",
        "Classic dual-EMA scalper. Long when fast EMA crosses above slow, exits on cross below.",
        ["trend", "beginner"], "beginner", 100_000, "NIFTY",
        _indicator_algo(
            timeframe="5m",
            indicators=[
                {"id": "f", "type": "EMA", "params": {"length": 9}},
                {"id": "s", "type": "EMA", "params": {"length": 21}},
            ],
            entry=[_cond(_ind("f"), "CROSS_ABOVE", _ind("s"))],
            exit_=[_cond(_ind("f"), "CROSS_BELOW", _ind("s"))],
        ),
    ),
    _algo(
        "vwap-reclaim", "VWAP Reclaim", "intraday",
        "Institutional favourite: long when price reclaims session VWAP, out on the loss of it.",
        ["intraday", "vwap"], "beginner", 100_000, "NIFTY",
        _indicator_algo(
            timeframe="5m",
            indicators=[{"id": "vw", "type": "VWAP", "params": {}}],
            entry=[_cond(_price(), "CROSS_ABOVE", _ind("vw"))],
            exit_=[_cond(_price(), "CROSS_BELOW", _ind("vw"))],
            risk={"stop_loss_pct": 0.4, "target_pct": 0.8},
        ),
    ),
    _algo(
        "supertrend-follower-10x3", "Supertrend Follower 10×3", "intraday",
        "Rides the classic Supertrend(10,3). Long above the band, flat below it.",
        ["trend", "atr"], "beginner", 100_000, "NIFTY",
        _indicator_algo(
            timeframe="15m",
            indicators=[{"id": "st", "type": "SUPERTREND", "params": {"period": 10, "multiplier": 3.0}}],
            entry=[_cond(_price(), "GT", _ind("st.supertrend"))],
            exit_=[_cond(_price(), "LT", _ind("st.supertrend"))],
        ),
    ),
    _algo(
        "rsi-mean-reversion", "RSI Mean Reversion", "intraday",
        "Buys oversold dips (RSI<30), books profit into strength (RSI>70). Hard stop included.",
        ["mean-reversion"], "beginner", 100_000, "NIFTY",
        _indicator_algo(
            timeframe="15m",
            indicators=[{"id": "r", "type": "RSI", "params": {"length": 14}}],
            entry=[_cond(_ind("r"), "LT", _const(30))],
            exit_=[_cond(_ind("r"), "GT", _const(70))],
            risk={"stop_loss_pct": 3.0, "target_pct": 6.0},
        ),
    ),
    _algo(
        "bb-squeeze-breakout", "Bollinger Breakout", "intraday",
        "Momentum entry when price closes above the upper band; trails with a 2% stop.",
        ["breakout", "volatility"], "intermediate", 100_000, "NIFTY",
        _indicator_algo(
            timeframe="5m",
            indicators=[{"id": "bb", "type": "BBANDS", "params": {"length": 20, "stddev": 2.0}}],
            entry=[_cond(_price(), "GT", _ind("bb.upper"))],
            exit_=[_cond(_price(), "LT", _ind("bb.middle"))],
            risk={"trailing_sl_pct": 2.0},
        ),
    ),
    _algo(
        "macd-momentum-ema200", "MACD Momentum + 200 EMA", "intraday",
        "Continuation setup: histogram flips positive while price holds above the 200 EMA.",
        ["momentum", "trend"], "intermediate", 150_000, "NIFTY",
        _indicator_algo(
            timeframe="5m",
            indicators=[
                {"id": "m", "type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
                {"id": "e2", "type": "EMA", "params": {"length": 200}},
            ],
            entry=[_cond(_ind("m.histogram"), "CROSS_ABOVE", _const(0)), _cond(_price(), "GT", _ind("e2"))],
            exit_=[_cond(_ind("m.histogram"), "CROSS_BELOW", _const(0))],
        ),
    ),
    _algo(
        "adx-supertrend-rider", "ADX Trend Rider", "intraday",
        "Only trades when ADX confirms a real trend (variable threshold) above Supertrend.",
        ["trend", "adx"], "advanced", 150_000, "NIFTY",
        _indicator_algo(
            timeframe="15m",
            indicators=[
                {"id": "ax", "type": "ADX", "params": {"length": 14}},
                {"id": "st", "type": "SUPERTREND", "params": {"period": 10, "multiplier": 3.0}},
            ],
            entry=[_cond(_ind("ax.adx"), "GT", _var("adx_min")), _cond(_price(), "GT", _ind("st.supertrend"))],
            exit_=[_cond(_price(), "LT", _ind("st.supertrend"))],
            variables=[{"name": "adx_min", "value": 25}],
            risk={"trailing_sl_pct": 1.5},
        ),
    ),
    _algo(
        "stochastic-reversal", "Stochastic Oversold Reversal", "intraday",
        "%K crossing %D from oversold (<20); exits into overbought (>80).",
        ["oscillator", "reversal"], "intermediate", 100_000, "NIFTY",
        _indicator_algo(
            timeframe="15m",
            indicators=[{"id": "so", "type": "STOCH", "params": {"k_length": 14, "d_length": 3}}],
            entry=[_cond(_ind("so.k"), "LT", _const(20)), _cond(_ind("so.k"), "CROSS_ABOVE", _ind("so.d"))],
            exit_=[_cond(_ind("so.k"), "GT", _const(80))],
        ),
    ),

    # ---------------- swing (daily trend systems) ----------------
    _algo(
        "golden-cross", "Golden Cross 50/200", "swing",
        "The classic regime filter: long when the 50 SMA crosses above the 200 SMA. Ingest 1d history before backtesting.",
        ["trend", "long-term"], "beginner", 200_000, "NIFTY",
        _indicator_algo(
            timeframe="1d",
            indicators=[
                {"id": "f", "type": "SMA", "params": {"length": 50}},
                {"id": "s", "type": "SMA", "params": {"length": 200}},
            ],
            entry=[_cond(_ind("f"), "CROSS_ABOVE", _ind("s"))],
            exit_=[_cond(_ind("f"), "CROSS_BELOW", _ind("s"))],
            quantity=5,
        ),
    ),
    _algo(
        "macd-daily-swing", "MACD Daily Swing", "swing",
        "Position swings on the daily MACD signal cross with a 4% trailing stop.",
        ["swing", "momentum"], "intermediate", 200_000, "NIFTY",
        _indicator_algo(
            timeframe="1d",
            indicators=[{"id": "m", "type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}],
            entry=[_cond(_ind("m.macd"), "CROSS_ABOVE", _ind("m.signal"))],
            exit_=[_cond(_ind("m.macd"), "CROSS_BELOW", _ind("m.signal"))],
            quantity=5, risk={"trailing_sl_pct": 4.0},
        ),
    ),
    _algo(
        "roc-momentum-swing", "ROC Momentum Swing", "swing",
        "Buys 10-day rate-of-change strength above a variable threshold; exits on momentum fade.",
        ["swing", "momentum"], "intermediate", 200_000, "NIFTY",
        _indicator_algo(
            timeframe="1d",
            indicators=[{"id": "rc", "type": "ROC", "params": {"length": 10}}],
            entry=[_cond(_ind("rc"), "CROSS_ABOVE", _var("roc_min"))],
            exit_=[_cond(_ind("rc"), "CROSS_BELOW", _const(0))],
            variables=[{"name": "roc_min", "value": 2.0}],
            quantity=5, risk={"stop_loss_pct": 5.0, "target_pct": 12.0},
        ),
    ),
    _algo(
        "trend-pullback-50ema", "Trend Pullback (50 EMA)", "swing",
        "Daily uptrend pullback: price above rising 50 EMA, RSI dips below 45 to enter the dip.",
        ["swing", "pullback"], "intermediate", 200_000, "NIFTY",
        _indicator_algo(
            timeframe="1d",
            indicators=[
                {"id": "e5", "type": "EMA", "params": {"length": 50}},
                {"id": "r", "type": "RSI", "params": {"length": 14}},
            ],
            entry=[_cond(_price(), "GT", _ind("e5")), _cond(_ind("r"), "LT", _const(45))],
            exit_=[_cond(_ind("r"), "GT", _const(75))],
            quantity=5, risk={"stop_loss_pct": 4.0, "target_pct": 10.0},
        ),
    ),

    # ---------------- option buying (debit) ----------------
    _algo(
        "bull-call-spread-nifty", "NIFTY Bull Call Spread", "option-buying",
        "Buy ATM CE, sell 1-strike-higher CE. Capped-risk bullish debit spread.",
        ["options", "bullish"], "beginner", 65_000, "NIFTY",
        _legs(("buy", "CE", 0, 65), ("sell", "CE", 1, 65)),
    ),
    _algo(
        "bear-put-spread-nifty", "NIFTY Bear Put Spread", "option-buying",
        "Buy ATM PE, sell 1-strike-lower PE. Capped-risk bearish debit spread.",
        ["options", "bearish"], "beginner", 65_000, "NIFTY",
        _legs(("buy", "PE", 0, 65), ("sell", "PE", -1, 65)),
    ),
    _algo(
        "long-straddle-nifty", "NIFTY Long Straddle", "option-buying",
        "ATM CE + ATM PE. Profits from a large move either way — a pure volatility play.",
        ["options", "volatile"], "intermediate", 90_000, "NIFTY",
        _legs(("buy", "CE", 0, 65), ("buy", "PE", 0, 65)),
    ),
    _algo(
        "long-strangle-nifty", "NIFTY Long Strangle", "option-buying",
        "Cheaper vol play: buy 1-strike OTM CE and PE. Needs a bigger move than the straddle.",
        ["options", "volatile"], "intermediate", 60_000, "NIFTY",
        _legs(("buy", "CE", 1, 65), ("buy", "PE", -1, 65)),
    ),
    _algo(
        "call-ratio-backspread-nifty", "Call Ratio Backspread", "option-buying",
        "Sell 1 ATM CE, buy 2 OTM CE. Unlimited upside with a small capped-risk zone below.",
        ["options", "bullish", "ratio"], "advanced", 80_000, "NIFTY",
        _legs(("sell", "CE", 0, 65), ("buy", "CE", 1, 130)),
    ),
    _algo(
        "bull-call-spread-banknifty", "BANKNIFTY Bull Call Spread", "option-buying",
        "Same debit-spread structure sized for BANKNIFTY lots.",
        ["options", "bullish"], "beginner", 55_000, "BANKNIFTY",
        _legs(("buy", "CE", 0, 30), ("sell", "CE", 1, 30), underlying="BANKNIFTY"),
    ),

    # ---------------- option selling / credit ----------------
    _algo(
        "bull-put-spread-nifty", "NIFTY Bull Put Spread", "credit-spread",
        "Sell OTM PE, buy further OTM PE. Collect theta while defining max loss.",
        ["options", "credit", "bullish"], "intermediate", 80_000, "NIFTY",
        _legs(("sell", "PE", -1, 65), ("buy", "PE", -2, 65)),
    ),
    _algo(
        "bear-call-spread-nifty", "NIFTY Bear Call Spread", "credit-spread",
        "Sell OTM CE, buy further OTM CE. Premium collection with a bearish/neutral view.",
        ["options", "credit", "bearish"], "intermediate", 80_000, "NIFTY",
        _legs(("sell", "CE", 1, 65), ("buy", "CE", 2, 65)),
    ),
    _algo(
        "iron-condor-nifty", "NIFTY Iron Condor", "credit-spread",
        "OTM call spread + OTM put spread. The canonical range-bound income trade.",
        ["options", "credit", "range"], "intermediate", 120_000, "NIFTY",
        _legs(
            ("sell", "CE", 1, 65), ("sell", "PE", -1, 65),
            ("buy", "CE", 2, 65), ("buy", "PE", -2, 65),
        ),
    ),
    _algo(
        "iron-condor-banknifty", "BANKNIFTY Iron Condor", "credit-spread",
        "Wider-winged condor on BANKNIFTY for larger absolute credit.",
        ["options", "credit", "range"], "advanced", 110_000, "BANKNIFTY",
        _legs(
            ("sell", "CE", 1, 30), ("sell", "PE", -1, 30),
            ("buy", "CE", 2, 30), ("buy", "PE", -2, 30),
            underlying="BANKNIFTY",
        ),
    ),

    # ---------------- short straddle / strangle ----------------
    _algo(
        "nifty-short-straddle", "NIFTY Short Straddle", "short-straddle",
        "Sell ATM CE + ATM PE. Maximum theta, unlimited tail risk — respect the margin.",
        ["options", "volatility", "credit"], "advanced", 150_000, "NIFTY",
        _legs(("sell", "CE", 0, 65), ("sell", "PE", 0, 65)),
    ),
    _algo(
        "banknifty-short-straddle", "BANKNIFTY Short Straddle", "short-straddle",
        "Higher-premium ATM straddle on BANKNIFTY. Strictly for defined-margin accounts.",
        ["options", "volatility", "credit"], "advanced", 140_000, "BANKNIFTY",
        _legs(("sell", "CE", 0, 30), ("sell", "PE", 0, 30), underlying="BANKNIFTY"),
    ),
    _algo(
        "nifty-short-strangle", "NIFTY Short Strangle", "short-strangle",
        "Sell 1-strike OTM wings. More breathing room than the straddle, smaller credit.",
        ["options", "volatility", "credit"], "advanced", 130_000, "NIFTY",
        _legs(("sell", "CE", 1, 65), ("sell", "PE", -1, 65)),
    ),
    _algo(
        "banknifty-short-strangle", "BANKNIFTY Short Strangle", "short-strangle",
        "2-strike OTM wings on BANKNIFTY for a wider profit zone.",
        ["options", "volatility", "credit"], "advanced", 125_000, "BANKNIFTY",
        _legs(("sell", "CE", 2, 30), ("sell", "PE", -2, 30), underlying="BANKNIFTY"),
    ),

    # ---------------- iron butterfly ----------------
    _algo(
        "iron-butterfly-nifty", "NIFTY Iron Butterfly", "option-selling",
        "Short ATM straddle protected by wings. Max profit exactly at ATM expiry.",
        ["options", "range", "credit"], "advanced", 120_000, "NIFTY",
        _legs(
            ("sell", "CE", 0, 65), ("sell", "PE", 0, 65),
            ("buy", "CE", 1, 65), ("buy", "PE", -1, 65),
        ),
    ),
    _algo(
        "iron-butterfly-banknifty", "BANKNIFTY Iron Butterfly", "option-selling",
        "Defined-risk ATM butterfly on BANKNIFTY.",
        ["options", "range", "credit"], "advanced", 115_000, "BANKNIFTY",
        _legs(
            ("sell", "CE", 0, 30), ("sell", "PE", 0, 30),
            ("buy", "CE", 1, 30), ("buy", "PE", -1, 30),
            underlying="BANKNIFTY",
        ),
    ),

    # ---------------- expiry-day specials ----------------
    _algo(
        "theta-harvest-weekly", "Theta Harvest Weekly", "expiry-day",
        "Thursday-expiry credit structure: sell 1-strike wings designed to decay to zero.",
        ["options", "theta", "weekly"], "advanced", 100_000, "NIFTY",
        _legs(("sell", "CE", 1, 65), ("sell", "PE", -1, 65)),
    ),
    _algo(
        "expiry-iron-fly-wide", "Expiry Day Wide Iron Fly", "expiry-day",
        "Wide-winged fly for expiry afternoon — cheap wings cap gamma damage.",
        ["options", "theta", "range"], "advanced", 110_000, "NIFTY",
        _legs(
            ("sell", "CE", 0, 65), ("sell", "PE", 0, 65),
            ("buy", "CE", 2, 65), ("buy", "PE", -2, 65),
        ),
    ),
    _algo(
        "directional-butterfly-ce", "Directional CE Butterfly", "expiry-day",
        "Buy ITM CE, sell 2 ATM CE, buy OTM CE. Low-cost directional lottery with defined risk.",
        ["options", "bullish", "weekly"], "advanced", 45_000, "NIFTY",
        _legs(
            ("buy", "CE", -1, 65), ("sell", "CE", 0, 130), ("buy", "CE", 1, 65),
        ),
    ),

    # ---------------- banknifty specials ----------------
    _algo(
        "banknifty-bear-put-spread", "BANKNIFTY Bear Put Spread", "option-buying",
        "Bearish debit spread sized for BANKNIFTY.",
        ["options", "bearish"], "beginner", 55_000, "BANKNIFTY",
        _legs(("buy", "PE", 0, 30), ("sell", "PE", -1, 30), underlying="BANKNIFTY"),
    ),
    _algo(
        "banknifty-ratio-call-spread", "BANKNIFTY Ratio Call Spread", "credit-spread",
        "Sell 2 OTM calls against 1 ATM long call — financed upside with a capped zone.",
        ["options", "ratio", "neutral"], "advanced", 85_000, "BANKNIFTY",
        _legs(("buy", "CE", 0, 30), ("sell", "CE", 1, 60), underlying="BANKNIFTY"),
    ),
]


def get_templates() -> list[dict]:
    """Backward-compatible template list (enriched entries)."""
    return CATALOG


def get_explore() -> dict:
    """Explore-gallery payload: category facets + full algo catalog."""
    counts: dict[str, int] = {}
    for a in CATALOG:
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    categories = [{**c, "count": counts.get(c["id"], 0)} for c in CATEGORIES]
    return {"categories": categories, "algos": CATALOG, "total": len(CATALOG)}
