# Architecture

## Principles

1. **One Strategy Definition.** Visual Builder, Technical Builder, Strategy Flow and the future
   AI Builder all compile to a single canonical JSON strategy definition. The backtest engine and
   paper engine consume that same definition.
2. **Provider-agnostic market data.** All engines access data through the `MarketDataProvider`
   interface (`apps/api/app/marketdata/base.py`). Vendor SDKs (Dhan, TrueData, NSE) only ever
   appear inside adapters.
3. **Paper-only in V1.** There is no execution path to any broker. The paper engine is designed so
   it can later be swapped for a live execution engine without touching strategy definitions.

## System context (target)

```
Market Data (Dhan / Demo / future providers)
      ↓
Data Collector → Normalizer → Validator → Database (TimescaleDB)
      ↓
Market Data Service
      ↓
Strategy Engine ── consumes Strategy Definition
      ↓                 ↓
Backtest Engine    Paper Execution Engine (virtual orders only)
      ↓                 ↓
Analytics / Reports / Debugging
```

## Phase 1 implementation

### Backend (`apps/api`)

- **FastAPI** app factory (`app/main.py`) with CORS + versioned routers under `/api/v1`.
- **Settings** via `pydantic-settings` (`app/core/config.py`); `.env` driven; SQLite fallback URL
  for zero-infra development, PostgreSQL/TimescaleDB for Docker.
- **Auth**: bcrypt password hashing (`pwdlib`), JWT bearer tokens (`pyjwt`),
  `OAuth2PasswordBearer` dependency. Roles (`USER`/`ADMIN`) exist on the model for future use.
- **Persistence**: SQLAlchemy 2.0 async ORM. Portable `JSONType`
  (JSONB on PostgreSQL, JSON on SQLite). Alembic async migrations.
- **Tables**: `users`, `strategies`, `strategy_versions` (immutable snapshots, auto-bumped on
  definition change), `paper_accounts`, `backtest_runs` (engine arrives in Phase 5).
- **Multi-user ready**: every row carries `user_id`; strategies are strictly scoped per user.

### Market data

- `MarketDataProvider` ABC: `get_instruments()`, `get_historical_data()`, `get_option_chain()`.
- `DemoProvider`: deterministic synthetic data (seeded PRNG per symbol/date), NSE hours
  (09:15–15:30 IST), interval aggregation (1m→1d), Black-Scholes-based synthetic option chain.
  Every payload is flagged `is_demo: true`. It exists so UI/engine work never blocks on broker
  credentials — it is never presented as real data.
- `DhanProvider` (Phase 2): DhanHQ v2 REST adapter — master CSV instruments, historical
  candles, option chain; throttled and auth-aware. See `docs/market-data.md`.
- Provider selection via settings (`MARKET_DATA_PROVIDER=demo|dhan`, lazy registry in
  `app/marketdata/factory.py`); FastAPI dependency `ProviderDep` allows test overrides.

### Market data pipeline (Phase 2)

- **Instrument master**: synced into `instrument_master` from the provider
  (`POST /api/v1/data/instruments/sync`).
- **Ingestion service** normalizes timestamps to UTC, de-duplicates, validates, then upserts
  idempotently into segment-specific candle tables (`index/equity/futures/options_candles`,
  composite PK `(instrument_id, interval, time)`).
- **Validation** flags invalid OHLC, duplicates, abnormal jumps, misaligned timestamps,
  market-hour violations, and reports session coverage (healthy/warning/critical).
- **Caching**: option chains cached with TTL — Redis when configured, in-process fallback otherwise.

### Frontend (`apps/web`)

- Next.js 16 App Router, TypeScript, Tailwind v4.
- Dark navy sidebar with MAIN/BUILD/TOOLS sections exactly matching the product spec;
  unimplemented features are labeled "Soon" — never faked.
- Dashboard: live API health badge, honest empty-state metrics, workflow map.
- Strategy Library: real CRUD against the API; "+ New Strategy" opens a builder picker
  (Visual / Flow / Technical).
- **Builders (Phase 4)** — three editors that all compile to the canonical definition:
  - *Visual Builder*: guided forms (indicators from the live catalog, nested condition
    groups, variables, risk/position), debounced validation and signal preview.
  - *Strategy Flow*: pipeline visualization of the strategy with inline stage editing.
  - *Technical Builder*: direct JSON editing with templates and validation.
- Shared builder kit: `OperandEditor`, `ConditionRow`, `ConditionGroupEditor`,
  `IndicatorsEditor`, `MetaPanel`, `ValidationPanel` + `useBuilderWorkflow`
  (catalog fetch → validate → preview → save).
- Auth context persists the JWT client-side; API client attaches bearer tokens automatically.

### Quant engine (Phase 3)

- **Canonical strategy definition** (`app/quant/schema.py`, v1): every builder
  compiles to the same JSON; deep validation separates errors from warnings.
  See `docs/strategy-definition.md`.
- **Indicator library** (`app/quant/indicators.py`): registry-driven — the same
  `INDICATORS` table validates definitions and computes values, so a definition
  can never reference an indicator that cannot run. 12 indicators (SMA/EMA/WMA,
  RSI, MACD, BBANDS, ATR, Supertrend, Stochastic, ADX, session VWAP, ROC).
- **Formula engine** (`app/quant/formula.py`): recursive-descent parser +
  AST evaluator; no `eval`/`exec`; whitelisted functions; NaN on domain errors.
- **Condition engine** (`app/quant/conditions.py`): tagged operands
  (price/constant/variable/indicator/formula), comparison + cross operators,
  ALL/ANY groups (depth-capped).
- **Evaluation engine** (`app/quant/engine.py`): definition + candles →
  indicator series and entry/exit signal vectors. Backtest (Phase 5), paper
  (Phase 6) and optimizer (Phase 7) engines consume exactly this output.
- **API**: `/quant/catalog`, `/quant/validate`, `/quant/preview`.

### Backtest engine (Phase 5)

- **Pure simulation core** (`app/backtest/engine.py`): definition + candles +
  config in → trades, equity curve, summary out. No DB or IO inside; the API
  layer owns persistence. See `docs/backtesting.md` for the exact semantics.
- **Stored-candles-only**: runs read local history via
  `app/services/candles.py`; if the range has no ingested candles the run is
  rejected with a pointer to the Data Manager instead of silently fetching
  provider data — results must be reproducible.
- **API** (`app/api/v1/backtests.py`): `POST /backtests` (run + persist),
  `GET /backtests?strategy_id=…`, `GET /backtests/{id}`. Runs pin the strategy
  version they executed and store full trades/equity in `result_summary`.
- **UI** (`/backtest`): run form, metric cards, SVG equity curve, trade table
  with exit reasons, run history. Strategies page links straight in with
  `?strategy=<id>` preselected.

### Forward testing engine (Phase 6)

- **Incremental tick engine** (`app/paper/engine.py`): `step_paper(history, new_candles, ...)`
  processes newly completed candles with history context for correct indicator evaluation
  across tick boundaries.
- **Pending action carry**: signals at bar close are stored in `pending_action` on the
  `ForwardTestRun` row and executed at the next tick's first bar open. Nothing is lost or
  double-executed.
- **First-tick initialization**: the first tick anchors to the latest stored bar without
  acting — forward tests start from "now", they do not replay old history.
- **API** (`app/api/v1/forward_tests.py`): create, tick, pause, resume, stop. Stop
  force-closes any open position at the latest stored close.
- **Paper accounts** (`app/api/v1/paper.py`): virtual capital accounts with marked-to-market
  equity (cash + unrealized positions).
- **UI**: `/forward-test` (start/tick/pause/resume/stop with fills table),
  `/tools/paper-accounts` (equity + positions + orders).

### Optimization engine (Phase 7)

- **Grid search** (`app/optimizer/engine.py`): cartesian product of parameter ranges,
  backtest each combination, rank by target metric.
- **Walk-forward**: split candles into train/test windows, run each combination on both,
  report train and test Sharpe ratios for overfitting detection.
- **`apply_params()`**: dot-notation parameter overrides (e.g., `indicators.f.params.length`)
  applied to a copy of the definition. Handles list navigation by indicator ID.
- **API** (`app/api/v1/optimizations.py`): create (max 500 combos, synchronous), list,
  detail, results.
- **UI** (`/optimization`): JSON parameter range editor, method/target metric selectors,
  ranked results table.

## Decision log

| Decision | Rationale |
| --- | --- |
| uv for Python env management | Fast, reproducible lockfile, no system Python pollution |
| SQLite dev fallback | Lets contributors run the stack before installing Docker |
| Generic JSON columns | Portable across SQLite/Postgres now; TimescaleDB hypertables arrive with candle tables in Phase 2 |
| Immutable strategy versions | Required for compare/restore/backtest-reproducibility guarantees |
| Float64 candle storage | Sufficient precision for research/analytics; revisit only if rounding ever becomes material |
| Inline ingestion (FastAPI BackgroundTasks later) | Current volumes are small; a job queue (Celery/RQ) is deferred until backfills demand it |
| Dhan master CSV column mapping | Written from published docs; pinned by tests, flagged LIVE-VERIFY until run against live credentials |
| Redis optional | Cache layer falls back to an in-process TTL cache so dev needs no extra services |
| UTC storage, IST presentation | All candle timestamps normalized to UTC before insert; naive DB reads re-anchored to UTC |
| Pure-Python indicator kernels | O(n) algorithms are fast enough at research scale; numpy/pandas deferred until profiling demands them |
| Registry-driven indicators | One table drives validation AND computation — definitions can't reference non-runnable indicators |
| Formula interpreter over eval | Safe arithmetic subset via recursive-descent parser; no eval/exec surface for user input |
| Quant lives in apps/api/app/quant | Single consumer today; extraction to packages/ when a second service needs it |
| Definitions validated at the strategy API door | Engines can trust stored definitions; builders get immediate feedback via /quant/validate |
| Three builders, one schema | Visual/Flow/Technical are presentation choices over the same canonical JSON — no divergence possible |
| Next-bar-open execution, pessimistic intrabar fills | No same-bar lookahead; stop assumed before target when both are touched in one bar — results err conservative, never optimistic |
| Backtests read stored candles only | Reproducibility: a run re-executed later uses the exact same series, not whatever the provider now returns |
| Runs pin strategy version + config JSON | Any historical result can be traced to the exact definition that produced it |
| Incremental tick with history context | Indicators need N bars of warmup; passing only new bars causes missed signals at tick boundaries |
| First-tick anchors to latest bar | Forward tests start from "now", not replaying old history — consistent with live semantics |
| Stored-candles-only for all engines | Backtest, forward test, and optimizer all read from DB — reproducible and provider-agnostic |
| Grid search runs synchronously | Up to 500 combos fast enough at research scale; async job queue deferred until needed |
