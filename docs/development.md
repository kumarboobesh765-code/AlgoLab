# Development Guide

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python 3.12 manager (`uv python install 3.12`)
- Node.js 20+ and npm
- Docker Desktop (optional — only needed for PostgreSQL/TimescaleDB + Redis)

## Daily workflow

```powershell
# Terminal 1 - API
cd apps/api
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 - Web
cd apps/web
npm run dev
```

## Database

```powershell
cd apps/api
uv run alembic upgrade head                     # apply migrations
uv run alembic revision --autogenerate -m "..." # create a new migration after model changes
```

Default dev database is `apps/api/strategylab.db` (SQLite). Point `DATABASE_URL` at the Docker
Postgres to test the production path.

## Quality gates (run before every commit)

```powershell
cd apps/api
uv run pytest -v      # unit/integration tests
uv run ruff check .   # lint

cd apps/web
npm run lint          # eslint
npm run build         # tsc + production build
```

## Conventions

- Backend: async everywhere, Pydantic schemas for all I/O, routers thin, models typed with
  SQLAlchemy 2.0 `Mapped[]` annotations.
- Frontend: server components by default; `"use client"` only where interactivity is required.
- Never add a feature that pretends to work: mark it **Coming Soon** instead.
- Never commit secrets; `.env` is gitignored.
