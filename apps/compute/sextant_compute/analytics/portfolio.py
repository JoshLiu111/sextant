"""Portfolio return series from per-asset prices, weights or quantities.

A weighted portfolio (the demo) holds constant weights, rebalanced at every close:
its daily return is the weighted sum of the assets' simple daily returns,
``r_p,t = sum_i w_i * r_i,t``, over the dates every asset has a return.

A saved portfolio holds fixed quantities instead (buy and hold): its value is
``V_t = sum_i q_i * close_i,0 * TRI_i,t`` with dividends reinvested, and its
returns are ``V_t / V_t-1 - 1``.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from sextant_compute.analytics import performance
from sextant_compute.analytics.errors import MissingData


def weighted_returns(returns: Mapping[str, pd.Series], weights: Mapping[str, float]) -> pd.Series:
    """Daily-rebalanced portfolio returns on the dates shared by every asset."""
    if not weights:
        raise MissingData("needs at least one holding")
    aligned = pd.concat({asset: returns[asset] for asset in weights}, axis=1, join="inner").dropna()
    if aligned.empty:
        raise MissingData("the holdings share no trading days")
    return aligned.mul(pd.Series(weights)).sum(axis=1)


def buy_and_hold_value(prices: Mapping[str, pd.DataFrame], quantities: Mapping[str, float]) -> pd.Series:
    """Value of holding fixed quantities from the first close on, with dividends reinvested.

    Each holding starts at ``quantity * first close`` and grows with its total
    return index; the portfolio is never rebalanced. ``prices`` frames have
    ``close`` and ``dividend`` columns on the same dates.
    """
    if not quantities:
        raise MissingData("needs at least one holding")
    values = [
        q * prices[t]["close"].iloc[0] * performance.total_return_index(prices[t]["close"], prices[t]["dividend"])
        for t, q in quantities.items()
    ]
    return pd.concat(values, axis=1, join="inner").sum(axis=1)


def wealth_index(returns: pd.Series, start: pd.Timestamp) -> pd.Series:
    """Wealth from investing 1 at the ``start`` close (the day before the first return)."""
    growth = (1 + returns).cumprod()
    return pd.concat([pd.Series([1.0], index=pd.DatetimeIndex([start], name=returns.index.name)), growth])
