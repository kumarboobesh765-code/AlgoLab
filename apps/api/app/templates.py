"""Pre-built strategy templates.

Each template is a complete canonical definition that users can start from.
They are read-only reference data — never mutated at runtime.
"""

TEMPLATES = [
    {
        "name": "EMA Crossover",
        "description": "Classic dual exponential moving average crossover. Enters long when fast EMA crosses above slow EMA, exits on cross below.",
        "tags": ["trend", "beginner"],
        "definition": {
            "version": 1,
            "timeframe": "5m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "ema_fast", "type": "EMA", "params": {"length": 9}},
                {"id": "ema_slow", "type": "EMA", "params": {"length": 21}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "ema_fast"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "ema_slow"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "ema_fast"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "ema_slow"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
        },
    },
    {
        "name": "RSI Mean Reversion",
        "description": "Buys when RSI drops below oversold (30) and sells when it rises above overbought (70).",
        "tags": ["mean-reversion", "oscillator"],
        "definition": {
            "version": 1,
            "timeframe": "15m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "rsi", "type": "RSI", "params": {"length": 14}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "rsi"}, "op": "LT", "right": {"kind": "constant", "value": 30}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "rsi"}, "op": "GT", "right": {"kind": "constant", "value": 70}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
            "risk": {"stop_loss_pct": 3.0, "target_pct": 6.0},
        },
    },
    {
        "name": "Bollinger Breakout",
        "description": "Enters long when price breaks above the upper Bollinger Band (momentum), exits when it drops below the middle band.",
        "tags": ["breakout", "volatility"],
        "definition": {
            "version": 1,
            "timeframe": "5m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "bb_mid", "type": "BBANDS", "params": {"length": 20, "std_dev": 2.0}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "source": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "bb_mid", "output": "upper"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "source": "close"}, "op": "LT", "right": {"kind": "indicator", "ref": "bb_mid", "output": "middle"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
            "risk": {"trailing_sl_pct": 2.0},
        },
    },
    {
        "name": "MACD Signal Crossover",
        "description": "Long when MACD line crosses above its signal line, exits on cross below.",
        "tags": ["trend", "momentum"],
        "definition": {
            "version": 1,
            "timeframe": "5m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "macd", "type": "MACD", "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "macd", "output": "macd"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "macd", "output": "signal"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "macd", "output": "macd"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "macd", "output": "signal"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
        },
    },
    {
        "name": "Supertrend Trend Following",
        "description": "Follows the Supertrend indicator. Long when price is above Supertrend, exits when price drops below.",
        "tags": ["trend", "atr"],
        "definition": {
            "version": 1,
            "timeframe": "15m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "st", "type": "SUPERTREND", "params": {"period": 10, "multiplier": 3.0}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "source": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "st"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "source": "close"}, "op": "LT", "right": {"kind": "indicator", "ref": "st"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
        },
    },
    {
        "name": "SMA Trend Filter",
        "description": "Enters long when price is above the 200 SMA (uptrend), uses RSI for entry timing.",
        "tags": ["trend", "multi-indicator"],
        "definition": {
            "version": 1,
            "timeframe": "5m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "sma200", "type": "SMA", "params": {"length": 200}},
                {"id": "rsi", "type": "RSI", "params": {"length": 14}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "source": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "sma200"}},
                    {"left": {"kind": "indicator", "ref": "rsi"}, "op": "LT", "right": {"kind": "constant", "value": 40}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "rsi"}, "op": "GT", "right": {"kind": "constant", "value": 75}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
            "risk": {"stop_loss_pct": 2.0},
        },
    },
]


def get_templates() -> list[dict]:
    """Return all available strategy templates."""
    return TEMPLATES
