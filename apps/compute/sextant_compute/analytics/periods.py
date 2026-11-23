"""Return periods: compound daily returns into weekly, monthly, quarterly or yearly ones.

Every period-dependent statistic (volatility, Sharpe, Sortino, VaR, CVaR, beta,
skewness, kurtosis) runs on the returns of the chosen period and annualizes with
that period's count per year. Periods are calendar periods (weeks end on Friday),
so the first and last period of a date range may be partial.
"""

from __future__ import annotations

from typing import Literal

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

_NAME_BY_COUNT = {count: period for period, count in PERIODS_PER_YEAR.items()}


def period_name(periods_per_year: int) -> str:
    """The adjective for a period count, for messages ("daily", "monthly", ...)."""
    return _NAME_BY_COUNT.get(periods_per_year, f"1/{periods_per_year}-year")


def period_returns(daily_returns: pd.Series, period: ReturnPeriod) -> pd.Series:
    """Compound simple daily returns into simple returns per period.

    Daily returns come back unchanged. Otherwise each period's return is
    ``prod(1 + r) - 1`` over its days, indexed by the period's last calendar day
    (so two series on different trading calendars still line up by period).
    """
    if period == "daily":
        return daily_returns
    clean = daily_returns.dropna()
    keys = clean.index.to_period(_PANDAS_PERIOD[period])
    compounded = (1 + clean).groupby(keys).prod() - 1
    compounded.index = compounded.index.to_timestamp(how="end").normalize()
    return compounded
