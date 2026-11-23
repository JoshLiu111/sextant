"""My Portfolio construction views (stories 55, 56): rebalancing backtest and efficient frontier.

Both take the demo portfolio's ticker + weight holdings (``PortfolioRequest``) and
work on demo data without sign-in. Prices come through ``api.load_prices``, so
unknown tickers and empty ranges report the same field errors as ``/metrics``.

- ``POST /rebalancing``: the target weights rebalanced by a rule vs bought and held.
  Ids ``<metric>:rebalanced`` / ``<metric>:buy_and_hold``, series
  ``cumulative_return:<same>``, plus ``rebalance_count:rebalanced`` and
  ``turnover:rebalanced``.
- ``POST /frontier``: the long-only mean-variance frontier of the holdings
  (``analytics.optimization``). Portfolios ``min_variance``, ``max_sharpe`` and
  ``current`` (the entered weights) each get ``expected_return:<who>``,
  ``volatility:<who>``, ``sharpe:<who>`` and ``weight:<TICKER>:<who>``. Series
  ``frontier`` (x = volatility, y = expected return) and ``frontier_weight:<TICKER>``
  (x = the frontier point's volatility, y = the weight), sorted by volatility; the
  first frontier point is the minimum-variance portfolio.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Annotated, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import optimization, rebalancing
from sextant_compute.analytics.errors import MissingData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import Detailed, MetricResult, ResultEnvelope, SeriesResult, envelope, metric, series
from sextant_compute.errors import INPUT_ERROR, ApiError, check
from sextant_compute.portfolio.api import TOOL, Holding, PortfolioRequest, load_prices, returns_of
from sextant_compute.risk.metrics import date_series, risk_metric_set

router = APIRouter(tags=["portfolio"])

REBALANCED = "rebalanced"
BUY_AND_HOLD = "buy_and_hold"


class RebalancingRequest(PortfolioRequest):
    rule: Literal["monthly", "quarterly", "yearly", "drift"] = "quarterly"
    """Calendar rules rebalance at each period's last trading day; ``drift`` when a weight strays too far."""
    drift_threshold: Annotated[
        float, check(lambda v: 0 < v <= 0.5, "Enter a drift threshold above 0% and up to 50%.")
    ] = 0.05
    """For ``rule = "drift"``: how far (absolute, decimal) any weight may stray from its target."""


def _count(backtest: rebalancing.Backtest) -> Detailed:
    last = backtest.rebalances[-1].date().isoformat() if backtest.rebalances else None
    return Detailed(len(backtest.rebalances), {"last": last})


@router.post("/rebalancing")
def rebalancing_backtest(req: RebalancingRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    weights = {h.ticker: h.weight for h in req.holdings}
    prices, frames = load_prices(data, ctx, list(weights), req)
    start = frames[req.benchmark].index[0]
    returns = pd.DataFrame({t: returns_of(frames[t]) for t in weights})
    benchmark_returns = returns_of(frames[req.benchmark])
    runs = {
        REBALANCED: rebalancing.run(returns, start, weights, req.rule, threshold=req.drift_threshold),
        BUY_AND_HOLD: rebalancing.run(returns, start, weights, "never"),
    }
    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    for name, run in runs.items():
        wealth = run.wealth
        scored = risk_metric_set(
            wealth.pct_change().iloc[1:],
            wealth,
            benchmark_returns,
            confidence=req.confidence,
            risk_free_rate=req.risk_free_rate,
        )
        metrics.update({f"{metric_name}:{name}": result for metric_name, result in scored.items()})
        charts[f"cumulative_return:{name}"] = date_series(lambda w=wealth: w - 1)
    rebalanced = runs[REBALANCED]
    metrics["rebalance_count:rebalanced"] = metric(lambda: _count(rebalanced), unit="count")
    metrics["turnover:rebalanced"] = metric(lambda: rebalanced.turnover, unit="decimal")
    return envelope(
        tool=TOOL, request=req, metrics=metrics, series=charts, source=prices.source, data_cutoff=prices.last_date
    )


class FrontierRequest(PortfolioRequest):
    """The holdings (their weights are the ``current`` portfolio), range and risk-free rate.

    ``benchmark`` and ``confidence`` are accepted for symmetry with the other portfolio
    views; the benchmark only narrows the dates to those it shares with the holdings.
    """

    @field_validator("holdings")
    @classmethod
    def _at_least_two(cls, holdings: list[Holding]) -> list[Holding]:
        if len(holdings) < 2:
            raise PydanticCustomError(INPUT_ERROR, "Add at least two holdings to build a frontier.")
        return holdings


def _allocation_metrics(
    who: str, allocate: Callable[[], optimization.Allocation], tickers: list[str], rf: float
) -> dict[str, MetricResult]:
    out = {
        f"expected_return:{who}": metric(lambda: allocate().expected_return, unit="decimal"),
        f"volatility:{who}": metric(lambda: allocate().volatility, unit="decimal"),
        f"sharpe:{who}": metric(lambda: allocate().sharpe(rf), unit="ratio"),
    }
    for t in tickers:
        out[f"weight:{t}:{who}"] = metric(lambda t=t: float(allocate().weights[t]), unit="decimal")
    return out


@router.post("/frontier")
def efficient_frontier(req: FrontierRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    current_weights = {h.ticker: h.weight for h in req.holdings}
    tickers = list(current_weights)
    prices, frames = load_prices(data, ctx, tickers, req)
    try:
        inputs = optimization.estimate(pd.DataFrame({t: returns_of(frames[t]) for t in tickers}))
        points = optimization.frontier(inputs, optimization.min_variance(inputs))
    except MissingData as exc:
        message = f"Cannot build a frontier for this range: {exc}."
        raise ApiError(422, "no_such_data", message, {"start": message}) from exc
    rf = req.risk_free_rate
    lowest = points[0]  # sorted by volatility, so no frontier point is less volatile
    current = inputs.allocation(np.array([current_weights[t] for t in tickers]))
    allocations: dict[str, Callable[[], optimization.Allocation]] = {
        "min_variance": lambda: lowest,
        "max_sharpe": cache(lambda: optimization.max_sharpe(inputs, rf)),
        "current": lambda: current,
    }
    metrics: dict[str, MetricResult] = {}
    for who, allocate in allocations.items():
        metrics.update(_allocation_metrics(who, allocate, tickers, rf))
    charts = {
        "frontier": series(
            lambda: [(p.volatility, p.expected_return) for p in points], x_unit="decimal", y_unit="decimal"
        )
    }
    for t in tickers:
        charts[f"frontier_weight:{t}"] = series(
            lambda t=t: [(p.volatility, float(p.weights[t])) for p in points], x_unit="decimal", y_unit="decimal"
        )
    return envelope(
        tool=TOOL, request=req, metrics=metrics, series=charts, source=prices.source, data_cutoff=prices.last_date
    )
