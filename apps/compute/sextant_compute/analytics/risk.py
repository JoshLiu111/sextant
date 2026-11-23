"""Risk analytics: drawdowns on a wealth series; VaR, CVaR and beta on return series.

A wealth series is any positive value-over-time series where dividends are
reinvested: a total-return index, a portfolio value. Its first value is the
starting point, so a loss on the first day already counts as a drawdown.

Return series are simple periodic (daily) returns indexed by date, as built by
``performance.total_returns``; a portfolio's return series works the same way.
VaR and CVaR are one-period (daily) figures reported as positive losses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from sextant_compute.analytics.errors import MissingData


def _require(wealth: pd.Series) -> pd.Series:
    clean = wealth.dropna()
    if len(clean) < 2:
        raise MissingData(f"needs at least 2 daily prices, got {len(clean)}")
    return clean


def drawdown(wealth: pd.Series) -> pd.Series:
    """Underwater curve: wealth / running peak - 1 (0 at a new high, negative below it)."""
    w = _require(wealth)
    return w / w.cummax() - 1


@dataclass(frozen=True)
class MaxDrawdown:
    depth: float
    """Largest peak-to-trough fall as a positive decimal (0.45 = a 45% fall)."""
    peak: date
    """Last high before the fall (the drawdown's start)."""
    trough: date
    """Lowest point (the drawdown's end)."""
    recovery: date | None
    """First day back at the peak level, or None if not recovered within the series."""


def max_drawdown(wealth: pd.Series) -> MaxDrawdown:
    underwater = drawdown(wealth)
    trough_ts = underwater.idxmin()
    before = underwater.loc[:trough_ts]
    peak_ts = before[before >= 0].index[-1]
    after = underwater.loc[trough_ts:]
    recovered = after[after >= 0]
    return MaxDrawdown(
        depth=-float(underwater.loc[trough_ts]),
        peak=pd.Timestamp(peak_ts).date(),
        trough=pd.Timestamp(trough_ts).date(),
        recovery=pd.Timestamp(recovered.index[0]).date() if not recovered.empty else None,
    )


def beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """OLS beta of ``returns`` on ``benchmark_returns``: Cov(r, b) / Var(b), both ddof=1.

    Raw (not excess) simple returns, on the dates where both series have a value.
    """
    both = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(both) < 2:
        raise MissingData(f"needs at least 2 returns on dates shared with the benchmark, got {len(both)}")
    r, b = both.iloc[:, 0], both.iloc[:, 1]
    variance = float(b.var(ddof=1))
    if variance == 0:
        raise MissingData("the benchmark's returns do not vary, so beta is undefined")
    return float(r.cov(b, ddof=1)) / variance


def _tail(returns: pd.Series, confidence: float, period: str) -> pd.Series:
    """The ``k = ceil(n * (1 - confidence))`` worst returns, worst first."""
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
    clean = returns.dropna()
    tail_probability = 1 - confidence
    # Round away float noise so that e.g. 20 * 0.05 counts as exactly 1 observation.
    needed = math.ceil(round(1 / tail_probability, 9))
    if len(clean) < needed:
        raise MissingData(
            f"needs at least {needed} {period} returns for a {confidence:.1%} VaR, got {len(clean)}"
        )
    k = math.ceil(round(len(clean) * tail_probability, 9))
    return clean.sort_values().iloc[:k]


def historical_var(returns: pd.Series, confidence: float = 0.95, *, period: str = "daily") -> float:
    """Historical Value at Risk over one period, as a positive loss (0.03 = a 3% loss).

    The empirical (1 - confidence) quantile without interpolation: with n returns
    sorted ascending, VaR = -r_(k) where k = ceil(n * (1 - confidence)). Needs
    k >= 1, i.e. at least 1 / (1 - confidence) returns. Negative if even the
    tail return is a gain.
    """
    return -float(_tail(returns, confidence, period).iloc[-1])


def historical_cvar(returns: pd.Series, confidence: float = 0.95, *, period: str = "daily") -> float:
    """Historical CVaR (expected shortfall): minus the mean of the k worst returns.

    Same k and sign convention as ``historical_var``, so CVaR >= VaR always.
    """
    return -float(_tail(returns, confidence, period).mean())
