"""Model checks on Risk & Performance: VaR backtests (Kupiec) and GARCH(1,1) volatility.

Kept apart from ``risk_metric_set`` (which My Portfolio shares) because these are
heavier, per-ticker diagnostics. Metric ids (suffix ``:<ticker>`` added by the router):

- ``backtest_var``, ``backtest_parametric_var``, ``backtest_cornish_fisher_var``:
  a rolling backtest of the historical, parametric and Cornish-Fisher VaR at the
  request's confidence. Value: breaches (unit ``count``); details: ``window``,
  ``observations``, ``expected_breaches``, ``breach_rate``, ``kupiec_statistic``,
  ``p_value``, ``significance`` and ``result`` (``"accept"`` | ``"reject"``).
- ``garch_volatility``: next-day conditional volatility, annualized; details carry
  the fitted ``omega`` (daily), ``alpha``, ``beta``, ``persistence``,
  ``long_run_volatility`` (annualized), ``log_likelihood`` and ``observations``.
  Series ``garch_volatility`` is the annualized conditional volatility over time.
"""

from __future__ import annotations

import pandas as pd

from sextant_compute.analytics import backtest, garch
from sextant_compute.envelope import Detailed, MetricResult, MetricStatus, SeriesResult, metric
from sextant_compute.risk.metrics import CHART_POINTS, date_series, missing_series

GARCH_ID = "garch_volatility"
BACKTEST_IDS: dict[str, backtest.VarMethod] = {
    "backtest_var": "historical",
    "backtest_parametric_var": "parametric",
    "backtest_cornish_fisher_var": "cornish_fisher",
}


def _backtest_metric(returns: pd.Series, method: backtest.VarMethod, confidence: float) -> Detailed:
    bt = backtest.backtest_var(returns, method, confidence)
    return Detailed(
        bt.breaches,
        {
            "window": bt.window,
            "observations": bt.observations,
            "expected_breaches": bt.expected_breaches,
            "breach_rate": bt.breach_rate,
            "kupiec_statistic": bt.kupiec_statistic,
            "p_value": bt.p_value,
            "significance": bt.significance,
            "result": "reject" if bt.rejected else "accept",
        },
    )


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


def model_check_set(
    returns: pd.Series, *, confidence: float
) -> tuple[dict[str, MetricResult], dict[str, SeriesResult]]:
    """The backtest and GARCH metrics and series for one return series, keyed without the ticker."""
    fits: dict[str, garch.GarchFit] = {}

    def fitted() -> garch.GarchFit:
        if "fit" not in fits:
            fits["fit"] = garch.fit_garch(returns)
        return fits["fit"]

    metrics = {
        metric_id: metric(lambda method=method: _backtest_metric(returns, method, confidence), unit="count")
        for metric_id, method in BACKTEST_IDS.items()
    }
    metrics[GARCH_ID] = metric(lambda: _garch_metric(fitted()), unit="decimal")
    series = {
        GARCH_ID: date_series(
            lambda: garch.annualized_volatility(fitted().conditional_variance), max_points=CHART_POINTS
        )
    }
    return metrics, series


def missing_model_check_set(reason: str) -> tuple[dict[str, MetricResult], dict[str, SeriesResult]]:
    """The ids ``model_check_set`` returns, all ``missing_data`` with ``reason``
    (e.g. for a ticker the user's provider has no prices for)."""
    missing = MetricStatus.MISSING_DATA
    metrics = {
        metric_id: MetricResult(value=None, status=missing, reason=reason, unit="count") for metric_id in BACKTEST_IDS
    }
    metrics[GARCH_ID] = MetricResult(value=None, status=missing, reason=reason, unit="decimal")
    return metrics, {GARCH_ID: missing_series(reason)}
