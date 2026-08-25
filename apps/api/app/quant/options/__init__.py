"""Options pricing and Greeks calculations.

Black-Scholes model with dividend yield extension for index options.
Supports CE/PE options, IV calculation, and Greeks.
"""

from app.quant.options.analytics import (
    GreeksHeatmap,
    IVRankPercentile,
    IVSurface,
    MaxPainResult,
    OptionChainSnapshot,
    PCRData,
    calculate_greeks_heatmap,
    calculate_iv_rank_percentile,
    calculate_iv_surface,
    calculate_max_pain,
    calculate_pcr,
    calculate_support_resistance_from_oi,
    find_max_pain_levels,
    get_option_chain_analytics,
)
from app.quant.options.expiry import (
    ExpiryType,
    days_to_expiry,
    get_expiry_by_type,
    get_monthly_expiry,
    get_weekly_expiry,
    parse_expiry_formula,
)
from app.quant.options.formulas import (
    ATM_STRIKE,
    LotsResult,
    StrikeResult,
    calculate_atm_strike,
    calculate_strike_by_delta,
    calculate_strike_by_percent,
    capital_pct_lots,
    delta_neutral_lots,
    gamma_neutral_lots,
    parse_strike_formula,
    theta_neutral_lots,
    vega_neutral_lots,
)
from app.quant.options.pricing import black_scholes_price, calculate_greeks, implied_volatility

__all__ = [
    "black_scholes_price",
    "calculate_greeks",
    "implied_volatility",
    "ATM_STRIKE",
    "calculate_atm_strike",
    "calculate_strike_by_delta",
    "calculate_strike_by_percent",
    "delta_neutral_lots",
    "vega_neutral_lots",
    "theta_neutral_lots",
    "gamma_neutral_lots",
    "capital_pct_lots",
    "parse_strike_formula",
    "StrikeResult",
    "LotsResult",
    "get_expiry_by_type",
    "parse_expiry_formula",
    "days_to_expiry",
    "get_weekly_expiry",
    "get_monthly_expiry",
    "ExpiryType",
    "OptionChainSnapshot",
    "IVSurface",
    "PCRData",
    "MaxPainResult",
    "GreeksHeatmap",
    "IVRankPercentile",
    "calculate_pcr",
    "calculate_max_pain",
    "calculate_iv_surface",
    "calculate_iv_rank_percentile",
    "calculate_greeks_heatmap",
    "get_option_chain_analytics",
    "find_max_pain_levels",
    "calculate_support_resistance_from_oi",
]
