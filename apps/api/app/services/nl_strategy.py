"""Rule-based natural-language -> strategy-definition drafts.

Deterministic keyword/number extraction so the AI Builder works with zero
external dependencies. When an LLM key is configured, the /ai endpoint prefers
the LLM draft and falls back to this parser on any failure.
"""

import re

DEFAULT_SYMBOL = "NIFTY"

KNOWN_SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]

_TIMEFRAME_PATTERNS: list[tuple[str, str]] = [
    (r"\b1\s*min(?:ute)?s?\b|\b1m\b", "1m"),
    (r"\b5\s*min(?:ute)?s?\b|\b5m\b", "5m"),
    (r"\b15\s*min(?:ute)?s?\b|\b15m\b", "15m"),
    (r"\b30\s*min(?:ute)?s?\b|\b30m\b", "30m"),
    (r"\b1\s*hour\b|\bhourly\b|\b1h\b", "1h"),
    (r"\bdaily\b|\b1\s*day\b|\b1d\b", "1d"),
]


def _detect_timeframe(text: str) -> str:
    for pattern, tf in _TIMEFRAME_PATTERNS:
        if re.search(pattern, text):
            return tf
    return "5m"


def _detect_symbol(raw_text: str) -> str | None:
    upper = raw_text.upper()
    # Longest first: BANKNIFTY contains NIFTY as a substring.
    for symbol in sorted(KNOWN_SYMBOLS, key=len, reverse=True):
        if symbol in upper:
            return symbol
    return None


def _numbers_after(text: str, keyword_pattern: str) -> list[int]:
    m = re.search(keyword_pattern + r"[^\d]{0,12}(\d+)", text)
    return [int(m.group(1))] if m else []


def draft_definition(prompt: str) -> tuple[dict, list[str]]:
    """Extract a canonical definition v1 from plain English. Never raises."""
    text = prompt.lower()
    notes: list[str] = []

    timeframe = _detect_timeframe(text)
    symbol = _detect_symbol(prompt) or DEFAULT_SYMBOL

    definition: dict = {
        "version": 1,
        "timeframe": timeframe,
        "instrument": {"symbol": symbol},
        "variables": [],
        "indicators": [],
        "entry": {"logic": "ALL", "conditions": []},
        "exit": None,
        "risk": {"stop_loss_pct": None, "target_pct": None, "trailing_sl_pct": None},
        "position": {
            "direction": "long_only",
            "quantity_type": "fixed",
            "quantity": 10,
            "capital_pct": None,
        },
    }

    # --- stop-loss / target percentages -----------------------------------
    sl_match = re.search(r"stop\s*-?loss\D{0,12}(\d+(?:\.\d+)?)\s*%", text)
    tgt_match = re.search(r"target\D{0,12}(\d+(?:\.\d+)?)\s*%", text)
    trail_match = re.search(r"trail\w*\D{0,12}(\d+(?:\.\d+)?)\s*%", text)
    if sl_match or tgt_match or trail_match:
        definition["risk"] = {
            "stop_loss_pct": float(sl_match.group(1)) if sl_match else None,
            "target_pct": float(tgt_match.group(1)) if tgt_match else None,
            "trailing_sl_pct": float(trail_match.group(1)) if trail_match else None,
        }
        if not (sl_match and tgt_match):
            notes.append("Risk block partially detected — review stop-loss/target values.")

    # --- RSI ---------------------------------------------------------------
    if re.search(r"\brsi\b", text):
        length = (_numbers_after(text, r"\brsi\b") or [14])[0]
        oversold = 30
        overbought = 70
        os_m = re.search(r"(?:oversold|below)\D{0,10}(\d{2})", text)
        ob_m = re.search(r"(?:overbought|above)\D{0,10}(\d{2})", text)
        if os_m:
            oversold = int(os_m.group(1))
        if ob_m:
            overbought = int(ob_m.group(1))
        definition["indicators"].append(
            {"id": "rsi", "type": "RSI", "params": {"length": length}}
        )
        definition["entry"]["conditions"].append(
            {"left": {"kind": "indicator", "ref": "rsi"}, "op": "LT", "right": {"kind": "constant", "value": oversold}}
        )
        definition["exit"] = {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "rsi"}, "op": "GT", "right": {"kind": "constant", "value": overbought}}
            ],
        }
        return definition, notes

    # --- MACD --------------------------------------------------------------
    if re.search(r"\bmacd\b", text):
        definition["indicators"].append(
            {"id": "macd", "type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}}
        )
        below = bool(re.search(r"cross\w*\s+below|bearish", text))
        op_entry = "CROSS_BELOW" if below else "CROSS_ABOVE"
        op_exit = "CROSS_ABOVE" if below else "CROSS_BELOW"
        definition["entry"]["conditions"].append(
            {"left": {"kind": "indicator", "ref": "macd.histogram"}, "op": op_entry, "right": {"kind": "constant", "value": 0}}
        )
        definition["exit"] = {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "indicator", "ref": "macd.histogram"}, "op": op_exit, "right": {"kind": "constant", "value": 0}}
            ],
        }
        return definition, notes

    # --- Bollinger Bands ----------------------------------------------------
    if re.search(r"bollinger|\bbb\b", text):
        length = (_numbers_after(text, r"bollinger") or [20])[0]
        definition["indicators"].append(
            {"id": "bb", "type": "BBANDS", "params": {"length": length, "stddev": 2.0}}
        )
        definition["entry"]["conditions"].append(
            {"left": {"kind": "price", "price": "close"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "bb.lower"}}
        )
        definition["exit"] = {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "price", "price": "close"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "bb.middle"}}
            ],
        }
        return definition, notes

    # --- Supertrend ----------------------------------------------------------
    if re.search(r"supertrend", text):
        period = (_numbers_after(text, r"supertrend") or [10])[0]
        mult_m = re.search(r"supertrend\D{0,16}(\d(?:\.\d+)?)\D", text)
        multiplier = float(mult_m.group(1)) if mult_m else 3.0
        definition["indicators"].append(
            {"id": "st", "type": "SUPERTREND", "params": {"period": period, "multiplier": multiplier}}
        )
        definition["entry"]["conditions"].append(
            {"left": {"kind": "price", "price": "close"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "st.supertrend"}}
        )
        definition["exit"] = {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "price", "price": "close"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "st.supertrend"}}
            ],
        }
        return definition, notes

    # --- VWAP -----------------------------------------------------------------
    if re.search(r"\bvwap\b", text):
        definition["indicators"].append({"id": "vwap", "type": "VWAP", "params": {}})
        below = bool(re.search(r"below|under", text))
        definition["entry"]["conditions"].append(
            {"left": {"kind": "price", "price": "close"}, "op": "CROSS_BELOW" if below else "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "vwap"}}
        )
        definition["exit"] = {
            "logic": "ALL",
            "conditions": [
                {"left": {"kind": "price", "price": "close"}, "op": "CROSS_ABOVE" if below else "CROSS_BELOW", "right": {"kind": "indicator", "ref": "vwap"}}
            ],
        }
        return definition, notes

    # --- MA crossover (default fallback) --------------------------------------
    pair = re.search(r"\b(\d{1,3})\s*(?:[/&+,-]\s*|\band\s+)(\d{1,3})\b", text)
    fast_len, slow_len = (int(pair.group(1)), int(pair.group(2))) if pair else (9, 21)
    if pair is None:
        notes.append("No specific numbers found — defaulted to EMA 9/21 crossover.")
    ma_type = "SMA" if re.search(r"\bsma\b|\bsimple\b", text) else "EMA"
    prefix = "sma" if ma_type == "SMA" else "ema"
    definition["indicators"] = [
        {"id": f"{prefix}_fast", "type": ma_type, "params": {"length": fast_len}},
        {"id": f"{prefix}_slow", "type": ma_type, "params": {"length": slow_len}},
    ]
    definition["entry"]["conditions"].append(
        {"left": {"kind": "indicator", "ref": f"{prefix}_fast"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": f"{prefix}_slow"}}
    )
    short_side = bool(re.search(r"short|sell|bearish", text))
    if short_side:
        definition["position"]["direction"] = "both"
    definition["exit"] = {
        "logic": "ALL",
        "conditions": [
            {"left": {"kind": "indicator", "ref": f"{prefix}_fast"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": f"{prefix}_slow"}}
        ],
    }
    return definition, notes
