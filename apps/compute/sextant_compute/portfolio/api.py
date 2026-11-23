"""My Portfolio (P4) endpoints.

A portfolio is a list of holdings (ticker + weight). Its daily return series is
built with ``analytics.portfolio`` and then scored with the same metric set as
Risk & Performance (``risk.metrics.risk_metric_set``).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import performance, portfolio
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import MetricResult, ResultEnvelope, SeriesResult, envelope
from sextant_compute.errors import INPUT_ERROR, ApiError, check
from sextant_compute.risk.api import Ticker
from sextant_compute.risk.metrics import date_series, risk_metric_set

router = APIRouter(tags=["portfolio"])

TOOL = "portfolio"
MAX_HOLDINGS = 20
WEIGHT_TOLERANCE = 1e-4
"""How far the weights may sum from 100% (0.01 percentage points), to absorb rounding like 3 x 33.33%."""

PORTFOLIO = "portfolio"
BENCHMARK = "benchmark"
"""Metric ids are ``<metric>:portfolio`` and ``<metric>:benchmark``; series ids ``cumulative_return:<same>``."""


class Holding(BaseModel):
    ticker: Ticker
    weight: Annotated[float, check(lambda v: 0 < v <= 1, "Enter a weight above 0% and up to 100%.")]
    """Share of the portfolio as a decimal (0.6 = 60%)."""


def _percent(x: float) -> str:
    return f"{x * 100:.2f}".rstrip("0").rstrip(".") + "%"


class PortfolioRequest(BaseModel):
    holdings: Annotated[
        list[Holding],
        check(lambda v: len(v) >= 1, "Add at least one holding."),
        check(lambda v: len(v) <= MAX_HOLDINGS, f"Enter at most {MAX_HOLDINGS} holdings."),
        check(lambda v: len({h.ticker for h in v}) == len(v), "Each ticker can only be listed once."),
    ]
    benchmark: Ticker = "DEMO-MKT"
    start: date
    end: date
    confidence: Annotated[
        float, check(lambda v: 0.5 <= v <= 0.999, "Enter a confidence level between 50% and 99.9%.")
    ] = 0.95
    risk_free_rate: Annotated[
        float, check(lambda v: -0.05 <= v <= 0.2, "Enter a risk-free rate between -5% and 20%.")
    ] = 0.0
    source: Literal["synthetic"] = "synthetic"

    @field_validator("holdings")
    @classmethod
    def _weights_sum_to_one(cls, holdings: list[Holding]) -> list[Holding]:
        total = sum(h.weight for h in holdings)
        if abs(total - 1) > WEIGHT_TOLERANCE:
            raise PydanticCustomError(
                INPUT_ERROR, "Weights must add up to 100% (they add up to {total}).", {"total": _percent(total)}
            )
        return holdings

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end


def _fields_for(exc: NoSuchData, req: PortfolioRequest) -> dict[str, str]:
    """Attach each missing ticker's message to the holding row (or benchmark) that named it."""
    fields = {f"holdings.{i}.ticker": exc.missing[h.ticker] for i, h in enumerate(req.holdings) if h.ticker in exc.missing}
    if req.benchmark in exc.missing:
        fields["benchmark"] = exc.missing[req.benchmark]
    if not fields:  # nothing named a ticker, so the date range is what has no data
        fields["start"] = exc.message
    return fields


@router.post("/metrics")
def portfolio_metrics(req: PortfolioRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    weights = {h.ticker: h.weight for h in req.holdings}
    symbols = list(dict.fromkeys([*weights, req.benchmark]))
    try:
        prices = data.daily_prices(ctx, symbols, req.start, req.end, source=req.source)
    except NoSuchData as exc:
        raise ApiError(422, "no_such_data", exc.message, _fields_for(exc, req)) from exc

    # Score portfolio and benchmark on the same trading days: those every symbol has a price for.
    common = prices.frames[symbols[0]].index
    for symbol in symbols[1:]:
        common = common.intersection(prices.frames[symbol].index)
    if len(common) < 2:
        message = "The holdings and the benchmark share fewer than 2 trading days in this range."
        raise ApiError(422, "no_such_data", message, {"start": message})

    def returns_of(ticker: str) -> pd.Series:
        frame = prices.frames[ticker].loc[common]
        return performance.total_returns(frame["close"], frame["dividend"])

    benchmark_returns = returns_of(req.benchmark)
    returns = {
        PORTFOLIO: portfolio.weighted_returns({t: returns_of(t) for t in weights}, weights),
        BENCHMARK: benchmark_returns,
    }

    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    for name, r in returns.items():
        wealth = portfolio.wealth_index(r, common[0])
        scored = risk_metric_set(
            r, wealth, benchmark_returns, confidence=req.confidence, risk_free_rate=req.risk_free_rate
        )
        metrics.update({f"{metric_name}:{name}": result for metric_name, result in scored.items()})
        charts[f"cumulative_return:{name}"] = date_series(lambda: wealth - 1)
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=prices.source,
        data_cutoff=prices.last_date,
    )
