"""Cox-Ross-Rubinstein binomial tree for European and American options.

Pure functions on floats. Units follow ``analytics.options``: decimals for
rates, yields and volatility; years for time.
"""

from __future__ import annotations

import math

import numpy as np

from sextant_compute.analytics.errors import MetricError
from sextant_compute.analytics.options import OptionType


def tree_price(
    kind: OptionType,
    s: float,
    k: float,
    t: float,
    sigma: float,
    r: float,
    q: float,
    steps: int,
    *,
    american: bool,
) -> float:
    """Price on a CRR tree with ``steps`` steps: u = e^(σ√Δt), d = 1/u,
    p = (e^((r−q)Δt) − d) / (u − d). American options compare holding with
    exercising at every node."""
    dt = t / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise MetricError(
            "The tree has no valid risk-neutral probability with these inputs: increase the number of steps."
        )
    disc = math.exp(-r * dt)
    sign = 1.0 if kind == "call" else -1.0

    # Underlying prices at expiry, from all-down (j = 0) to all-up (j = steps).
    j = np.arange(steps + 1)
    prices = s * u**j * d ** (steps - j)
    values = np.maximum(sign * (prices - k), 0.0)
    for _ in range(steps):
        values = disc * (p * values[1:] + (1.0 - p) * values[:-1])
        if american:
            prices = prices[:-1] * u  # one step earlier: s·u^j·d^(n−1−j)
            values = np.maximum(values, sign * (prices - k))
    return float(values[0])


def steps_grid(steps: int, points: int = 25) -> list[int]:
    """Step counts from 1 (or a few) up to ``steps``, about evenly spaced, ending at ``steps``."""
    return sorted({max(1, round(steps * i / points)) for i in range(1, points + 1)} | {steps})
