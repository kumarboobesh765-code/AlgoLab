# StrategyLab

**Build. Backtest. Forward Test. Grow.**

A professional Indian-market algorithmic trading **research platform**.

> ⚠️ **V1 is strictly research + backtesting + paper trading.**
> There is **no real-money trading, no broker order placement, no live execution**.
> The architecture keeps an execution seam so a live engine can be added later — disabled by design in V1.

---

## What works today (Phase 2 — Market Data)

| Area | Status |
| --- | --- |
| Monorepo structure (apps / services / packages / infrastructure) | ✅ |
| FastAPI backend with JWT auth (register / login / me) | ✅ |
| PostgreSQL/TimescaleDB + Redis via Docker Compose | ✅ config ready |
| SQLite fallback for zero-infra local development | ✅ |
| Alembic migrations (users, strategies, versions, paper_accounts, backtest_runs, instrument_master, 4 candle tables) | ✅ |
| Market-data abstraction (`MarketDataProvider`) + provider factory (`demo`/`dhan`) | ✅ |
| Demo Data Provider (deterministic synthetic NIFTY/BANKNIFTY/… candles + option chain, clearly labeled `DEMO`) | ✅ |
| DhanHQ v2 adapter: instrument master CSV, historical candles, option chain (mock-tested; LIVE-VERIFY markers pending real credentials) | ✅ |
| Instrument master sync + search API | ✅ |
| Historical ingestion pipeline: UTC normalization, idempotent upserts, range cap | ✅ |
| Data-quality validation + coverage reports (missing/dupes/jumps/hours) | ✅ |
| Option-chain caching (Redis or in-process fallback) | ✅ |
| Strategy CRUD + automatic versioning + clone + user isolation | ✅ |
| Next.js 16 shell: dark sidebar navigation, Dashboard, Strategy Library | ✅ |
| Login/register UI wired to the API | ✅ |
| **Data Manager UI**: sync instruments, ingest history, quality checks, status overview | ✅ |
| **Option Chain UI**: CALLS/STRIKE/PUTS grid, ATM highlight, max-OI markers, DEMO badge | ✅ |
| Quant engine: 12 indicators, condition/formula engines, canonical strategy schema + validator | ✅ |
| `/quant` API: indicator catalog, definition validation, signal preview | ✅ |
| **Visual Builder**: guided forms — indicators, conditions, variables, risk, live validation + preview | ✅ |
| **Technical Builder**: direct JSON editing of the canonical definition with templates | ✅ |
| **Strategy Flow**: pipeline view of the strategy with inline stage editing | ✅ |
| Strategy Library: create via any builder, auto-versioning on definition change | ✅ |
| Backtest engine: next-bar-open fills, stop/target/trailing exits, costs, long/short | ✅ |
| `/backtests` API: run, list, detail — results persisted per strategy version | ✅ |
| **Backtest UI**: run form, 12 metric cards, equity curve, trade list, run history | ✅ |
| Forward test engine: incremental tick on stored candles with carried pending actions | ✅ |
| Paper accounts: virtual capital, equity tracking, open position mark-to-market | ✅ |
| **Forward Test UI**: start/tick/pause/resume/stop lifecycle with fills table | ✅ |
| Grid search + walk-forward optimization with parameter range sweep | ✅ |
| **Optimization UI**: parameter editor, ranked results, train/test Sharpe for overfitting | ✅ |
| **Reports UI**: per-strategy report — meta, version history, latest backtest metrics, recent optimizations | ✅ |
| **Version compare**: backtest metric deltas + side-by-side definition diff between any two versions | ✅ |
| **Strategy import/export**: JSON download/upload from the Strategies page (`/strategies/{id}/export`, `/strategies/import`) | ✅ |
| **Trade Replay debugger**: bar-by-bar playback of any completed run — candlestick chart with B/S markers, equity strip, position & unrealized P&L panels | ✅ |
| **Market calendar** (`/calendar`): NSE trading holidays (2024-26), upcoming F&O expiries (weekly NIFTY/SENSEX, monthly third-Wednesday), lot-size + freeze-quantity validator | ✅ |
| **Transaction cost calculator** (`POST /calendar/costs`): STT, exchange txn, SEBI fee, stamp duty, GST — per segment/product | ✅ |
| **Parameter sensitivity heatmap** (`POST /optimizations/heatmap` + UI): 2D parameter surface with diverging color scale — visual overfitting detection | ✅ |
| **Tax report** (`/tax/report` + `/tools/tax-report` UI): STCG/LTCG buckets by holding period, F&O turnover view, estimated tax, CSV export | ✅ |
| **Background optimization runs** (`?background=true`): 202 + poll pattern so long sweeps never block the API worker | ✅ |
| **Playwright E2E suite**: login → dashboard → strategies → backtest → optimization → tax report flows against mock mode (`npm run test:e2e`) | ✅ |
| **SEBI retail-algo compliance** (CIR/2025/0000013): 10-OPS order-rate limiter, static-IP whitelist on execution routes, OTR monitoring in risk status, white-box disclosure on AI drafts, algo-ID tagging + kill switch | ✅ |
| **Multi-symbol scanner API** (`POST /quant/scan`): one definition across up to 50 symbols on stored candles, ranked by signal recency | ✅ |
| **Expired-options history** (`GET /options/expired-history`, DhanHQ v2.2): real option-premium candles for leg backtesting | ✅ |
| **Backtest slippage** (`slippage_pct`): adverse per-side fill adjustment — entries pay more, exits receive less | ✅ |
| **Prometheus-style metrics** (`GET /api/v1/metrics`): request counts by method/path/status + latency sums, zero dependencies | ✅ |
| **UX polish**: toast notifications, dark/light theme toggle (persisted), mobile-responsive sidebar drawer, dashboard onboarding checklist | ✅ |
| **Strategy sharing**: copy a shareable link (`?import=<base64url>`) that imports the strategy into another account | ✅ |
| CI pipeline (GitHub Actions): ruff + pytest on backend, eslint + build on frontend | ✅ |
| Backend test suite (317 tests) | ✅ |

Everything else (analytics, market scanner, portfolio)
is intentionally marked **Coming Soon** in the UI — see the roadmap below.

## Repository layout

```
AlgoLab/
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/v1/      # REST routers (auth, strategies, market, data, quant, backtests, health)
│   │   │   ├── core/        # settings, security, dependencies, cache
│   │   │   ├── db/          # engine, session, base, portable JSON type
│   │   │   ├── models/      # SQLAlchemy models
│   │   │   ├── schemas/     # Pydantic schemas
│   │   │   ├── marketdata/  # provider abstraction + demo/dhan providers
│   │   │   ├── quant/       # indicators, formula/condition engines, strategy schema
│   │   │   └── backtest/    # trade simulation engine (pure functions)
│   │   ├── alembic/         # migrations
│   │   └── tests/           # pytest suite
│   └── web/                 # Next.js 16 frontend (App Router, Tailwind v4)
├── services/                # future engines (market-data, backtest, paper, strategy, analytics, optimization)
├── packages/                # future shared libs (strategy-schema, indicators, options, risk, execution, shared)
├── infrastructure/
│   ├── docker/              # Dockerfiles + postgres init
│   ├── postgres/
│   ├── redis/
│   └── monitoring/
├── docs/
├── tests/                   # cross-cutting/integration tests (Phase 2+)
├── scripts/
├── docker-compose.yml       # TimescaleDB + Redis + API + Web
└── .env.example
```

## Quickstart (local development, no Docker required)

Prerequisites: [uv](https://docs.astral.sh/uv/) (Python manager), Node.js 20+.

### 1. Backend

```powershell
cd apps/api
uv sync                                  # creates .venv and installs deps
uv run alembic upgrade head              # applies migrations (SQLite by default)
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 2. Frontend

```powershell
cd apps/web
npm install
npm run dev
```

Web app: http://localhost:3000

### 3. Try it end-to-end

1. Open http://localhost:3000 → **Sign in** → create an account.
2. Open **Tools → Data Manager** → *Sync now* → *Ingest* a few days of NIFTY 5m candles
   (demo provider generates deterministic data) → run a quality check.
3. Open **Tools → Option Chain** → explore the synthetic chain (persistent `DEMO DATA` badge).
4. Click **+ New Strategy** on the Strategies page → pick a builder → add an EMA cross,
   validate, preview signals on demo data, and save — the definition is versioned automatically.
5. Open **Backtest** → pick the strategy (same date range you ingested) → *Run backtest* →
   inspect metrics, equity curve and every trade with its exit reason.
6. The Dashboard shows live API health, real backtest counts and a clear `DEMO DATA` badge
   while the demo provider is active.

## Quickstart (Docker)

```bash
cp .env.example .env        # set JWT_SECRET at minimum
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000
- Postgres (TimescaleDB): localhost:5432 · Redis: localhost:6379

## Environment variables

See [.env.example](.env.example). Key values:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy async URL. SQLite for dev, `postgresql+asyncpg://…` for Docker/prod |
| `REDIS_URL` | Redis for cache/queues (used from Phase 2) |
| `JWT_SECRET` | Token signing secret (min 32 chars) |
| `MARKET_DATA_PROVIDER` | `demo` (default) or `dhan` |
| `DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN` | DhanHQ credentials (never exposed to frontend) |
| `INGEST_MAX_DAYS` | Max historical range per ingestion request (default 90) |
| `OPTION_CHAIN_CACHE_TTL` | Option-chain cache TTL in seconds (default 20) |
| `NEXT_PUBLIC_API_URL` | Browser-facing API base URL |

## Tests

```powershell
cd apps/api
uv run pytest -v        # 317 tests: auth, strategies, polish endpoints, providers, ingestion, quant engine, backtest engine + API + replay candles, paper engine, optimizer + heatmap, forward-test API, AI drafting, alerts, market calendar, tax report, metrics
cd apps/web
npm run lint            # ESLint (react-hooks, next)
npm run build           # type-check + production build of all 25 routes
npm run test:e2e        # Playwright E2E (mock mode — no API needed)
```

## Roadmap

Phases follow the master plan:

1. ✅ **Foundation** (Phase 1)
2. ✅ **Market data** — Dhan adapter, instrument master, historical ingestion, data validation
3. ✅ **Quant engine** — indicators, conditions, variables, formula engine, strategy schema + validator
4. ✅ **Strategy creators** — Visual Builder, Technical Builder, Strategy Flow
5. ✅ **Backtest engine + UI** — historical simulation over stored candles, metrics, equity curve, trade list
6. ✅ **Forward testing + paper accounts** — incremental tick engine, virtual capital, equity tracking, start/tick/pause/resume/stop lifecycle
7. ✅ **Optimization** — grid search + walk-forward analysis with parameter range sweep and overfitting detection
8. ✅ **Polish** — Reports UI, version comparison, JSON import/export, trade replay/debugger
9. ✅ **Platform extras** — Analytics / Market Scanner / Portfolio pages, AI Builder (`POST /ai/draft-strategy`, LLM-first with deterministic rule-based fallback), Strategy Library, Settings, forward-test auto-tick scheduler, Telegram/webhook alerts
10. ✅ **Scale & UX** — market calendar + statutory cost calculator, expiry/lot validators, metrics endpoint, CI pipeline, toasts/theme/mobile/onboarding polish, strategy share links
11. ✅ **Quant + compliance depth** — parameter sensitivity heatmap, tax report (STCG/LTCG/F&O turnover), background optimization runs, Playwright E2E suite

Remaining (post-roadmap): DhanHQ live verification (`LIVE-VERIFY` markers need real credentials), Celery+Redis for multi-process scale, strategy marketplace.

## Disclaimer

Backtests are historical simulations; forward tests use virtual money only.
Historical performance does not guarantee future results.
