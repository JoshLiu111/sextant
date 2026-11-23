"""The P3 risk & performance metric set, shared by every tool that shows it.

Risk & Performance (per ticker) and My Portfolio (per portfolio) both call
``risk_metric_set`` so their numbers come from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import cache

import pandas as pd

from sextant_compute.analytics import factors as factor_models
from sextant_compute.analytics import performance, risk
from sextant_compute.analytics.periods import PERIODS_PER_YEAR, ReturnPeriod, period_returns
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
    period: ReturnPeriod = "daily",
) -> dict[str, MetricResult]:
    """Every P3 metric for one return series, keyed by metric name (see ``METRIC_NAMES``).

    ``returns`` and ``benchmark_returns`` are simple daily returns; ``wealth`` is
    the matching wealth series (1.0 on the day before the first return).

    ``period`` picks the return period for the period-dependent metrics
    (volatility, every ratio, every VaR/CVaR, beta, alpha, capture), annualized with that period's
    count per year. Annualized return and max drawdown describe the whole wealth
    path, so they always use the daily data.
    """
    per_year = PERIODS_PER_YEAR[period]
    r = period_returns(returns, period)
    b = period_returns(benchmark_returns, period)
    computations: dict[str, Callable[[], float | Detailed]] = {
        "annualized_return": lambda: performance.annualized_return(returns),
        "annualized_volatility": lambda: performance.annualized_volatility(r, per_year),
        "max_drawdown": lambda: _max_drawdown(wealth),
        "sharpe": lambda: performance.sharpe_ratio(r, risk_free_rate, per_year),
        "sortino": lambda: performance.sortino_ratio(r, risk_free_rate, per_year),
        "var": lambda: risk.historical_var(r, confidence, period=period),
        "cvar": lambda: risk.historical_cvar(r, confidence, period=period),
        "parametric_var": lambda: risk.parametric_var(r, confidence, period=period),
        "parametric_cvar": lambda: risk.parametric_cvar(r, confidence, period=period),
        "cornish_fisher_var": lambda: risk.cornish_fisher_var(r, confidence, period=period),
        "cornish_fisher_cvar": lambda: risk.cornish_fisher_cvar(r, confidence, period=period),
        "beta": lambda: risk.beta(r, b),
        "treynor": lambda: risk.treynor_ratio(r, b, risk_free_rate, per_year),
        "information_ratio": lambda: risk.information_ratio(r, b, per_year),
        "alpha": lambda: risk.capm_alpha(r, b, risk_free_rate, per_year),
        "upside_capture": lambda: risk.upside_capture(r, b),
        "downside_capture": lambda: risk.downside_capture(r, b),
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

_COEFFICIENT = {"Mkt-RF": "market", "SMB": "smb", "HML": "hml", "MOM": "mom"}


def factor_metric_names(model: str) -> list[str]:
    """``<model>_alpha``, ``<model>_<factor>`` for each factor, ``<model>_r_squared``."""
    return [f"{model}_alpha", *(f"{model}_{_COEFFICIENT[c]}" for c in FACTOR_MODELS[model]), f"{model}_r_squared"]


def factor_metric_set(
    returns: pd.Series,
    factors: pd.DataFrame | MissingData,
    *,
    factor_source: str | None,
    period: ReturnPeriod = "daily",
) -> dict[str, MetricResult]:
    """FF3 and Carhart regression metrics for one return series, keyed like ``factor_metric_names``.

    ``factors`` is any frame in the ``analytics.factors`` layout, whatever its origin, or
    the ``MissingData`` that explains why there is none (every metric then reports it).
    Coefficients carry ``t_stat`` in details, R-squared carries ``observations``;
    every metric names the ``factor_source``.

    ``returns`` and ``factors`` are daily; ``period`` compounds both into that return
    period first and annualizes alpha with its count per year, like ``risk_metric_set``.
    """
    per_year = PERIODS_PER_YEAR[period]
    r, f = returns, factors
    if not isinstance(factors, MissingData) and period != "daily":
        # Compound over the same days on both sides, so each period pairs like with like.
        days = returns.index.intersection(factors.index)
        r = period_returns(returns.loc[days], period)
        f = factor_models.period_factors(factors.loc[days], period)
    out: dict[str, MetricResult] = {}
    for model, columns in FACTOR_MODELS.items():

        @cache
        def fit(columns: tuple[str, ...] = columns) -> factor_models.FactorRegression:
            if isinstance(f, MissingData):
                raise f
            return factor_models.factor_regression(r, f, columns, periods_per_year=per_year)

        def coefficient(name: str, value: Callable[[factor_models.FactorRegression], float]) -> Detailed:
            result = fit()
            return Detailed(value(result), {"t_stat": result.t_stats[name], "factor_source": factor_source})

        out[f"{model}_alpha"] = metric(lambda: coefficient("alpha", lambda f: f.alpha), unit="decimal")
        for column in columns:
            out[f"{model}_{_COEFFICIENT[column]}"] = metric(
                lambda column=column: coefficient(column, lambda f: f.loadings[column]), unit="ratio"
            )
        out[f"{model}_r_squared"] = metric(
            lambda: Detailed(fit().r_squared, {"observations": fit().observations, "factor_source": factor_source}),
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
