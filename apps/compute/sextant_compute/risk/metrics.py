"""The P3 risk & performance metric set, shared by every tool that shows it.

Risk & Performance (per ticker) and My Portfolio (per portfolio) both call
``risk_metric_set`` so their numbers come from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from sextant_compute.analytics import performance, risk
from sextant_compute.analytics.periods import PERIODS_PER_YEAR, ReturnPeriod, period_returns
from sextant_compute.envelope import Detailed, MetricResult, SeriesResult, metric, series

METRIC_NAMES = (
    "annualized_return",
    "annualized_volatility",
    "max_drawdown",
    "sharpe",
    "sortino",
    "var",
    "cvar",
    "beta",
)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _max_drawdown(wealth: pd.Series) -> Detailed:
    mdd = risk.max_drawdown(wealth)
    return Detailed(mdd.depth, {"peak": _iso(mdd.peak), "trough": _iso(mdd.trough), "recovery": _iso(mdd.recovery)})


def risk_metric_set(
    returns: pd.Series,
    wealth: pd.Series,
    benchmark_returns: pd.Series,
    *,
    confidence: float,
    risk_free_rate: float,
    period: ReturnPeriod = "daily",
) -> dict[str, MetricResult]:
    """Every P3 metric for one return series, keyed by metric name (see ``METRIC_NAMES``).

    ``returns`` and ``benchmark_returns`` are simple daily returns; ``wealth`` is
    the matching wealth series (1.0 on the day before the first return).

    ``period`` picks the return period for the period-dependent metrics
    (volatility, Sharpe, Sortino, VaR, CVaR, beta), annualized with that period's
    count per year. Annualized return and max drawdown describe the whole wealth
    path, so they always use the daily data.
    """
    per_year = PERIODS_PER_YEAR[period]
    r = period_returns(returns, period)
    b = period_returns(benchmark_returns, period)
    return {
        "annualized_return": metric(lambda: performance.annualized_return(returns), unit="decimal"),
        "annualized_volatility": metric(lambda: performance.annualized_volatility(r, per_year), unit="decimal"),
        "max_drawdown": metric(lambda: _max_drawdown(wealth), unit="decimal"),
        "sharpe": metric(lambda: performance.sharpe_ratio(r, risk_free_rate, per_year), unit="ratio"),
        "sortino": metric(lambda: performance.sortino_ratio(r, risk_free_rate, per_year), unit="ratio"),
        "var": metric(lambda: risk.historical_var(r, confidence, period=period), unit="decimal"),
        "cvar": metric(lambda: risk.historical_cvar(r, confidence, period=period), unit="decimal"),
        "beta": metric(lambda: risk.beta(r, b), unit="ratio"),
    }


def date_series(compute_values: Callable[[], pd.Series], *, y_unit: str = "decimal") -> SeriesResult:
    """A chart series of ``(ISO date, value)`` points from a date-indexed Series."""
    return series(
        lambda: [(ts.date().isoformat(), float(v)) for ts, v in compute_values().items()],
        x_unit="date",
        y_unit=y_unit,
    )
