"""Options Lab package: Black-Scholes greeks + multi-leg payoff analysis."""

from app.options.greeks import bs_price, implied_vol
from app.options.lab import OptionsLabError, ResolvedLeg

__all__ = ["bs_price", "implied_vol", "OptionsLabError", "ResolvedLeg"]
