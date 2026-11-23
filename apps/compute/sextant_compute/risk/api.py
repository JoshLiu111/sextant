"""Risk & Performance (P3) endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import performance, risk
from sextant_compute.analytics.periods import ReturnPeriod
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.data.sources import DEMO_SOURCE, PriceSource
from sextant_compute.envelope import MetricResult, MissingData, ResultEnvelope, SeriesResult, envelope
from sextant_compute.errors import INPUT_ERROR, ApiError, check
from sextant_compute.risk.factor_api import FACTOR_SOURCE, Db, load_user_factors
from sextant_compute.risk.factor_files import Frequency
from sextant_compute.risk.metrics import (
    factor_metric_set,
    missing_metric_set,
    missing_series,
    risk_metric_set,
)
from sextant_compute.risk.timescale import missing_timescale_results, timescale_results, underwater_series
from sextant_compute.risk.model_checks import missing_model_check_set, model_check_set

router = APIRouter(tags=["risk"])

TOOL = "risk"
MAX_TICKERS = 10
MIN_ROLLING_WINDOW = 20
MAX_ROLLING_WINDOW = 756


def _normalize_ticker(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


Ticker = Annotated[str, BeforeValidator(_normalize_ticker), check(lambda v: v != "", "Enter a ticker.")]


class RiskRequest(BaseModel):
    tickers: Annotated[
        list[Ticker],
        check(lambda v: len(v) >= 1, "Enter at least one ticker."),
        check(lambda v: len(v) <= MAX_TICKERS, f"Enter at most {MAX_TICKERS} tickers."),
        check(lambda v: len(set(v)) == len(v), "Each ticker can only be listed once."),
    ]
    benchmark: Ticker = "DEMO-MKT"
    start: date
    end: date
    confidence: Annotated[
        float, check(lambda v: 0.5 <= v <= 0.999, "Enter a confidence level between 50% and 99.9%.")
    ] = 0.95
    """VaR/CVaR confidence level as a decimal (0.95 = 95%)."""
    risk_free_rate: Annotated[
        float, check(lambda v: -0.05 <= v <= 0.2, "Enter a risk-free rate between -5% and 20%.")
    ] = 0.0
    """Effective annual risk-free rate as a decimal, used by Sharpe and Sortino."""
    period: ReturnPeriod = "daily"
    """Return period for the period-dependent statistics (volatility, Sharpe, VaR, factor regressions, ...)."""
    rolling_window: Annotated[
        int,
        check(
            lambda v: MIN_ROLLING_WINDOW <= v <= MAX_ROLLING_WINDOW,
            f"Enter a window between {MIN_ROLLING_WINDOW} and {MAX_ROLLING_WINDOW} trading days.",
        ),
    ] = 63
    """Rolling-curve window in trading days (daily returns, whatever the period)."""
    source: PriceSource = DEMO_SOURCE
    """Demo data (``"synthetic"``) or the user's own provider (My data, e.g. ``"tiingo"``)."""

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end


def _fields_for(exc: NoSuchData, req: RiskRequest) -> dict[str, str]:
    """Attach each missing ticker's message to the input that named it."""
    fields: dict[str, str] = {}
    in_tickers = [msg for t, msg in exc.missing.items() if t in req.tickers]
    if in_tickers:
        fields["tickers"] = " ".join(in_tickers)
    if req.benchmark in exc.missing:
        fields["benchmark"] = exc.missing[req.benchmark]
    if not fields:  # nothing named a ticker, so the date range is what has no data
        fields["start"] = exc.message
    return fields


@router.post("/metrics")
def risk_metrics(req: RiskRequest, data: Data, ctx: Ctx, db: Db) -> ResultEnvelope:
    """Demo data rejects an unknown ticker inline (the demo set is small and
    listed). On My data an unknown real ticker only marks its own metrics
    ``missing_data``; the benchmark must exist either way.

    Factor regressions use the synthetic demo factors on Demo data, and on My data
    the factor file the user uploaded (``risk.factor_api``), at its frequency."""
    symbols = list(dict.fromkeys([*req.tickers, req.benchmark]))
    try:
        prices = data.daily_prices(
            ctx, symbols, req.start, req.end, source=req.source, partial=req.source != DEMO_SOURCE
        )
    except NoSuchData as exc:
        raise ApiError(422, "no_such_data", exc.message, _fields_for(exc, req)) from exc
    if req.benchmark in prices.missing:
        message = prices.missing[req.benchmark]
        raise ApiError(422, "no_such_data", message, {"benchmark": message})

    factors: pd.DataFrame | MissingData
    frequency: Frequency = "daily"
    if req.source == DEMO_SOURCE:
        try:
            history = data.daily_factors(ctx, req.start, req.end, source=req.source)
            factors, factor_source = history.frame, history.source.id
        except NoSuchData as exc:
            factors, factor_source = MissingData(exc.message), None
    else:
        # ADR 0003: real factors only come from the user's own upload, read per request
        # for this user and never cached.
        factors, frequency = load_user_factors(db, ctx.user_id, req.start, req.end)
        factor_source = FACTOR_SOURCE

    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    for ticker, reason in prices.missing.items():
        missing = missing_metric_set(reason)
        missing.update(factor_metric_set(pd.Series(dtype=float), MissingData(reason), factor_source=None))
        metrics.update({f"{name}:{ticker}": result for name, result in missing.items()})
        charts[f"drawdown:{ticker}"] = missing_series(reason)
        extra_metrics, extra_charts = missing_timescale_results(ticker, reason)
        metrics.update(extra_metrics)
        charts.update(extra_charts)
        check_metrics, check_series = missing_model_check_set(reason)
        metrics.update({f"{name}:{ticker}": result for name, result in check_metrics.items()})
        charts.update({f"{name}:{ticker}": result for name, result in check_series.items()})

    def returns_of(ticker: str) -> pd.Series:
        frame = prices.frames[ticker]
        return performance.total_returns(frame["close"], frame["dividend"])

    def factor_returns_of(ticker: str) -> pd.Series:
        """The ticker's returns at the factor data's frequency."""
        if frequency == "daily":
            return returns_of(ticker)
        frame = prices.frames[ticker]
        return performance.monthly_returns(performance.total_return_index(frame["close"], frame["dividend"]), req.end)

    benchmark_returns = returns_of(req.benchmark)
    for ticker in prices.frames:
        frame = prices.frames[ticker]
        wealth = performance.total_return_index(frame["close"], frame["dividend"])
        ticker_metrics = risk_metric_set(
            returns_of(ticker),
            wealth,
            benchmark_returns,
            confidence=req.confidence,
            risk_free_rate=req.risk_free_rate,
            period=req.period,
        )
        ticker_metrics.update(
            factor_metric_set(
                factor_returns_of(ticker),
                factors,
                factor_source=factor_source,
                period=req.period,
                frequency=frequency,
            )
        )
        metrics.update({f"{name}:{ticker}": result for name, result in ticker_metrics.items()})
        charts[f"drawdown:{ticker}"] = underwater_series(wealth)
        extra_metrics, extra_charts = timescale_results(
            ticker,
            returns_of(ticker),
            benchmark_returns,
            window=req.rolling_window,
            risk_free_rate=req.risk_free_rate,
            period=req.period,
        )
        metrics.update(extra_metrics)
        charts.update(extra_charts)
        check_metrics, check_series = model_check_set(returns_of(ticker), confidence=req.confidence)
        metrics.update({f"{name}:{ticker}": result for name, result in check_metrics.items()})
        charts.update({f"{name}:{ticker}": result for name, result in check_series.items()})
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=prices.source,
        data_cutoff=prices.last_date,
    )
