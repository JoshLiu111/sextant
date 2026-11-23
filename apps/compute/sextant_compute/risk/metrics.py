"""The P3 risk & performance metric set, shared by every tool that shows it.

Risk & Performance (per ticker) and My Portfolio (per portfolio) both call
``risk_metric_set`` so their numbers come from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import cache
from typing import Literal

import pandas as pd

from sextant_compute.analytics import factors as factor_models
from sextant_compute.analytics import performance, risk
from sextant_compute.envelope import Detailed, MetricResult, MetricStatus, MissingData, SeriesResult, metric, series

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

METRIC_UNITS: dict[str, str] = {
    "annualized_return": "decimal",
    "annualized_volatility": "decimal",
    "max_drawdown": "decimal",
    "sharpe": "ratio",
    "sortino": "ratio",
    "var": "decimal",
    "cvar": "decimal",
    "parametric_var": "decimal",
    "parametric_cvar": "decimal",
    "cornish_fisher_var": "decimal",
    "cornish_fisher_cvar": "decimal",
    "beta": "ratio",
    "treynor": "decimal",
    "information_ratio": "ratio",
    "alpha": "decimal",
    "upside_capture": "decimal",
    "downside_capture": "decimal",
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
        "parametric_var": lambda: risk.parametric_var(returns, confidence),
        "parametric_cvar": lambda: risk.parametric_cvar(returns, confidence),
        "cornish_fisher_var": lambda: risk.cornish_fisher_var(returns, confidence),
        "cornish_fisher_cvar": lambda: risk.cornish_fisher_cvar(returns, confidence),
        "beta": lambda: risk.beta(returns, benchmark_returns),
        "treynor": lambda: risk.treynor_ratio(returns, benchmark_returns, risk_free_rate),
        "information_ratio": lambda: risk.information_ratio(returns, benchmark_returns),
        "alpha": lambda: risk.capm_alpha(returns, benchmark_returns, risk_free_rate),
        "upside_capture": lambda: risk.upside_capture(returns, benchmark_returns),
        "downside_capture": lambda: risk.downside_capture(returns, benchmark_returns),
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


FACTOR_MODELS: dict[str, tuple[str, ...]] = {"ff3": factor_models.FF3, "carhart": factor_models.CARHART}
"""Metric-id prefix -> the factor columns the model regresses on."""

_PERIODS_PER_YEAR = {"daily": performance.TRADING_DAYS, "monthly": 12}

_COEFFICIENT = {"Mkt-RF": "market", "SMB": "smb", "HML": "hml", "MOM": "mom"}


def factor_metric_names(model: str) -> list[str]:
    """``<model>_alpha``, ``<model>_<factor>`` for each factor, ``<model>_r_squared``."""
    return [f"{model}_alpha", *(f"{model}_{_COEFFICIENT[c]}" for c in FACTOR_MODELS[model]), f"{model}_r_squared"]


def factor_metric_set(
    returns: pd.Series,
    factors: pd.DataFrame | MissingData,
    *,
    factor_source: str | None,
    frequency: Literal["daily", "monthly"] = "daily",
) -> dict[str, MetricResult]:
    """FF3 and Carhart regression metrics for one return series, keyed like ``factor_metric_names``.

    ``factors`` is any frame in the ``analytics.factors`` layout, whatever its origin, or
    the ``MissingData`` that explains why there is none (every metric then reports it).
    Coefficients carry ``t_stat`` in details, R-squared carries ``observations`` and
    ``frequency``; every metric names the ``factor_source``. ``returns`` and ``factors``
    are both daily or both monthly (``frequency``), which sets the alpha annualization.
    """
    out: dict[str, MetricResult] = {}
    for model, columns in FACTOR_MODELS.items():

        @cache
        def fit(columns: tuple[str, ...] = columns) -> factor_models.FactorRegression:
            if isinstance(factors, MissingData):
                raise factors
            return factor_models.factor_regression(
                returns, factors, columns, periods_per_year=_PERIODS_PER_YEAR[frequency]
            )

        def coefficient(name: str, value: Callable[[factor_models.FactorRegression], float]) -> Detailed:
            result = fit()
            return Detailed(value(result), {"t_stat": result.t_stats[name], "factor_source": factor_source})

        out[f"{model}_alpha"] = metric(lambda: coefficient("alpha", lambda f: f.alpha), unit="decimal")
        for column in columns:
            out[f"{model}_{_COEFFICIENT[column]}"] = metric(
                lambda column=column: coefficient(column, lambda f: f.loadings[column]), unit="ratio"
            )
        out[f"{model}_r_squared"] = metric(
            lambda: Detailed(
                fit().r_squared,
                {"observations": fit().observations, "frequency": frequency, "factor_source": factor_source},
            ),
            unit="ratio",
        )
    return out


def date_series(compute_values: Callable[[], pd.Series], *, y_unit: str = "decimal") -> SeriesResult:
    """A chart series of ``(ISO date, value)`` points from a date-indexed Series."""
    return series(
        lambda: [(ts.date().isoformat(), float(v)) for ts, v in compute_values().items()],
        x_unit="date",
        y_unit=y_unit,
    )
