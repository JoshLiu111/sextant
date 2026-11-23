"""The P3 risk & performance metric set, shared by every tool that shows it.

Risk & Performance (per ticker) and My Portfolio (per portfolio) both call
``risk_metric_set`` so their numbers come from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from sextant_compute.analytics import performance, risk
from sextant_compute.envelope import Detailed, MetricResult, SeriesResult, metric, series

METRIC_NAMES = (
    "annualized_return",
    "annualized_volatility",
    "max_drawdown",
    "sharpe",
    "sortino",
    "var",
    "cvar",
    "parametric_var",
    "parametric_cvar",
    "cornish_fisher_var",
    "cornish_fisher_cvar",
    "beta",
    "treynor",
    "information_ratio",
    "alpha",
    "upside_capture",
    "downside_capture",
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
) -> dict[str, MetricResult]:
    """Every P3 metric for one return series, keyed by metric name (see ``METRIC_NAMES``).

    ``returns`` are simple daily returns; ``wealth`` is the matching wealth series
    (1.0 on the day before the first return).
    """
    return {
        "annualized_return": metric(lambda: performance.annualized_return(returns), unit="decimal"),
        "annualized_volatility": metric(lambda: performance.annualized_volatility(returns), unit="decimal"),
        "max_drawdown": metric(lambda: _max_drawdown(wealth), unit="decimal"),
        "sharpe": metric(lambda: performance.sharpe_ratio(returns, risk_free_rate), unit="ratio"),
        "sortino": metric(lambda: performance.sortino_ratio(returns, risk_free_rate), unit="ratio"),
        "var": metric(lambda: risk.historical_var(returns, confidence), unit="decimal"),
        "cvar": metric(lambda: risk.historical_cvar(returns, confidence), unit="decimal"),
        "parametric_var": metric(lambda: risk.parametric_var(returns, confidence), unit="decimal"),
        "parametric_cvar": metric(lambda: risk.parametric_cvar(returns, confidence), unit="decimal"),
        "cornish_fisher_var": metric(lambda: risk.cornish_fisher_var(returns, confidence), unit="decimal"),
        "cornish_fisher_cvar": metric(lambda: risk.cornish_fisher_cvar(returns, confidence), unit="decimal"),
        "beta": metric(lambda: risk.beta(returns, benchmark_returns), unit="ratio"),
        "treynor": metric(lambda: risk.treynor_ratio(returns, benchmark_returns, risk_free_rate), unit="decimal"),
        "information_ratio": metric(lambda: risk.information_ratio(returns, benchmark_returns), unit="ratio"),
        "alpha": metric(lambda: risk.capm_alpha(returns, benchmark_returns, risk_free_rate), unit="decimal"),
        "upside_capture": metric(lambda: risk.upside_capture(returns, benchmark_returns), unit="decimal"),
        "downside_capture": metric(lambda: risk.downside_capture(returns, benchmark_returns), unit="decimal"),
    }


def date_series(compute_values: Callable[[], pd.Series], *, y_unit: str = "decimal") -> SeriesResult:
    """A chart series of ``(ISO date, value)`` points from a date-indexed Series."""
    return series(
        lambda: [(ts.date().isoformat(), float(v)) for ts, v in compute_values().items()],
        x_unit="date",
        y_unit=y_unit,
    )
