"""The P3 risk & performance metric set, shared by every tool that shows it.

Risk & Performance (per ticker) and My Portfolio (per portfolio) both call
``risk_metric_set`` so their numbers come from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from sextant_compute.analytics import performance, risk
from sextant_compute.envelope import Detailed, MetricResult, MetricStatus, SeriesResult, metric, series

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

METRIC_UNITS: dict[str, str] = {
    "annualized_return": "decimal",
    "annualized_volatility": "decimal",
    "max_drawdown": "decimal",
    "sharpe": "ratio",
    "sortino": "ratio",
    "var": "decimal",
    "cvar": "decimal",
    "beta": "ratio",
}


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
) -> dict[str, MetricResult]:
    """Every P3 metric for one return series, keyed by metric name (see ``METRIC_NAMES``).

    ``returns`` are simple daily returns; ``wealth`` is the matching wealth series
    (1.0 on the day before the first return).
    """
    computations: dict[str, Callable[[], float | Detailed]] = {
        "annualized_return": lambda: performance.annualized_return(returns),
        "annualized_volatility": lambda: performance.annualized_volatility(returns),
        "max_drawdown": lambda: _max_drawdown(wealth),
        "sharpe": lambda: performance.sharpe_ratio(returns, risk_free_rate),
        "sortino": lambda: performance.sortino_ratio(returns, risk_free_rate),
        "var": lambda: risk.historical_var(returns, confidence),
        "cvar": lambda: risk.historical_cvar(returns, confidence),
        "beta": lambda: risk.beta(returns, benchmark_returns),
    }
    return {name: metric(computations[name], unit=METRIC_UNITS[name]) for name in METRIC_NAMES}


def missing_metric_set(reason: str) -> dict[str, MetricResult]:
    """Every P3 metric as ``missing_data`` with ``reason``, e.g. for a ticker the
    user's provider has no prices for."""
    return {
        name: MetricResult(value=None, status=MetricStatus.MISSING_DATA, reason=reason, unit=METRIC_UNITS[name])
        for name in METRIC_NAMES
    }


def missing_series(reason: str, *, y_unit: str = "decimal") -> SeriesResult:
    """A date series that could not be built, with ``reason``."""
    return SeriesResult(status=MetricStatus.MISSING_DATA, reason=reason, x_unit="date", y_unit=y_unit)


def date_series(compute_values: Callable[[], pd.Series], *, y_unit: str = "decimal") -> SeriesResult:
    """A chart series of ``(ISO date, value)`` points from a date-indexed Series."""
    return series(
        lambda: [(ts.date().isoformat(), float(v)) for ts, v in compute_values().items()],
        x_unit="date",
        y_unit=y_unit,
    )
