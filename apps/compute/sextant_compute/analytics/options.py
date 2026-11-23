"""Black-Scholes(-Merton) for European options with a continuous dividend yield.

Pure functions on floats. Units: rates, yields and volatility are decimals
(0.05 = 5%), time is in years.
"""

from __future__ import annotations

import math
from typing import Literal

from sextant_compute.analytics.errors import MetricError, MissingData

OptionType = Literal["call", "put"]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1_d2(s: float, k: float, t: float, sigma: float, r: float, q: float) -> tuple[float, float]:
    vol_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def bs_price(kind: OptionType, s: float, k: float, t: float, sigma: float, r: float, q: float) -> float:
    d1, d2 = _d1_d2(s, k, t, sigma, r, q)
    disc_s, disc_k = s * math.exp(-q * t), k * math.exp(-r * t)
    if kind == "call":
        return disc_s * _norm_cdf(d1) - disc_k * _norm_cdf(d2)
    return disc_k * _norm_cdf(-d2) - disc_s * _norm_cdf(-d1)


def payoff_at_expiry(kind: OptionType, s: float, k: float) -> float:
    return max(s - k, 0.0) if kind == "call" else max(k - s, 0.0)


def spot_grid(*anchors: float, points: int = 101) -> list[float]:
    """Spot prices from 50% of the lowest anchor (spot, strikes) to 150% of the
    highest, including every anchor exactly."""
    lo, hi = 0.5 * min(anchors), 1.5 * max(anchors)
    step = (hi - lo) / (points - 1)
    grid = {round(lo + i * step, 10) for i in range(points)} | set(anchors)
    return sorted(grid)


IV_LOW, IV_HIGH = 1e-6, 5.0


def implied_volatility(
    kind: OptionType, market_price: float | None, s: float, k: float, t: float, r: float, q: float
) -> float:
    """Volatility that makes the BS price equal ``market_price`` (bisection on [1e-6, 5])."""
    if market_price is None:
        raise MissingData("Enter a market price to solve for implied volatility.")
    disc_s, disc_k = s * math.exp(-q * t), k * math.exp(-r * t)
    if kind == "call":
        lower, upper = max(disc_s - disc_k, 0.0), disc_s
    else:
        lower, upper = max(disc_k - disc_s, 0.0), disc_k
    if market_price <= lower:
        raise MetricError(
            f"No implied volatility: the price must be above the option's discounted intrinsic value ({lower:.4f})."
        )
    if market_price >= upper:
        raise MetricError(
            f"No implied volatility: the price must be below the no-arbitrage upper bound ({upper:.4f})."
        )

    lo, hi = IV_LOW, IV_HIGH
    if market_price > bs_price(kind, s, k, t, hi, r, q):
        raise MetricError("No implied volatility: the price implies a volatility above 500%.")
    if market_price < bs_price(kind, s, k, t, lo, r, q):
        raise MetricError("No implied volatility: the price is too close to intrinsic value to solve.")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if bs_price(kind, s, k, t, mid, r, q) < market_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# Greek scaling (shown to users, stated in the explainers):
#   delta, gamma: per $1 move in spot
#   vega: per 1 volatility point (0.01), i.e. dV/dsigma / 100
#   theta: per calendar day, i.e. dV/dt / 365 (negative for a long option that decays)
#   rho: per 1 percentage point (0.01) of the rate, i.e. dV/dr / 100


def delta(kind: OptionType, s: float, k: float, t: float, sigma: float, r: float, q: float) -> float:
    d1, _ = _d1_d2(s, k, t, sigma, r, q)
    growth = math.exp(-q * t)
    return growth * _norm_cdf(d1) if kind == "call" else -growth * _norm_cdf(-d1)


def gamma(s: float, k: float, t: float, sigma: float, r: float, q: float) -> float:
    d1, _ = _d1_d2(s, k, t, sigma, r, q)
    return math.exp(-q * t) * _norm_pdf(d1) / (s * sigma * math.sqrt(t))


def vega(s: float, k: float, t: float, sigma: float, r: float, q: float) -> float:
    d1, _ = _d1_d2(s, k, t, sigma, r, q)
    return s * math.exp(-q * t) * _norm_pdf(d1) * math.sqrt(t) / 100.0


def theta(kind: OptionType, s: float, k: float, t: float, sigma: float, r: float, q: float) -> float:
    d1, d2 = _d1_d2(s, k, t, sigma, r, q)
    disc_s, disc_k = s * math.exp(-q * t), k * math.exp(-r * t)
    decay = -disc_s * _norm_pdf(d1) * sigma / (2.0 * math.sqrt(t))
    if kind == "call":
        per_year = decay - r * disc_k * _norm_cdf(d2) + q * disc_s * _norm_cdf(d1)
    else:
        per_year = decay + r * disc_k * _norm_cdf(-d2) - q * disc_s * _norm_cdf(-d1)
    return per_year / 365.0


def rho(kind: OptionType, s: float, k: float, t: float, sigma: float, r: float, q: float) -> float:
    _, d2 = _d1_d2(s, k, t, sigma, r, q)
    disc_k = k * math.exp(-r * t)
    per_unit = t * disc_k * _norm_cdf(d2) if kind == "call" else -t * disc_k * _norm_cdf(-d2)
    return per_unit / 100.0
