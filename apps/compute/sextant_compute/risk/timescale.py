"""Risk & Performance time-scale views: rolling curves and the return distribution.

Kept apart from ``risk_metric_set`` so the shared P3 metric set stays small;
``timescale_results`` adds these per-ticker series and metrics to the envelope.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from sextant_compute.analytics import rolling
from sextant_compute.envelope import Detail, MetricResult, SeriesData, SeriesResult, series

ROLLING_SERIES = ("rolling_volatility", "rolling_sharpe", "rolling_beta")


def _rolling_series(compute: Callable[[], pd.Series], *, window: int, y_unit: str) -> SeriesResult:
    def points() -> SeriesData:
        values = compute()
        details: dict[str, Detail] = {"window": window}
        return SeriesData([(ts.date().isoformat(), float(v)) for ts, v in values.items()], details)

    return series(points, x_unit="date", y_unit=y_unit)


def timescale_results(
    ticker: str,
    returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    window: int,
    risk_free_rate: float,
) -> tuple[dict[str, MetricResult], dict[str, SeriesResult]]:
    """Metrics and series ids ``<name>:<ticker>`` for one ticker's daily returns."""
    charts = {
        f"rolling_volatility:{ticker}": _rolling_series(
            lambda: rolling.rolling_volatility(returns, window), window=window, y_unit="decimal"
        ),
        f"rolling_sharpe:{ticker}": _rolling_series(
            lambda: rolling.rolling_sharpe(returns, window, risk_free_rate), window=window, y_unit="ratio"
        ),
        f"rolling_beta:{ticker}": _rolling_series(
            lambda: rolling.rolling_beta(returns, benchmark_returns, window), window=window, y_unit="ratio"
        ),
    }
    return {}, charts
