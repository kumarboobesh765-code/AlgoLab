from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.deps import CurrentUser, ProviderDep
from app.options import lab
from app.options.lab import OptionsLabError, ResolvedLeg
from app.schemas.options import (
    AnalyticsRequest,
    GreeksHeatmapResponse,
    IVSurfaceResponse,
    MaxPainResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    OptionChainAnalyticsResponse,
    OptionsBacktestRequest,
    OptionsBacktestResponse,
    OptionsLegPnLOut,
    PayoffLeg,
    PayoffMetricsOut,
    PayoffPoint,
    PayoffRequest,
    PayoffResponse,
    PCRResponse,
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


@router.post("/analytics", response_model=OptionChainAnalyticsResponse)
async def analytics(provider: ProviderDep, request: AnalyticsRequest) -> OptionChainAnalyticsResponse:
    chain = await _option_chain(provider, request.underlying, request.expiry)

    from datetime import date

    from app.quant.options.analytics import (
        OptionChainSnapshot,
        calculate_support_resistance_from_oi,
        get_option_chain_analytics,
    )

    strikes = [row["strike"] for row in chain["strikes"]]
    expiry_str = chain.get("expiry", "")
    try:
        expiry = date.fromisoformat(expiry_str)
    except ValueError:
        expiry = date.today()

    snapshot = OptionChainSnapshot(
        underlying=chain["underlying"],
        expiry=expiry,
        spot=chain["spot"],
        strikes=strikes,
        call_oi={row["strike"]: row.get("call_oi", 0) for row in chain["strikes"]},
        call_volume={row["strike"]: row.get("call_volume", 0) for row in chain["strikes"]},
        call_ltp={row["strike"]: row.get("call_ltp", 0) for row in chain["strikes"]},
        call_bid={row["strike"]: row.get("call_bid", 0) for row in chain["strikes"]},
        call_ask={row["strike"]: row.get("call_ask", 0) for row in chain["strikes"]},
        put_oi={row["strike"]: row.get("put_oi", 0) for row in chain["strikes"]},
        put_volume={row["strike"]: row.get("put_volume", 0) for row in chain["strikes"]},
        put_ltp={row["strike"]: row.get("put_ltp", 0) for row in chain["strikes"]},
        put_bid={row["strike"]: row.get("put_bid", 0) for row in chain["strikes"]},
        put_ask={row["strike"]: row.get("put_ask", 0) for row in chain["strikes"]},
        call_iv={row["strike"]: row.get("call_iv", 0) for row in chain["strikes"] if row.get("call_iv", 0) > 0},
        put_iv={row["strike"]: row.get("put_iv", 0) for row in chain["strikes"] if row.get("put_iv", 0) > 0},
    )

    analytics_data = get_option_chain_analytics([snapshot])

    pcr_data = analytics_data.get("pcr", {})
    max_pain_data = analytics_data.get("max_pain", {})
    iv_surface_data = analytics_data.get("iv_surface", {})
    greeks_data = analytics_data.get("greeks_heatmap", {})
    sr_data = calculate_support_resistance_from_oi(snapshot)

    return OptionChainAnalyticsResponse(
        underlying=snapshot.underlying,
        spot=snapshot.spot,
        expiry=snapshot.expiry.isoformat(),
        pcr=PCRResponse(
            pcr_oi=pcr_data.get("oi", 0),
            pcr_volume=pcr_data.get("volume", 0),
            total_call_oi=pcr_data.get("total_call_oi", 0),
            total_put_oi=pcr_data.get("total_put_oi", 0),
            total_call_volume=pcr_data.get("total_call_volume", 0),
            total_put_volume=pcr_data.get("total_put_volume", 0),
            strike_pcr=pcr_data.get("strike_pcr", {}),
        ),
        max_pain=MaxPainResponse(
            max_pain_strike=max_pain_data.get("strike", 0),
            min_pain=max_pain_data.get("min_pain", 0),
            support_resistance=sr_data,
        ),
        iv_surface=IVSurfaceResponse(**iv_surface_data),
        greeks_heatmap=GreeksHeatmapResponse(**greeks_data),
    )


@router.post("/backtest", response_model=OptionsBacktestResponse)
async def options_backtest(provider: ProviderDep, request: OptionsBacktestRequest) -> OptionsBacktestResponse:
    from app.backtest.options_engine import OptionsBacktestError, OptionsConfig, run_options_backtest
    from app.quant.schema import InstrumentRef, OptionLeg, PositionConfig, StrategyDefinition

    legs = []
    for leg_data in request.legs:
        legs.append(OptionLeg(
            action=leg_data.get("action", "buy"),
            option_type=leg_data.get("option_type", "CE"),
            strike=leg_data.get("strike"),
            strike_formula=leg_data.get("strike_formula", "ATM"),
            lots=leg_data.get("lots", 1),
            expiry_formula=leg_data.get("expiry_formula", "THIS_WEEK"),
        ))

    definition = StrategyDefinition(
        version=1,
        timeframe="1d",
        instrument=InstrumentRef(symbol=request.underlying.upper(), exchange="NSE", segment="index"),
        legs=legs,
        entry={"logic": "ALL", "conditions": [{"left": {"kind": "constant", "value": 1}, "op": ">", "right": {"kind": "constant", "value": 0}}]},
        position=PositionConfig(direction="both"),
    )

    from datetime import date, timedelta
    end_date = date.today()
    start_date = end_date - timedelta(days=request.dte_days + 30)
    candle_list = await provider.get_historical_data(
        symbol=request.underlying.upper(),
        interval="1d",
        start=datetime.combine(start_date, datetime.min.time()),
        end=datetime.combine(end_date, datetime.max.time()),
    )
    if not candle_list:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No historical data available")

    cfg = OptionsConfig(
        initial_capital=request.initial_capital,
        volatility=request.volatility,
        lot_size=request.lot_size,
        auto_roll=request.auto_roll,
    )

    try:
        result = run_options_backtest(definition, candle_list, cfg)
    except OptionsBacktestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    leg_outs = [
        OptionsLegPnLOut(
            leg_index=leg.leg_index,
            action=leg.action,
            option_type=leg.option_type,
            strike=leg.strike,
            expiry=leg.expiry.isoformat(),
            lots=leg.lots,
            entry_price=leg.entry_price,
            entry_date=leg.entry_date.isoformat(),
            current_price=leg.current_price,
            current_date=leg.current_date.isoformat(),
            days_held=leg.days_held,
            gross_pnl=round(leg.gross_pnl, 2),
            costs={k: round(v, 2) for k, v in leg.costs.items()},
            net_pnl=round(leg.net_pnl, 2),
            exit_reason=leg.exit_reason,
        )
        for leg in result.legs
    ]

    return OptionsBacktestResponse(
        legs=leg_outs,
        daily_values=result.daily_values,
        summary=result.summary,
        cost_breakdown=result.cost_breakdown,
    )


# ---- expired options history (DhanHQ v2.2+) ----


@router.get("/expired-history")
async def expired_option_history(
    provider: ProviderDep,
    user: CurrentUser = None,
    underlying: str = "NIFTY",
    strike: float = 0,
    option_type: str = "CE",
    expiry: str = "",
    interval: str = "5m",
    start: str = "",
    end: str = "",
) -> dict:
    """Historical premium candles for an (optionally expired) option contract.

    Enables options-leg backtesting against real traded premiums instead of
    Black-Scholes synthesis where the provider supports it.
    """
    from datetime import UTC, timedelta
    from datetime import datetime as _dt

    fn = getattr(provider, "get_expired_option_history", None)
    if fn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider.name}' does not expose expired options history",
        )
    if not expiry:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="expiry (YYYY-MM-DD) is required")
    try:
        expiry_date = _dt.strptime(expiry, "%Y-%m-%d").date()
        start_dt = _dt.strptime(start, "%Y-%m-%d") if start else _dt.now(UTC) - timedelta(days=30)
        end_dt = _dt.strptime(end, "%Y-%m-%d") if end else _dt.now(UTC)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Bad date: {exc}") from exc
    if strike <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="strike must be > 0")

    candles = await fn(
        underlying=underlying,
        strike=strike,
        option_type=option_type,
        expiry=expiry_date,
        interval=interval,
        start=start_dt,
        end=end_dt,
    )
    return {
        "underlying": underlying.upper(),
        "strike": strike,
        "option_type": option_type.upper(),
        "expiry": expiry,
        "interval": interval,
        "count": len(candles),
        "is_demo": provider.is_demo,
        "candles": [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": c.open, "high": c.high, "low": c.low, "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ],
    }
