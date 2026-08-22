# Database

## Engines

| Store | Purpose |
| --- | --- |
| PostgreSQL 16 + TimescaleDB | Relational data + time-series candle hypertables |
| SQLite (dev fallback) | Zero-infra local development; same SQLAlchemy models |
| Redis | Option-chain cache, market/strategy state |

## Complete schema (4 migrations)

### Migration 0001 — Core

```
users
  id (UUID PK), email (unique), hashed_password, full_name, role, is_active, created_at

strategies
  id (UUID PK), user_id -> users, name, description, exchange, underlying,
  instrument, strategy_type, status, tags (json), definition (json),
  current_version (int), created_at, updated_at

strategy_versions                    -- immutable snapshots
  id (UUID PK), strategy_id -> strategies, version_number, definition (json),
  changelog, created_at
  UNIQUE (strategy_id, version_number)

paper_accounts                       -- virtual money
  id (UUID PK), user_id -> users, name, initial_capital, cash_balance,
  status, created_at

backtest_runs
  id (UUID PK), strategy_id -> strategies, user_id -> users, version_number,
  status, config (json), result_summary (json),
  started_at, finished_at, created_at
```

### Migration 0002 — Market data

```
instrument_master
  id (UUID PK), security_id, exchange, segment (index|equity|futures|options),
  exchange_segment, symbol, name, underlying, instrument_type,
  expiry_code, expiry, strike, option_type, lot_size, tick_size, status
  UNIQUE (exchange, segment, security_id)

index_candles / equity_candles / futures_candles / options_candles
  instrument_id, interval ('1m'...'1d'), time (UTC),
  open, high, low, close, volume, oi
  PK (instrument_id, interval, time)
  -- TimescaleDB hypertables on PostgreSQL
```

### Migration 0003 — Forward testing

```
paper_positions
  id (UUID PK), account_id -> paper_accounts, strategy_id -> strategies,
  direction (long|short), quantity, entry_price, entry_time,
  stop_price, target_price, trail_pct, trailed (int), extreme,
  status (open|closed), exit_price, exit_time, exit_reason, realized_pnl,
  created_at

paper_orders
  id (UUID PK), account_id -> paper_accounts, strategy_id -> strategies,
  position_id, side (BUY|SELL), quantity, filled_price, reason,
  signal_time, created_at

forward_test_runs
  id (UUID PK), user_id -> users, strategy_id -> strategies,
  account_id -> paper_accounts, version_number, status (running|paused|stopped),
  last_bar_time, pending_action (entry_long|entry_short|exit|reverse_long|reverse_short),
  last_message, started_at, stopped_at, created_at
```

### Migration 0004 — Optimization

```
optimization_runs
  id (UUID PK), user_id -> users, strategy_id -> strategies,
  method (grid|walk_forward), param_ranges (json), start, end,
  train_pct, target_metric, costs_pct, status,
  total_combinations, completed_combinations,
  best_params (json), best_metrics (json), error,
  started_at, finished_at, created_at

optimization_results
  id (UUID PK), run_id -> optimization_runs, rank, params (json),
  net_pnl, return_pct, win_rate, profit_factor, max_drawdown_pct,
  sharpe_ratio, total_trades,
  train_sharpe, test_sharpe,
  status, error, created_at
```

## Conventions

- UUID primary keys (`sqlalchemy.Uuid`, native UUID on PostgreSQL).
- `JSONType` column type: JSONB on PostgreSQL, JSON on SQLite.
- Every user-owned row carries `user_id` with `ON DELETE CASCADE` — multi-user isolation is enforced in queries, not assumed.
- Strategy definition changes auto-create a new `strategy_versions` row.
- Candle timestamps are normalized to **UTC** before insert; IST is a presentation concern.
- OHLCV columns are `Float`/double precision — sufficient for research.
- Upserts are dialect-agnostic and idempotent: re-ingesting a range never duplicates rows.

## Migrations

```powershell
cd apps/api
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

Alembic runs through the async engine and reads `DATABASE_URL` at runtime.
