# Backtesting

How the backtest engine simulates a strategy definition over historical
candles, and how to run one from the API or the UI.

## Data source

Backtests read **stored candles only** (ingested via Tools → Data Manager).
If the requested range has no local history the run is rejected with a clear
message — the engine never silently fetches provider data, so any run can be
reproduced later against the exact same series.

## Execution semantics

| Rule | Behavior |
| --- | --- |
| Signal timing | Indicators/conditions are evaluated on a bar's **close** |
| Execution | Signals execute at the **next bar's open** — no same-bar lookahead |
| Stop loss | Intrabar; gap-aware fill `min(open, stop)` for longs (mirrored for shorts) |
| Target | Intrabar; gap-aware fill `max(open, target)` for longs |
| Same-bar stop + target | The **stop is assumed to hit first** (pessimistic) |
| Trailing stop | Ratchets on each bar's extreme **after** that bar's exit check, so a bar cannot stop itself out on its own high/low; exit reason becomes `trailing_stop` once ratcheted |
| Costs | Charged per side as % of traded value; included in every trade's P&L |
| End of data | Open positions force-close at the last bar's close (`end_of_data`) |
| Direction | `long_only` / `short_only` / `both` (`both` = stop-and-reverse on exit signals) |
| Sizing | `fixed` quantity or `capital_pct` of current equity at entry |

## Metrics

Each run stores a summary plus the full trade list and per-bar equity curve:

- Net P&L, return %, final equity, total costs
- Trades, win rate, profit factor, avg/largest win & loss
- Max drawdown (peak-to-trough on the equity curve)
- Sharpe ratio (per-bar returns annualized by timeframe)

Accounting identity: `net_pnl == Σ trade.pnl` — entry **and** exit costs are
included in each trade's P&L, and the final equity point reflects the
force-close cost. Pinned by tests.

## API

```bash
POST /api/v1/backtests
{
  "strategy_id": "<uuid>",
  "start": "2026-08-10",        # optional, default: end - 30d
  "end": "2026-08-14",          # optional, default: today
  "initial_capital": 100000,
  "costs_pct": 0.03
}
# → 201 { id, status: "completed", version_number, config, result_summary }
#    result_summary = { summary, equity_curve: [{time, equity}], trades: [...] }

GET  /api/v1/backtests?strategy_id=<uuid>   # run history (newest first)
GET  /api/v1/backtests/{run_id}             # full detail incl. trades
```

Errors: `400` when the strategy has no definition, the range is invalid, or no
stored candles exist; runs that fail mid-engine are persisted with
`status: "failed"` and an error message. All routes are user-scoped.

Runs pin `version_number` — the immutable strategy version they executed.

## UI

The **Backtest** page offers a run form (strategy, date range, capital,
costs), twelve metric cards, an SVG equity curve with the initial-capital
baseline, a trade table with color-coded exit reasons, and the run history.
The Strategies page deep-links with `?strategy=<id>` preselected.
