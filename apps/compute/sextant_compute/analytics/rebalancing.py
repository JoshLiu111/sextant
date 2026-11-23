"""Backtest a rebalancing rule: hold target weights, let them drift, reset them when the rule says so.

Each holding starts at its target weight of a wealth of 1 at the first close and
grows with its own daily total return. After each close the rule may rebalance:

- calendar (``monthly`` / ``quarterly`` / ``yearly``): at the last trading day of
  each period (the next trading day falls in a new period);
- ``drift``: when any holding's weight is more than ``threshold`` (absolute, e.g.
  0.05 = 5 percentage points) away from its target.

The last day is never a rebalance day (nothing follows it). Rebalancing is
frictionless (no costs or taxes). Never rebalancing is buy and hold.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sextant_compute.analytics.errors import MissingData

CalendarRule = Literal["monthly", "quarterly", "yearly"]
Rule = CalendarRule | Literal["drift", "never"]

_PERIOD: dict[str, str] = {"monthly": "M", "quarterly": "Q", "yearly": "Y"}


@dataclass(frozen=True)
class Backtest:
    wealth: pd.Series
    """Wealth from investing 1 at the first close (1.0 on the first date)."""
    rebalances: tuple[pd.Timestamp, ...]
    """Closes at which the weights were reset to target."""
    turnover: float
    """Total one-way turnover: the sum over rebalances of half the absolute weight changes."""


def _rebalance_days(index: pd.DatetimeIndex, rule: CalendarRule) -> np.ndarray:
    periods = index.to_period(_PERIOD[rule])
    ends = np.zeros(len(index), dtype=bool)
    ends[:-1] = periods[1:] != periods[:-1]
    return ends


def run(
    returns: pd.DataFrame,
    start: pd.Timestamp,
    weights: Mapping[str, float],
    rule: Rule,
    *,
    threshold: float | None = None,
) -> Backtest:
    """Backtest ``rule`` on simple daily ``returns`` (one column per holding, no NaNs).

    ``start`` is the close the portfolio is bought at (the date before the first return).
    """
    if not weights:
        raise MissingData("needs at least one holding")
    if returns.empty:
        raise MissingData("needs at least one daily return")
    if rule == "drift" and threshold is None:
        raise ValueError("a drift rule needs a threshold")
    tickers = list(weights)
    target = np.array([weights[t] for t in tickers], dtype=float)
    growth = 1 + returns[tickers].to_numpy(dtype=float)
    calendar = _rebalance_days(returns.index, rule) if rule in _PERIOD else None

    holdings = target.copy()
    wealth = np.empty(len(returns) + 1)
    wealth[0] = holdings.sum()
    rebalances: list[pd.Timestamp] = []
    turnover = 0.0
    last = len(returns) - 1
    for day in range(len(returns)):
        holdings = holdings * growth[day]
        total = holdings.sum()
        wealth[day + 1] = total
        if day == last or rule == "never":
            continue
        drifted = holdings / total
        if calendar is not None:
            due = bool(calendar[day])
        else:
            due = bool(np.max(np.abs(drifted - target)) > threshold)
        if due:
            turnover += float(np.abs(drifted - target).sum()) / 2
            holdings = target * total
            rebalances.append(returns.index[day])
    index = pd.DatetimeIndex([start], name=returns.index.name).append(returns.index)
    return Backtest(wealth=pd.Series(wealth / wealth[0], index=index), rebalances=tuple(rebalances), turnover=turnover)
