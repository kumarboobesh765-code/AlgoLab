# Tests

Phase 1 test suites live with the code they cover:

- **API**: `apps/api/tests/` — pytest + httpx against an isolated in-memory SQLite database.
  Covers auth flows, strategy CRUD/versioning/cloning, cross-user isolation, health endpoint and
  the demo market-data provider (determinism, market hours, OHLC sanity, option chain).

Run:

```powershell
cd apps/api
uv run pytest -v
```

Cross-cutting integration tests (Dhan adapter, Dockerized Postgres, WebSocket) are added in
Phase 2+ alongside the features they verify.
