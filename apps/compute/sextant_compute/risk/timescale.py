"""Risk & Performance time-scale views: underwater chart, rolling curves and the
return distribution.

Kept apart from ``risk_metric_set`` so the shared P3 metric set stays small;
``timescale_results`` adds these per-ticker series and metrics to the envelope.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from sextant_compute.analytics import distribution, risk, rolling
from sextant_compute.analytics.periods import PERIODS_PER_YEAR, ReturnPeriod, period_returns
from sextant_compute.risk.metrics import CHART_DECIMALS, CHART_POINTS
from sextant_compute.envelope import (
    Band,
    Detail,
    MetricResult,
    MetricStatus,
    SeriesData,
    SeriesResult,
    metric,
    series,
)

def _rolling_series(compute: Callable[[], pd.Series], *, window: int, y_unit: str) -> SeriesResult:
    def points() -> SeriesData:
        values = compute()
        details: dict[str, Detail] = {"window": window}
        # Rounded and thinned: a chart needs no more, and it keeps the response small.
        return SeriesData([(ts.date().isoformat(), round(float(v), CHART_DECIMALS)) for ts, v in values.items()], details)

    return series(points, x_unit="date", y_unit=y_unit, max_points=CHART_POINTS)


def _iso(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).date().isoformat()


def underwater_series(wealth: pd.Series) -> SeriesResult:
    """The drawdown curve, with the max drawdown shaded from its peak to its
    recovery (or to the end of the range when it has not recovered). Thinned for
    drawing; the trough survives thinning (``envelope.thin_points``)."""

    def points() -> SeriesData:
        underwater = risk.drawdown(wealth)
        mdd = risk.max_drawdown(wealth)
        end = mdd.recovery.isoformat() if mdd.recovery else _iso(underwater.index[-1])
        band = Band(start=mdd.peak.isoformat(), end=end, label="max_drawdown")
        values = [(_iso(ts), round(float(v), CHART_DECIMALS)) for ts, v in underwater.items()]
        return SeriesData(values, bands=[band] if mdd.depth > 0 else [])

    return series(points, x_unit="date", y_unit="decimal", max_points=CHART_POINTS)


def _histogram(returns: pd.Series, per_year: int) -> SeriesData:
    hist = distribution.histogram(returns, per_year)
    details: dict[str, Detail] = {"bin_width": hist.bin_width, "observations": hist.observations}
    return SeriesData(list(zip(hist.centers, [float(c) for c in hist.counts], strict=True)), details)


def timescale_results(
    ticker: str,
    returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    window: int,
    risk_free_rate: float,
    period: ReturnPeriod,
) -> tuple[dict[str, MetricResult], dict[str, SeriesResult]]:
    """Metrics and series ids ``<name>:<ticker>`` for one ticker's daily returns.

    Rolling curves use daily returns (``window`` in trading days); the
    distribution uses the chosen return period.
    """
    per_year = PERIODS_PER_YEAR[period]
    by_period = period_returns(returns, period)
    shape = {
        f"skewness:{ticker}": metric(lambda: distribution.skewness(by_period, per_year), unit="ratio"),
        f"excess_kurtosis:{ticker}": metric(lambda: distribution.excess_kurtosis(by_period, per_year), unit="ratio"),
    }
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
        f"return_distribution:{ticker}": series(
            lambda: _histogram(by_period, per_year), x_unit="decimal", y_unit="count"
        ),
    }
    return shape, charts


def missing_timescale_results(ticker: str, reason: str) -> tuple[dict[str, MetricResult], dict[str, SeriesResult]]:
    """The ids ``timescale_results`` returns, all ``missing_data`` with ``reason``
    (e.g. for a ticker the user's provider has no prices for)."""
    missing = MetricStatus.MISSING_DATA
    shape = {
        f"{name}:{ticker}": MetricResult(value=None, status=missing, reason=reason, unit="ratio")
        for name in ("skewness", "excess_kurtosis")
    }
    units = {"rolling_volatility": ("date", "decimal"), "rolling_sharpe": ("date", "ratio")}
    units |= {"rolling_beta": ("date", "ratio"), "return_distribution": ("decimal", "count")}
    charts = {
        f"{name}:{ticker}": SeriesResult(status=missing, reason=reason, x_unit=x_unit, y_unit=y_unit)
        for name, (x_unit, y_unit) in units.items()
    }
    return shape, charts
