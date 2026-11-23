"""Model checks on Risk & Performance: VaR backtests (Kupiec) and GARCH(1,1) volatility.

Kept apart from ``risk_metric_set`` (which My Portfolio shares) because these are
heavier, per-ticker diagnostics. Metric ids (suffix ``:<ticker>`` added by the router):

- ``garch_volatility``: next-day conditional volatility, annualized; details carry
  the fitted ``omega`` (daily), ``alpha``, ``beta``, ``persistence``,
  ``long_run_volatility`` (annualized), ``log_likelihood`` and ``observations``.
  Series ``garch_volatility`` is the annualized conditional volatility over time.
"""

from __future__ import annotations

import pandas as pd

from sextant_compute.analytics import garch
from sextant_compute.envelope import Detailed, MetricResult, SeriesResult, metric
from sextant_compute.risk.metrics import date_series

GARCH_ID = "garch_volatility"


def _garch_metric(fit: garch.GarchFit) -> Detailed:
    return Detailed(
        garch.annualized_volatility(fit.next_variance),
        {
            "omega": fit.omega,
            "alpha": fit.alpha,
            "beta": fit.beta,
            "persistence": fit.persistence,
            "long_run_volatility": garch.annualized_volatility(fit.long_run_variance),
            "log_likelihood": fit.log_likelihood,
            "observations": fit.observations,
        },
    )


def model_check_set(returns: pd.Series, *, confidence: float) -> tuple[dict[str, MetricResult], dict[str, SeriesResult]]:
    """The backtest and GARCH metrics and series for one return series, keyed without the ticker."""
    fits: dict[str, garch.GarchFit] = {}

    def fitted() -> garch.GarchFit:
        if "fit" not in fits:
            fits["fit"] = garch.fit_garch(returns)
        return fits["fit"]

    metrics = {GARCH_ID: metric(lambda: _garch_metric(fitted()), unit="decimal")}
    series = {GARCH_ID: date_series(lambda: garch.annualized_volatility(fitted().conditional_variance))}
    return metrics, series
