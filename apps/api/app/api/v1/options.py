from fastapi import APIRouter, HTTPException, status

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.deps import ProviderDep
from app.options import lab
from app.options.lab import OptionsLabError, ResolvedLeg
from app.schemas.options import (
    MonteCarloRequest,
    MonteCarloResponse,
    PayoffLeg,
    PayoffMetricsOut,
    PayoffPoint,
    PayoffRequest,
    PayoffResponse,
)

router = APIRouter(prefix="/options", tags=["options"])


async def _option_chain(provider: ProviderDep, underlying: str, expiry: str | None) -> dict:
    settings = get_settings()
    cache = get_cache()
    key = f"oc:{provider.name}:{underlying.upper()}:{expiry or 'nearest'}"
    cached = await cache.get_json(key)
    if cached is not None:
        return cached
    try:
        chain = await provider.get_option_chain(underlying, expiry)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{underlying}: {exc}",
        ) from exc
    await cache.set_json(key, chain, ttl=settings.OPTION_CHAIN_CACHE_TTL)
    return chain


def _resolve_legs(request: PayoffRequest, chain: dict) -> tuple[list[ResolvedLeg], float]:
    strikes = [row["strike"] for row in chain["strikes"]]
    premiums = {row["strike"]: (row["call_ltp"], row["put_ltp"]) for row in chain["strikes"]}
    ivs = {row["strike"]: (row["call_iv"], row["put_iv"]) for row in chain["strikes"]}
    spot = request.spot_override or chain["spot"]
    legs = [
        lab.LegInput(
            action=leg.action,
            option_type=leg.option_type,
            strike_offset=leg.strike_offset,
            lots=leg.lots,
        )
        for leg in request.legs
    ]
    resolved = [
        lab.resolve_leg(
            leg,
            spot,
            strikes,
            request.dte_days,
            request.interest_rate,
            request.iv_override,
            premiums,
            ivs,
        )
        for leg in legs
    ]
    return resolved, spot


def _payoff_leg_out(leg: ResolvedLeg) -> PayoffLeg:
    return PayoffLeg(
        action=leg.action,
        option_type=leg.option_type,
        strike_offset=leg.strike_offset,
        lots=leg.lots,
        strike=leg.strike,
        premium=round(leg.premium, 2),
        iv_pct=round(leg.iv * 100, 2),
        delta=round(leg.delta, 4),
        gamma=round(leg.gamma, 6),
        theta_per_day=round(leg.theta_per_day, 4),
        vega=round(leg.vega, 4),
    )


@router.post("/payoff", response_model=PayoffResponse)
async def payoff(provider: ProviderDep, request: PayoffRequest) -> PayoffResponse:
    chain = await _option_chain(provider, request.underlying, request.expiry)
    try:
        resolved, spot = _resolve_legs(request, chain)
    except OptionsLabError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    curve_raw = lab.payoff_curve(resolved, request.lot_size, spot)
    curve = [PayoffPoint(price=round(p, 2), pnl=round(v, 2)) for p, v in curve_raw]
    metrics = lab.payoff_metrics(curve_raw, resolved)
    atm = min((row["strike"] for row in chain["strikes"]), key=lambda k: abs(k - spot))

    return PayoffResponse(
        underlying=request.underlying.upper(),
        spot=spot,
        atm_strike=atm,
        expiry=chain["expiry"],
        dte_days=request.dte_days,
        lot_size=request.lot_size,
        is_demo=chain.get("is_demo", False),
        provider=chain.get("provider", provider.name),
        legs=[_payoff_leg_out(leg) for leg in resolved],
        curve=curve,
        metrics=PayoffMetricsOut(
            net_premium=lab.net_premium(resolved, request.lot_size),
            max_profit=metrics["max_profit"],
            max_loss=metrics["max_loss"],
            breakevens=metrics["breakevens"],
            risk_reward=metrics["risk_reward"],
        ),
        net_greeks=lab.net_greeks(resolved, request.lot_size),
    )


@router.post("/monte-carlo", response_model=MonteCarloResponse)
async def monte_carlo(provider: ProviderDep, request: MonteCarloRequest) -> MonteCarloResponse:
    chain = await _option_chain(provider, request.underlying, request.expiry)
    try:
        resolved, spot = _resolve_legs(request, chain)
    except OptionsLabError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    horizon = request.horizon_days or min(max(request.dte_days, 1), 7)
    result = lab.monte_carlo(
        legs=resolved,
        spot=spot,
        dte_days=request.dte_days,
        horizon_days=horizon,
        paths=request.paths,
        rate=request.interest_rate,
        lot_size=request.lot_size,
        vol_override=request.vol_override,
    )
    return MonteCarloResponse(**result)
