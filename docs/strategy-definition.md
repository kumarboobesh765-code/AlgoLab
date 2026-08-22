# Strategy Definition (canonical schema v1)

One Strategy Definition is the contract between every builder and every engine.
Visual Builder, Technical Builder, Strategy Flow and future AI Builder all
compile to this JSON; the backtest engine and paper engine consume it unchanged.

```json
{
  "version": 1,
  "timeframe": "5m",
  "instrument": {"symbol": "NIFTY", "exchange": "NSE", "segment": "index"},
  "variables": [
    {"name": "fast_len", "value": 9}
  ],
  "indicators": [
    {"id": "ema_fast", "type": "EMA", "params": {"length": {"var": "fast_len"}}},
    {"id": "ema_slow", "type": "EMA", "params": {"length": 21}}
  ],
  "entry": {
    "logic": "ALL",
    "conditions": [
      {"left": {"kind": "indicator", "ref": "ema_fast"},
       "op": "CROSS_ABOVE",
       "right": {"kind": "indicator", "ref": "ema_slow"}}
    ]
  },
  "exit": {
    "logic": "ANY",
    "conditions": [
      {"left": {"kind": "indicator", "ref": "ema_fast"},
       "op": "CROSS_BELOW",
       "right": {"kind": "indicator", "ref": "ema_slow"}}
    ]
  },
  "risk": {"stop_loss_pct": 1.0, "target_pct": 2.0},
  "position": {"direction": "long_only", "quantity_type": "fixed", "quantity": 1}
}
```

## Rules

- `timeframe`: one of `1m 5m 15m 30m 1h 1d`.
- Indicator `id`s are unique lowercase snake_case; `type` must exist in the
  indicator registry (`GET /api/v1/quant/catalog`).
- Params may be literals or variable references (`{"var": "name"}`).
- Condition operands are tagged by `kind`:

| kind | fields | resolves to |
| --- | --- | --- |
| `price` | `price` | open/high/low/close/volume/hl2/hlc3/ohlc4 series |
| `constant` | `value` | scalar broadcast to all bars |
| `variable` | `name` | strategy variable value |
| `indicator` | `ref` | `<id>.<output>` (output optional when single) |
| `formula` | `expression` | safe arithmetic expression evaluated per bar |

- Operators: `GT LT GTE LTE CROSS_ABOVE CROSS_BELOW`. Crosses compare the
  previous completed pair of bars; touching exactly does not trigger.
- Groups nest with `ALL`/`ANY` logic up to depth 3.
- Formulas support `+ - * / % ^`, parentheses, unary minus and the functions
  `abs min max sqrt log round`. They never use `eval`; unknown identifiers,
  keywords or characters are rejected. Division by zero yields NaN for that bar.
- Validation distinguishes **errors** (invalid) from **warnings** (unused
  indicators/variables).

## Supported indicators

SMA, EMA, WMA, RSI, MACD, BBANDS, ATR, SUPERTREND, STOCH, ADX, VWAP (session-
anchored IST), ROC. All kernels are pure Python, NaN-padded during warm-up and
deterministic. The catalog endpoint exposes params/outputs/constraints so
builders can render editors automatically.

## API

- `GET /api/v1/quant/catalog` — machine-readable indicator catalog.
- `POST /api/v1/quant/validate` — `{valid, errors[], warnings[]}`.
- `POST /api/v1/quant/preview?bars=500` — evaluates a definition over recent
  candles from the active provider and reports signal counts plus each
  indicator's latest value. Demo-provider responses carry `is_demo: true`.
