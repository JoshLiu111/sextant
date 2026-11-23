"""Return periods: compound daily returns into weekly, monthly, quarterly or yearly ones.

Every period-dependent statistic (volatility, Sharpe, Sortino, VaR, CVaR, beta,
skewness, kurtosis) runs on the returns of the chosen period and annualizes with
that period's count per year. Periods are calendar periods (weeks end on Friday).
A date range that starts or ends inside a period leaves a partial first or last
period; those are dropped, so every period return covers a whole period.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd

ReturnPeriod = Literal["daily", "weekly", "monthly", "quarterly", "yearly"]

PERIODS_PER_YEAR: dict[ReturnPeriod, int] = {
    "daily": 252,
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "yearly": 1,
}

_PANDAS_PERIOD: dict[ReturnPeriod, str] = {"weekly": "W-FRI", "monthly": "M", "quarterly": "Q", "yearly": "Y"}

_MISSING_WEEKDAYS_ALLOWED: dict[ReturnPeriod, int] = {"weekly": 1, "monthly": 3, "quarterly": 3, "yearly": 3}
"""Most weekdays an edge period may lack and still count as whole: room for market
holidays at a period's edge (New Year's Day, Good Friday on April 1, Labor Day on
September 1) without letting a stub of a period pass as a full one."""

_NAME_BY_COUNT ={count: period for period, count in PERIODS_PER_YEAR.items()}


def period_name(periods_per_year: int) -> str:
    """The adjective for a period count, for messages ("daily", "monthly", ...)."""
    return _NAME_BY_COUNT.get(periods_per_year, f"1/{periods_per_year}-year")


def period_returns(daily_returns: pd.Series, period: ReturnPeriod) -> pd.Series:
    """Compound simple daily returns into simple returns per period.

    Daily returns come back unchanged. Otherwise each period's return is
    ``prod(1 + r) - 1`` over its days, indexed by the period's last calendar day
    (so two series on different trading calendars still line up by period).

    The first period is dropped when the returns start more than
    ``_MISSING_WEEKDAYS_ALLOWED`` weekdays into it, and the last when they end that
    many weekdays before its end: a stub is not a full period, and counting it as
    one skews every statistic.
    """
    if period == "daily":
        return daily_returns
    clean = daily_returns.dropna()
    keys = clean.index.to_period(_PANDAS_PERIOD[period])
    compounded = (1 + clean).groupby(keys).prod() - 1
    if len(compounded):
        allowed = _MISSING_WEEKDAYS_ALLOWED[period]
        first, last = compounded.index[0], compounded.index[-1]
        complete = pd.Series(True, index=compounded.index)
        if _weekdays(first.start_time.date(), clean.index[0].date()) > allowed:
            complete[first] = False
        if _weekdays(clean.index[-1].date() + timedelta(days=1), last.end_time.date() + timedelta(days=1)) > allowed:
            complete[last] = False
        compounded = compounded[complete]
    compounded.index = compounded.index.to_timestamp(how="end").normalize()
    return compounded


def _weekdays(start: date, end: date) -> int:
    """Weekdays (Monday to Friday) in ``[start, end)``."""
    return int(np.busday_count(start, end))
