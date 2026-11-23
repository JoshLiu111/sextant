"""Drawdown analytics on a wealth series (see ``performance.total_return_index``).

A wealth series is any positive value-over-time series where dividends are
reinvested: a total-return index, a portfolio value. Its first value is the
starting point, so a loss on the first day already counts as a drawdown.
"""

from __future__ import annotations

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
