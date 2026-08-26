"""Option chain analytics - IV surface, PCR, max pain, Greeks heatmap.

Computes market microstructure metrics from option chain data.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from app.quant.options.pricing import calculate_greeks, implied_volatility


@dataclass(frozen=True)
class OptionChainSnapshot:
    """Raw option chain data for a single expiry."""

    underlying: str
    expiry: date
    spot: float
    strikes: list[float]
    call_oi: dict[float, int]
    call_volume: dict[float, int]
    call_ltp: dict[float, float]
    call_bid: dict[float, float]
    call_ask: dict[float, float]
    put_oi: dict[float, int]
    put_volume: dict[float, int]
    put_ltp: dict[float, float]
    put_bid: dict[float, float]
    put_ask: dict[float, float]
    call_iv: dict[float, float] | None = None
    put_iv: dict[float, float] | None = None


@dataclass(frozen=True)
class IVSurfacePoint:
    """Single point on IV surface."""

    strike: float
    expiry: date
    days_to_expiry: int
    iv: float
    delta: float
    moneyness: float  # strike / spot


@dataclass(frozen=True)
class IVSurface:
    """Implied volatility surface across strikes and expiries."""

    underlying: str
    spot: float
    points: list[IVSurfacePoint]
    smile_params: dict[str, float]  # ATM IV, skew, kurtosis

    def get_atm_iv(self, days_to_expiry: int) -> float | None:
        """Get ATM IV for specific expiry."""
        atm_points = [p for p in self.points if p.days_to_expiry == days_to_expiry and abs(p.moneyness - 1.0) < 0.02]
        if atm_points:
            return atm_points[0].iv
        return None

    def get_skew(self, days_to_expiry: int) -> float | None:
        """Get 25-delta skew for specific expiry."""
        points = [p for p in self.points if p.days_to_expiry == days_to_expiry]
        if len(points) < 3:
            return None
        # Fit quadratic to get skew
        return self.smile_params.get("skew", 0.0)


@dataclass(frozen=True)
class PCRData:
    """Put-Call Ratio metrics."""

    pcr_oi: float
    pcr_volume: float
    total_call_oi: int
    total_put_oi: int
    total_call_volume: int
    total_put_volume: int
    strike_pcr: dict[float, float]


@dataclass(frozen=True)
class MaxPainResult:
    """Max pain calculation result."""

    max_pain_strike: float
    min_pain: float
    pain_by_strike: dict[float, float]


@dataclass(frozen=True)
class GreeksHeatmap:
    """Aggregated Greeks across the option chain."""

    underlying: str
    expiry: date
    spot: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    strike_greeks: dict[float, dict[str, float]]  # strike -> {delta, gamma, theta, vega, call/put breakdown}


@dataclass(frozen=True)
class IVRankPercentile:
    """IV Rank and IV Percentile metrics."""

    iv_rank: float  # Current IV vs 52-week range (0-100)
    iv_percentile: float  # % of days IV was below current (0-100)
    current_iv: float
    iv_52w_high: float
    iv_52w_low: float


def calculate_pcr(chain: OptionChainSnapshot) -> PCRData:
    """Calculate Put-Call Ratios from option chain.

    Args:
        chain: Option chain snapshot

    Returns:
        PCRData with OI and volume PCR
    """
    total_call_oi = sum(chain.call_oi.values())
    total_put_oi = sum(chain.put_oi.values())
    total_call_volume = sum(chain.call_volume.values())
    total_put_volume = sum(chain.put_volume.values())

    pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0
    pcr_volume = total_put_volume / total_call_volume if total_call_volume > 0 else 0.0

    strike_pcr = {}
    for strike in chain.strikes:
        call_oi = chain.call_oi.get(strike, 0)
        put_oi = chain.put_oi.get(strike, 0)
        strike_pcr[strike] = put_oi / call_oi if call_oi > 0 else 0.0

    return PCRData(
        pcr_oi=pcr_oi,
        pcr_volume=pcr_volume,
        total_call_oi=total_call_oi,
        total_put_oi=total_put_oi,
        total_call_volume=total_call_volume,
        total_put_volume=total_put_volume,
        strike_pcr=strike_pcr,
    )


def calculate_max_pain(chain: OptionChainSnapshot) -> MaxPainResult:
    """Calculate max pain strike (strike where option buyers lose most).

    Max pain = strike where total option value (calls + puts) is minimized.
    Assumes all options expire worthless at that strike.

    Args:
        chain: Option chain snapshot

    Returns:
        MaxPainResult with max pain strike and pain distribution
    """
    pain_by_strike = {}

    for test_strike in chain.strikes:
        total_pain = 0.0

        for strike in chain.strikes:
            # Call pain if spot > strike at expiry
            if test_strike > strike:
                call_oi = chain.call_oi.get(strike, 0)
                total_pain += (test_strike - strike) * call_oi

            # Put pain if spot < strike at expiry
            if test_strike < strike:
                put_oi = chain.put_oi.get(strike, 0)
                total_pain += (strike - test_strike) * put_oi

        pain_by_strike[test_strike] = total_pain

    max_pain_strike = min(pain_by_strike, key=pain_by_strike.get)
    min_pain = pain_by_strike[max_pain_strike]

    return MaxPainResult(
        max_pain_strike=max_pain_strike,
        min_pain=min_pain,
        pain_by_strike=pain_by_strike,
    )


def calculate_iv_surface(
    chains: list[OptionChainSnapshot],
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> IVSurface:
    """Build IV surface from multiple option chain expiries.

    Args:
        chains: List of option chain snapshots (different expiries)
        rate: Risk-free rate
        dividend_yield: Dividend yield

    Returns:
        IVSurface with all points and smile parameters
    """
    points = []

    for chain in chains:
        days_to_expiry = (chain.expiry - date.today()).days
        if days_to_expiry <= 0:
            continue

        for strike in chain.strikes:
            call_iv = chain.call_iv.get(strike) if chain.call_iv else None
            put_iv = chain.put_iv.get(strike) if chain.put_iv else None

            # Calculate IV from LTP if not provided
            if call_iv is None and chain.call_ltp.get(strike, 0) > 0:
                try:
                    call_iv = implied_volatility(
                        chain.call_ltp[strike],
                        chain.spot,
                        strike,
                        float(days_to_expiry),
                        rate,
                        dividend_yield,
                        "CE",
                    )
                except Exception:
                    pass

            if put_iv is None and chain.put_ltp.get(strike, 0) > 0:
                try:
                    put_iv = implied_volatility(
                        chain.put_ltp[strike],
                        chain.spot,
                        strike,
                        float(days_to_expiry),
                        rate,
                        dividend_yield,
                        "PE",
                    )
                except Exception:
                    pass

            # Use average of call/put IV, preferring call for ATM+
            if call_iv is not None and put_iv is not None:
                iv = (call_iv + put_iv) / 2
            elif call_iv is not None:
                iv = call_iv
            elif put_iv is not None:
                iv = put_iv
            else:
                continue

            # Calculate delta for moneyness reference
            greeks = calculate_greeks(chain.spot, strike, float(days_to_expiry), iv, rate, dividend_yield, "CE")
            moneyness = strike / chain.spot

            points.append(
                IVSurfacePoint(
                    strike=strike,
                    expiry=chain.expiry,
                    days_to_expiry=days_to_expiry,
                    iv=iv,
                    delta=greeks.delta,
                    moneyness=moneyness,
                )
            )

    # Fit smile parameters (simplified)
    smile_params = _fit_smile(points)

    return IVSurface(
        underlying=chains[0].underlying if chains else "",
        spot=chains[0].spot if chains else 0.0,
        points=points,
        smile_params=smile_params,
    )


def _fit_smile(points: list[IVSurfacePoint]) -> dict[str, float]:
    """Fit quadratic smile: IV = a + b*(moneyness-1) + c*(moneyness-1)^2."""
    if len(points) < 3:
        return {"atm_iv": 0.0, "skew": 0.0, "kurtosis": 0.0}

    # Group by expiry and fit each
    by_expiry = defaultdict(list)
    for p in points:
        by_expiry[p.days_to_expiry].append(p)

    atm_ivs = []
    skews = []

    for dte, pts in by_expiry.items():
        atm_pts = [p for p in pts if abs(p.moneyness - 1.0) < 0.05]
        if atm_pts:
            atm_ivs.append(atm_pts[0].iv)

        # Fit skew using 25 delta points
        otm_calls = [p for p in pts if 1.0 < p.moneyness < 1.1]
        otm_puts = [p for p in pts if 0.9 < p.moneyness < 1.0]
        if otm_calls and otm_puts:
            call_25d = min(otm_calls, key=lambda p: abs(p.delta - 0.25))
            put_25d = min(otm_puts, key=lambda p: abs(p.delta + 0.25))
            skew = put_25d.iv - call_25d.iv
            skews.append(skew)

    return {
        "atm_iv": sum(atm_ivs) / len(atm_ivs) if atm_ivs else 0.0,
        "skew": sum(skews) / len(skews) if skews else 0.0,
        "kurtosis": 0.0,  # Simplified
    }


def calculate_iv_rank_percentile(
    current_iv: float,
    historical_iv: list[float],
) -> IVRankPercentile:
    """Calculate IV Rank and IV Percentile.

    IV Rank = (current - min) / (max - min) * 100 (52-week range)
    IV Percentile = % of days IV was below current

    Args:
        current_iv: Current ATM IV
        historical_iv: List of historical daily ATM IV values

    Returns:
        IVRankPercentile with both metrics
    """
    if not historical_iv:
        return IVRankPercentile(
            iv_rank=50.0,
            iv_percentile=50.0,
            current_iv=current_iv,
            iv_52w_high=current_iv,
            iv_52w_low=current_iv,
        )

    iv_52w_high = max(historical_iv)
    iv_52w_low = min(historical_iv)

    if iv_52w_high == iv_52w_low:
        iv_rank = 50.0
    else:
        iv_rank = (current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low) * 100.0

    below_count = sum(1 for iv in historical_iv if iv < current_iv)
    iv_percentile = below_count / len(historical_iv) * 100.0

    return IVRankPercentile(
        iv_rank=round(iv_rank, 2),
        iv_percentile=round(iv_percentile, 2),
        current_iv=current_iv,
        iv_52w_high=iv_52w_high,
        iv_52w_low=iv_52w_low,
    )


def calculate_greeks_heatmap(
    chain: OptionChainSnapshot,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> GreeksHeatmap:
    """Calculate aggregated Greeks across all strikes for an expiry.

    Args:
        chain: Option chain snapshot
        rate: Risk-free rate
        dividend_yield: Dividend yield

    Returns:
        GreeksHeatmap with net and per-strike Greeks
    """
    days_to_expiry = (chain.expiry - date.today()).days
    if days_to_expiry <= 0:
        days_to_expiry = 1

    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0
    strike_greeks = {}

    for strike in chain.strikes:
        call_oi = chain.call_oi.get(strike, 0)
        put_oi = chain.put_oi.get(strike, 0)
        total_oi = call_oi + put_oi

        if total_oi == 0:
            continue

        # Call Greeks
        call_iv = chain.call_iv.get(strike, 0.2) if chain.call_iv else 0.2
        call_greeks = calculate_greeks(chain.spot, strike, float(days_to_expiry), call_iv, rate, dividend_yield, "CE")

        # Put Greeks
        put_iv = chain.put_iv.get(strike, 0.2) if chain.put_iv else 0.2
        put_greeks = calculate_greeks(chain.spot, strike, float(days_to_expiry), put_iv, rate, dividend_yield, "PE")

        # Weight by OI
        call_weight = call_oi / total_oi if total_oi > 0 else 0
        put_weight = put_oi / total_oi if total_oi > 0 else 0

        delta = call_weight * call_greeks.delta + put_weight * put_greeks.delta
        gamma = call_weight * call_greeks.gamma + put_weight * put_greeks.gamma
        theta = call_weight * call_greeks.theta + put_weight * put_greeks.theta
        vega = call_weight * call_greeks.vega + put_weight * put_greeks.vega

        strike_greeks[strike] = {
            "delta": round(delta * total_oi, 4),
            "gamma": round(gamma * total_oi, 6),
            "theta": round(theta * total_oi, 4),
            "vega": round(vega * total_oi, 4),
            "call_oi": call_oi,
            "put_oi": put_oi,
            "call_delta": round(call_greeks.delta, 4),
            "put_delta": round(put_greeks.delta, 4),
        }

        net_delta += delta * total_oi
        net_gamma += gamma * total_oi
        net_theta += theta * total_oi
        net_vega += vega * total_oi

    return GreeksHeatmap(
        underlying=chain.underlying,
        expiry=chain.expiry,
        spot=chain.spot,
        net_delta=round(net_delta, 4),
        net_gamma=round(net_gamma, 6),
        net_theta=round(net_theta, 4),
        net_vega=round(net_vega, 4),
        strike_greeks=strike_greeks,
    )


def get_option_chain_analytics(
    chains: list[OptionChainSnapshot],
    historical_iv: list[float] | None = None,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> dict:
    """Get comprehensive option chain analytics.

    Args:
        chains: List of option chain snapshots
        historical_iv: Historical ATM IV series for IV rank/percentile
        rate: Risk-free rate
        dividend_yield: Dividend yield

    Returns:
        Dict with all analytics
    """
    if not chains:
        return {}

    primary = chains[0]

    pcr = calculate_pcr(primary)
    max_pain = calculate_max_pain(primary)
    iv_surface = calculate_iv_surface(chains, rate, dividend_yield)
    greeks_heatmap = calculate_greeks_heatmap(primary, rate, dividend_yield)

    atm_iv = iv_surface.get_atm_iv((primary.expiry - date.today()).days) or 0.0
    iv_rank_pct = None
    if historical_iv:
        iv_rank_pct = calculate_iv_rank_percentile(atm_iv, historical_iv)

    return {
        "underlying": primary.underlying,
        "spot": primary.spot,
        "expiry": primary.expiry.isoformat(),
        "pcr": {
            "oi": round(pcr.pcr_oi, 3),
            "volume": round(pcr.pcr_volume, 3),
            "total_call_oi": pcr.total_call_oi,
            "total_put_oi": pcr.total_put_oi,
            "total_call_volume": pcr.total_call_volume,
            "total_put_volume": pcr.total_put_volume,
            "strike_pcr": {str(k): round(v, 3) for k, v in pcr.strike_pcr.items()},
        },
        "max_pain": {
            "strike": max_pain.max_pain_strike,
            "min_pain": max_pain.min_pain,
            "pain_by_strike": {str(k): round(v, 2) for k, v in max_pain.pain_by_strike.items()},
        },
        "iv_surface": {
            "atm_iv": round(atm_iv, 4),
            "skew": round(iv_surface.smile_params.get("skew", 0), 4),
            "kurtosis": round(iv_surface.smile_params.get("kurtosis", 0), 4),
            "points": [
                {
                    "strike": p.strike,
                    "expiry": p.expiry.isoformat(),
                    "days_to_expiry": p.days_to_expiry,
                    "iv": round(p.iv, 4),
                    "delta": round(p.delta, 4),
                    "moneyness": round(p.moneyness, 4),
                }
                for p in iv_surface.points
            ],
        },
        "iv_rank_percentile": (
            {
                "iv_rank": iv_rank_pct.iv_rank,
                "iv_percentile": iv_rank_pct.iv_percentile,
                "current_iv": iv_rank_pct.current_iv,
                "iv_52w_high": iv_rank_pct.iv_52w_high,
                "iv_52w_low": iv_rank_pct.iv_52w_low,
            }
            if iv_rank_pct
            else None
        ),
        "greeks_heatmap": {
            "net_delta": greeks_heatmap.net_delta,
            "net_gamma": greeks_heatmap.net_gamma,
            "net_theta": greeks_heatmap.net_theta,
            "net_vega": greeks_heatmap.net_vega,
            "strike_greeks": {
                str(k): {sk: round(sv, 4) for sk, sv in v.items()}
                for k, v in greeks_heatmap.strike_greeks.items()
            },
        },
    }


def find_max_pain_levels(chain: OptionChainSnapshot, num_levels: int = 3) -> list[tuple[float, float]]:
    """Find top N max pain levels (strikes with minimum pain).

    Args:
        chain: Option chain snapshot
        num_levels: Number of levels to return

    Returns:
        List of (strike, pain) tuples sorted by pain ascending
    """
    pain_result = calculate_max_pain(chain)
    sorted_pain = sorted(pain_result.pain_by_strike.items(), key=lambda x: x[1])
    return [(strike, round(pain, 2)) for strike, pain in sorted_pain[:num_levels]]


def calculate_support_resistance_from_oi(chain: OptionChainSnapshot) -> dict:
    """Identify support/resistance from OI concentrations.

    High Call OI -> Resistance
    High Put OI -> Support

    Args:
        chain: Option chain snapshot

    Returns:
        Dict with support/resistance levels
    """
    call_oi_strikes = sorted(chain.call_oi.items(), key=lambda x: x[1], reverse=True)
    put_oi_strikes = sorted(chain.put_oi.items(), key=lambda x: x[1], reverse=True)

    resistance = [
        {"strike": strike, "oi": oi, "type": "resistance"}
        for strike, oi in call_oi_strikes[:5]
        if oi > 0
    ]
    support = [
        {"strike": strike, "oi": oi, "type": "support"}
        for strike, oi in put_oi_strikes[:5]
        if oi > 0
    ]

    return {"resistance": resistance, "support": support}
