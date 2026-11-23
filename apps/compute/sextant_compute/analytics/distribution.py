"""Shape of a return distribution: skewness, excess kurtosis and a histogram.

Inputs are simple returns of any period (see ``periods.period_returns``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.periods import PERIODS_PER_YEAR, period_name


def _require(returns: pd.Series, minimum: int, periods_per_year: int) -> pd.Series:
    clean = returns.dropna()
    if len(clean) < minimum:
        raise MissingData(f"needs at least {minimum} {period_name(periods_per_year)} returns, got {len(clean)}")
    return clean


def _varies(r: pd.Series) -> pd.Series:
    if float(r.std(ddof=1)) == 0:
        raise MissingData("returns do not vary, so the shape of their distribution is undefined")
    return r


def skewness(returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR["daily"]) -> float:
    """Adjusted Fisher-Pearson sample skewness G1 (Excel ``SKEW``); 0 for a symmetric distribution."""
    return float(_varies(_require(returns, 3, periods_per_year)).skew())


def excess_kurtosis(returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR["daily"]) -> float:
    """Bias-corrected sample excess kurtosis G2 (Excel ``KURT``); 0 for a normal distribution."""
    return float(_varies(_require(returns, 4, periods_per_year)).kurt())


@dataclass(frozen=True)
class Histogram:
    centers: list[float]
    counts: list[int]
    bin_width: float
    observations: int


MAX_BINS = 50
MIN_BINS = 5


def histogram(returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR["daily"]) -> Histogram:
    """Equal-width bins from the lowest to the highest return; ``ceil(sqrt(n))`` bins, 5 to 50."""
    r = _varies(_require(returns, 2, periods_per_year))
    bins = min(MAX_BINS, max(MIN_BINS, math.ceil(math.sqrt(len(r)))))
    counts, edges = np.histogram(r.to_numpy(), bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return Histogram(
        centers=[float(c) for c in centers],
        counts=[int(c) for c in counts],
        bin_width=float(edges[1] - edges[0]),
        observations=len(r),
    )
