# Backend Agent Guide (apps/api)

## Tech stack
- Python 3.14, FastAPI, SQLAlchemy 2.0 async, Alembic async, pydantic v2
- uv for package management, pytest-asyncio for tests, ruff for linting
- SQLite (dev) / PostgreSQL+TimescaleDB (Docker)

## Entry point
`app/main.py` creates the FastAPI app, includes `api_router` from `app/api/v1/__init__.py`.

## Route modules (app/api/v1/)
Each domain has its own file. Routers are registered in `__init__.py` in import order.
Order matters: static routes (e.g., /templates) must come before parameterized (/{id}).

| File | Prefix | Purpose |
| --- | --- | --- |
| auth.py | /auth | Register, login, /me |
| strategies.py | /strategies | CRUD + clone + versions |
| data.py | /data | Instruments, ingestion, quality, status |
| market.py | /market | Option chain |
| quant.py | /quant | Catalog, validate, preview |
| backtests.py | /backtests | Run/list/detail backtests + GET /{run_id}/candles for replay |
| paper.py | /paper/accounts | Paper account CRUD + equity |
| forward_tests.py | /forward-tests | Lifecycle: create/tick/pause/resume/stop |
| optimizations.py | /optimizations | Grid search + walk-forward |
| strategies_polish.py | (various) | Templates, export/import, report, compare |
| ai.py | /ai | AI strategy drafting (LLM-first, rule-based fallback) |
| health.py | /health | Liveness/readiness |

## Dependencies (app/core/deps.py)
```python
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
ProviderDep = Annotated[MarketDataProvider, Depends(get_provider_instance)]
```
All route handlers use these annotated types. FastAPI injects them automatically.

## Engine modules (pure functions, no DB)
- `app/backtest/engine.py` — run_backtest(definition, candles, config) -> BacktestResult
- `app/paper/engine.py` — step_paper(definition, history, new_candles, position, pending, cash, costs) -> PaperStepResult
- `app/optimizer/engine.py` — run_grid_search / run_walk_forward (definition, candles, param_ranges, config) -> list[OptResult]
- `app/quant/engine.py` — evaluate_definition(definition, candles) -> EvaluationResult (indicator series + signal vectors)
- `app/quant/indicators.py` — INDICATORS registry dict, compute_indicator(name, candles, params)
- `app/quant/formula.py` — FormulaTokenizer/Parser/Evaluator (no eval/exec)
- `app/quant/conditions.py` — evaluate_condition, evaluate_group (depth-capped)

## How engines consume data
All engines take `list[Candle]` (from `app/marketdata/base.py`). The API layer loads
candles from DB via `app/services/candles.py::load_candles()`. Engines never touch the DB.

## Strategy definition schema (app/quant/schema.py)
```python
class StrategyDefinition(BaseModel):
    version: int  # must be 1
    timeframe: str  # "1m"|"5m"|"15m"|"30m"|"1h"|"1d"
    instrument: InstrumentRef
    indicators: list[IndicatorDef]
    entry: ConditionGroup
    exit: ConditionGroup | None
    variables: list[Variable]
    risk: RiskConfig | None
    position: PositionConfig
```
Validated by `validate_definition()` which returns (errors, warnings).

## Testing
```powershell
uv run pytest -q                    # run all 180 tests
uv run pytest tests/test_foo.py     # run one file
uv run pytest -k "test_name"        # run by name
uv run ruff check .                 # lint
```

Fixtures (tests/conftest.py):
- `db_engine` — isolated in-memory SQLite (shared across client + db_session)
- `db_session` — direct DB session for inserting test data
- `db_engine` -> `client` — httpx AsyncClient with API routes
- `auth_headers` — registered+logged-in user bearer token

## Common pitfalls
1. **Timestamps**: SQLite returns naive datetimes. Always use `ensure_utc()` from `app/services/validation.py` before comparing.
2. **Badge tones**: Frontend uses `green|red|amber|blue|slate`, NOT `emerald`.
3. **PowerShell UTF-8**: Never use `Get-Content | Set-Content` on source files. They corrupt UTF-8.
4. **Candle model**: All engines expect `Candle(timestamp, instrument_id, open, high, low, close, volume, oi)`.
5. **Route order**: Static routes before parameterized routes in FastAPI.
6. **Nonlocal keyword**: Python closures need explicit `nonlocal` when modifying outer-scope variables (engine inner functions).
