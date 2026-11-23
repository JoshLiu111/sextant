"""My Portfolio (P4) endpoints.

A portfolio is a list of holdings. The demo portfolio (this module) holds
ticker + weight and is rebalanced daily; a saved portfolio (``saved.py``) holds
quantities and is bought and held. Either way its daily return series is built
with ``analytics.portfolio`` and then scored with the same metric set as Risk &
Performance (``risk.metrics.risk_metric_set``), via ``score``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import performance, portfolio
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data, DataService, PriceHistory
from sextant_compute.data.sources import DEMO_SOURCE, PriceSource, is_demo_ticker
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


class AnalysisSettings(BaseModel):
    """How a portfolio is scored: benchmark, date range, VaR confidence, risk-free rate, data source."""

    benchmark: Ticker = "DEMO-MKT"
    start: date
    end: date
    confidence: Annotated[
        float, check(lambda v: 0.5 <= v <= 0.999, "Enter a confidence level between 50% and 99.9%.")
    ] = 0.95
    risk_free_rate: Annotated[
        float, check(lambda v: -0.05 <= v <= 0.2, "Enter a risk-free rate between -5% and 20%.")
    ] = 0.0
    source: PriceSource = DEMO_SOURCE
    """Demo data (``"synthetic"``) or the user's own provider (My data, e.g. ``"tiingo"``)."""

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end


class PortfolioRequest(AnalysisSettings):
    holdings: Annotated[
        list[Holding],
        check(lambda v: len(v) >= 1, "Add at least one holding."),
        check(lambda v: len(v) <= MAX_HOLDINGS, f"Enter at most {MAX_HOLDINGS} holdings."),
        check(lambda v: len({h.ticker for h in v}) == len(v), "Each ticker can only be listed once."),
    ]

    @field_validator("holdings")
    @classmethod
    def _weights_sum_to_one(cls, holdings: list[Holding]) -> list[Holding]:
        total = sum(h.weight for h in holdings)
        if abs(total - 1) > WEIGHT_TOLERANCE:
            raise PydanticCustomError(
                INPUT_ERROR, "Weights must add up to 100% (they add up to {total}).", {"total": _percent(total)}
            )
        return holdings


def _fields_for(exc: NoSuchData, tickers: Sequence[str], benchmark: str) -> dict[str, str]:
    """Attach each missing ticker's message to the holding row (or benchmark) that named it."""
    fields = {f"holdings.{i}.ticker": exc.missing[t] for i, t in enumerate(tickers) if t in exc.missing}
    if benchmark in exc.missing:
        fields["benchmark"] = exc.missing[benchmark]
    if not fields:  # nothing named a ticker, so the date range is what has no data
        fields["start"] = exc.message
    return fields


def fetch_prices(
    data: DataService,
    ctx: RequestContext,
    symbols: Sequence[str],
    start: date,
    end: date,
    source: str,
    *,
    allow_missing: bool = False,
) -> PriceHistory:
    """Prices for every symbol, or ``NoSuchData`` naming each symbol that has none.

    On My data each ticker is fetched and cached on its own (``partial``), sharing
    entries with Risk & Performance, and demo tickers are never sent to the provider.
    With ``allow_missing`` (saved portfolios on My data, like Risk & Performance) the
    symbols without prices come back in ``PriceHistory.missing`` instead; a portfolio
    built from weights can't be scored with a holding missing, so it fails instead.
    Demo data always fails on an unknown ticker (the demo set is small and listed).
    """
    if source == DEMO_SOURCE:
        return data.daily_prices(ctx, symbols, start, end, source=source)
    provider = data.source_info(source).name
    demo = {
        s: f"{s} is a demo ticker, so it only has Demo data. My data uses real tickers from {provider}, like AAPL."
        for s in symbols
        if is_demo_ticker(s)
    }
    if demo and not allow_missing:
        raise NoSuchData(source, " ".join(demo.values()), demo)
    real = [s for s in symbols if s not in demo]
    prices = data.daily_prices(ctx, real, start, end, source=source, partial=True) if real else None
    missing = {**demo, **(prices.missing if prices else {})}
    if missing and not allow_missing:
        raise NoSuchData(source, " ".join(missing.values()), missing)
    return PriceHistory(data.source_info(source), prices.frames if prices else {}, missing)


def load_prices(
    data: DataService,
    ctx: RequestContext,
    tickers: Sequence[str],
    settings: AnalysisSettings,
    *,
    allow_missing: bool = False,
) -> tuple[PriceHistory, dict[str, pd.DataFrame]]:
    """Prices for the holdings and the benchmark, restricted to the trading days every symbol has.

    Scoring portfolio and benchmark on the same days keeps them comparable.
    Unknown tickers come back as field errors on their holding row, or with
    ``allow_missing`` in ``PriceHistory.missing`` (and not in the frames). The
    benchmark must have prices either way.
    """
    symbols = list(dict.fromkeys([*tickers, settings.benchmark]))
    try:
        prices = fetch_prices(
            data, ctx, symbols, settings.start, settings.end, settings.source, allow_missing=allow_missing
        )
    except NoSuchData as exc:
        raise ApiError(422, "no_such_data", exc.message, _fields_for(exc, tickers, settings.benchmark)) from exc
    if settings.benchmark in prices.missing:
        message = prices.missing[settings.benchmark]
        raise ApiError(422, "no_such_data", message, {"benchmark": message})
    present = [s for s in symbols if s not in prices.missing]
    common = prices.frames[present[0]].index
    for symbol in present[1:]:
        common = common.intersection(prices.frames[symbol].index)
    if len(common) < 2:
        message = "The holdings and the benchmark share fewer than 2 trading days in this range."
        raise ApiError(422, "no_such_data", message, {"start": message})
    return prices, {s: prices.frames[s].loc[common] for s in present}


def returns_of(frame: pd.DataFrame) -> pd.Series:
    return performance.total_returns(frame["close"], frame["dividend"])


def score(
    req: BaseModel,
    settings: AnalysisSettings,
    prices: PriceHistory,
    frames: Mapping[str, pd.DataFrame],
    portfolio_wealth: pd.Series,
    extra_metrics: Mapping[str, MetricResult] | None = None,
) -> ResultEnvelope:
    """The portfolio envelope: P3 metrics and cumulative return for the portfolio and the benchmark.

    ``portfolio_wealth`` is the portfolio's wealth on the common dates (1.0 on the first).
    """
    benchmark_returns = returns_of(frames[settings.benchmark])
    wealths = {
        PORTFOLIO: portfolio_wealth,
        BENCHMARK: portfolio.wealth_index(benchmark_returns, portfolio_wealth.index[0]),
    }
    metrics: dict[str, MetricResult] = dict(extra_metrics or {})
    charts: dict[str, SeriesResult] = {}
    for name, wealth in wealths.items():
        r = wealth.pct_change().iloc[1:]
        scored = risk_metric_set(
            r, wealth, benchmark_returns, confidence=settings.confidence, risk_free_rate=settings.risk_free_rate
        )
        metrics.update({f"{metric_name}:{name}": result for metric_name, result in scored.items()})
        charts[f"cumulative_return:{name}"] = date_series(lambda w=wealth: w - 1)
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=prices.source,
        data_cutoff=prices.last_date,
    )


@router.post("/metrics")
def portfolio_metrics(req: PortfolioRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    weights = {h.ticker: h.weight for h in req.holdings}
    prices, frames = load_prices(data, ctx, list(weights), req)
    returns = portfolio.weighted_returns({t: returns_of(frames[t]) for t in weights}, weights)
    wealth = portfolio.wealth_index(returns, frames[req.benchmark].index[0])
    return score(req, req, prices, frames, wealth)
