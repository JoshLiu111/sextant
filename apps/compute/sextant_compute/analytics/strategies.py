"""Multi-leg option strategies: sums of Black-Scholes legs and the underlying.

Pure functions on floats. Every leg shares one market (spot, time, volatility,
rate, dividend yield). Units follow ``analytics.options``: decimals for rates,
years for time, and the same Greek scaling.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from sextant_compute.analytics import options as bs

Instrument = Literal["call", "put", "underlying"]
Greek = Literal["delta", "gamma", "vega", "theta", "rho"]
GREEKS: tuple[Greek, ...] = ("delta", "gamma", "vega", "theta", "rho")


@dataclass(frozen=True)
class Leg:
    instrument: Instrument
    quantity: float
    """Signed: positive for long, negative for short."""
    strike: float | None = None
    """Required for calls and puts; ignored for the underlying."""


@dataclass(frozen=True)
class Market:
    spot: float
    time_to_expiry: float
    volatility: float
    risk_free_rate: float
    dividend_yield: float


def _bs_args(leg: Leg, m: Market) -> tuple[float, float, float, float, float, float]:
    assert leg.strike is not None
    return m.spot, leg.strike, m.time_to_expiry, m.volatility, m.risk_free_rate, m.dividend_yield


def leg_value(leg: Leg, m: Market) -> float:
    """Theoretical value today of one unit of the leg (unsigned)."""
    if leg.instrument == "underlying":
        return m.spot
    return bs.bs_price(leg.instrument, *_bs_args(leg, m))


def leg_payoff(leg: Leg, spot: float) -> float:
    """Value of one unit at expiry for an underlying price ``spot``."""
    if leg.instrument == "underlying":
        return spot
    assert leg.strike is not None
    return bs.payoff_at_expiry(leg.instrument, spot, leg.strike)


def _leg_greek(greek: Greek, leg: Leg, m: Market) -> float:
    if leg.instrument == "underlying":
        return 1.0 if greek == "delta" else 0.0
    args = _bs_args(leg, m)
    kind = leg.instrument
    if greek == "delta":
        return bs.delta(kind, *args)
    if greek == "gamma":
        return bs.gamma(*args)
    if greek == "vega":
        return bs.vega(*args)
    if greek == "theta":
        return bs.theta(kind, *args)
    return bs.rho(kind, *args)


def value(legs: Sequence[Leg], m: Market) -> float:
    """Signed theoretical value today; positive means the strategy costs money to open."""
    return sum(leg.quantity * leg_value(leg, m) for leg in legs)


def payoff(legs: Sequence[Leg], spot: float) -> float:
    return sum(leg.quantity * leg_payoff(leg, spot) for leg in legs)


def greek(name: Greek, legs: Sequence[Leg], m: Market) -> float:
    return sum(leg.quantity * _leg_greek(name, leg, m) for leg in legs)


def strikes(legs: Sequence[Leg]) -> list[float]:
    return sorted({leg.strike for leg in legs if leg.instrument != "underlying" and leg.strike is not None})


def spot_grid(legs: Sequence[Leg], m: Market) -> list[float]:
    return bs.spot_grid(m.spot, *strikes(legs))


def time_grid(t: float, points: int = 60) -> list[float]:
    """Times to expiry from about one day (or half of ``t`` if shorter) to ``2t``, including ``t``."""
    lo, hi = min(1.0 / 365.0, t / 2.0), 2.0 * t
    step = (hi - lo) / (points - 1)
    return sorted({round(lo + i * step, 10) for i in range(points)} | {t})


def profit_at_expiry_curve(legs: Sequence[Leg], m: Market) -> list[tuple[float, float]]:
    cost = value(legs, m)
    return [(x, payoff(legs, x) - cost) for x in spot_grid(legs, m)]


def profit_today_curve(legs: Sequence[Leg], m: Market) -> list[tuple[float, float]]:
    cost = value(legs, m)
    return [(x, value(legs, replace(m, spot=x)) - cost) for x in spot_grid(legs, m)]


def greek_vs_spot(name: Greek, legs: Sequence[Leg], m: Market) -> list[tuple[float, float]]:
    return [(x, greek(name, legs, replace(m, spot=x))) for x in spot_grid(legs, m)]


def greek_vs_time(name: Greek, legs: Sequence[Leg], m: Market) -> list[tuple[float, float]]:
    return [(t, greek(name, legs, replace(m, time_to_expiry=t))) for t in time_grid(m.time_to_expiry)]


def _expiry_extremes(legs: Sequence[Leg], m: Market) -> tuple[float, float, float]:
    """(lowest, highest) profit at expiry over the kinks of the payoff (0 and each
    strike), and the payoff's slope above the highest strike."""
    cost = value(legs, m)
    profits = [payoff(legs, x) - cost for x in [0.0, *strikes(legs)]]
    slope = sum(leg.quantity for leg in legs if leg.instrument in ("call", "underlying"))
    return min(profits), max(profits), slope


class Unlimited(Exception):
    """The answer is a valid "unlimited", not a failure: the payoff has no bound.
    The message says why."""


def max_profit(legs: Sequence[Leg], m: Market) -> float:
    """Highest profit at expiry over all underlying prices (net of the opening cost).

    Raises ``Unlimited`` when the profit has no ceiling."""
    _, high, slope = _expiry_extremes(legs, m)
    if slope > 1e-12:
        raise Unlimited("The profit keeps rising as the underlying rises.")
    return high


def max_loss(legs: Sequence[Leg], m: Market) -> float:
    """Largest loss at expiry, as a positive amount (0 if the strategy can't lose).

    Raises ``Unlimited`` when the loss has no floor."""
    low, _, slope = _expiry_extremes(legs, m)
    if slope < -1e-12:
        raise Unlimited("The loss keeps growing as the underlying rises.")
    return max(-low, 0.0)
