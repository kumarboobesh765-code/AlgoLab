from fastapi import APIRouter

from app.api.v1 import auth, backtests, data, forward_tests, health, market, optimizations, paper, quant, strategies, strategies_polish

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(strategies_polish.router)
api_router.include_router(strategies.router)
api_router.include_router(market.router)
api_router.include_router(data.router)
api_router.include_router(quant.router)
api_router.include_router(backtests.router)
api_router.include_router(paper.router)
api_router.include_router(forward_tests.router)
api_router.include_router(optimizations.router)
