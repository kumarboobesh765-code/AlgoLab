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
                {"id": "bb", "type": "BBANDS", "params": {"length": 20, "stddev": 2.0}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "bb.upper"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "LT", "right": {"kind": "indicator", "ref": "bb.middle"}},
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
                {"id": "macd", "type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "macd.macd"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "macd.signal"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "macd.macd"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "macd.signal"}},
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
                    {"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "st.supertrend"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "LT", "right": {"kind": "indicator", "ref": "st.supertrend"}},
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
                    {"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "sma200"}},
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
    {
        "name": "Golden Cross",
        "description": "Classic long-term trend signal: buy when the 50 SMA crosses above the 200 SMA, sell on the cross below. Ingest daily history before backtesting.",
        "tags": ["trend", "long-term"],
        "definition": {
            "version": 1,
            "timeframe": "1d",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "sma_fast", "type": "SMA", "params": {"length": 50}},
                {"id": "sma_slow", "type": "SMA", "params": {"length": 200}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "sma_fast"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "sma_slow"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "sma_fast"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "sma_slow"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 5, "direction": "long_only"},
        },
    },
    {
        "name": "Bollinger Mean Reversion",
        "description": "Counter-trend play: buy when price falls below the lower Bollinger Band, exit when it recovers to the middle band.",
        "tags": ["mean-reversion", "volatility"],
        "definition": {
            "version": 1,
            "timeframe": "15m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "bb", "type": "BBANDS", "params": {"length": 20, "stddev": 2.0}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "LT", "right": {"kind": "indicator", "ref": "bb.lower"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "bb.middle"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
            "risk": {"stop_loss_pct": 2.0},
        },
    },
    {
        "name": "VWAP Intraday Pullback",
        "description": "Institutional favourite: go long when price crosses back above session VWAP, exit on the cross below.",
        "tags": ["intraday", "vwap"],
        "definition": {
            "version": 1,
            "timeframe": "5m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "vwap", "type": "VWAP", "params": {}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "vwap"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "vwap"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
            "risk": {"stop_loss_pct": 0.5, "target_pct": 1.0},
        },
    },
    {
        "name": "Stochastic Oversold Reversal",
        "description": "Buy when %K crosses above %D from oversold territory (<20), sell once %K reaches overbought (>80).",
        "tags": ["oscillator", "reversal"],
        "definition": {
            "version": 1,
            "timeframe": "15m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "stoch", "type": "STOCH", "params": {"k_length": 14, "d_length": 3}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "stoch.k"}, "op": "LT", "right": {"kind": "constant", "value": 20}},
                    {"left": {"kind": "indicator", "ref": "stoch.k"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "stoch.d"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "stoch.k"}, "op": "GT", "right": {"kind": "constant", "value": 80}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
        },
    },
    {
        "name": "ADX Trend Rider",
        "description": "Trend-following with a strength filter: enter only when ADX confirms a trending market (variable-driven threshold) and price is above Supertrend.",
        "tags": ["trend", "adx", "supertrend"],
        "definition": {
            "version": 1,
            "timeframe": "15m",
            "instrument": {"symbol": "NIFTY"},
            "variables": [{"name": "adx_min", "value": 25}],
            "indicators": [
                {"id": "adx", "type": "ADX", "params": {"length": 14}},
                {"id": "st", "type": "SUPERTREND", "params": {"period": 10, "multiplier": 3.0}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "adx.adx"}, "op": "GT", "right": {"kind": "variable", "name": "adx_min"}},
                    {"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "st.supertrend"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "price", "price": "close"}, "op": "LT", "right": {"kind": "indicator", "ref": "st.supertrend"}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
            "risk": {"trailing_sl_pct": 1.5},
        },
    },
    {
        "name": "MACD Histogram Momentum",
        "description": "Momentum continuation: buy when the MACD histogram flips positive while price holds above the 200 EMA; exit on the flip back below zero.",
        "tags": ["momentum", "trend"],
        "definition": {
            "version": 1,
            "timeframe": "5m",
            "instrument": {"symbol": "NIFTY"},
            "indicators": [
                {"id": "macd", "type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}},
                {"id": "ema200", "type": "EMA", "params": {"length": 200}},
            ],
            "entry": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "macd.histogram"}, "op": "CROSS_ABOVE", "right": {"kind": "constant", "value": 0}},
                    {"left": {"kind": "price", "price": "close"}, "op": "GT", "right": {"kind": "indicator", "ref": "ema200"}},
                ],
            },
            "exit": {
                "logic": "ALL",
                "conditions": [
                    {"left": {"kind": "indicator", "ref": "macd.histogram"}, "op": "CROSS_BELOW", "right": {"kind": "constant", "value": 0}},
                ],
            },
            "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
        },
    },
]


def get_templates() -> list[dict]:
    """Return all available strategy templates."""
    return TEMPLATES
