from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.metrics import MetricsMiddleware, render_metrics
from app.marketdata.base import ProviderError


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start_scheduler, stop_scheduler

    start_scheduler(app)
    try:
        yield
    finally:
        await stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="StrategyLab API",
        version="0.1.0",
        description=(
            "Indian-market algorithmic trading research platform. "
            "RESEARCH + BACKTEST + PAPER TRADING ONLY — no real order execution in V1."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    app.add_middleware(MetricsMiddleware)

    @app.get("/api/v1/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            content=render_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return app


app = create_app()
