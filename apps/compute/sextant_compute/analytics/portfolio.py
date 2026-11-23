"""Portfolio return series from per-asset return series and weights.

The portfolio holds constant weights, rebalanced at every close: its daily
return is the weighted sum of the assets' simple daily returns,
``r_p,t = sum_i w_i * r_i,t``, over the dates every asset has a return.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from sextant_compute.analytics.errors import MissingData


def weighted_returns(returns: Mapping[str, pd.Series], weights: Mapping[str, float]) -> pd.Series:
    """Daily-rebalanced portfolio returns on the dates shared by every asset."""
    if not weights:
        raise MissingData("needs at least one holding")
    aligned = pd.concat({asset: returns[asset] for asset in weights}, axis=1, join="inner").dropna()
    if aligned.empty:
        raise MissingData("the holdings share no trading days")
    return aligned.mul(pd.Series(weights)).sum(axis=1)


def wealth_index(returns: pd.Series, start: pd.Timestamp) -> pd.Series:
    """Wealth from investing 1 at the ``start`` close (the day before the first return)."""
    growth = (1 + returns).cumprod()
    return pd.concat([pd.Series([1.0], index=pd.DatetimeIndex([start], name=returns.index.name)), growth])
