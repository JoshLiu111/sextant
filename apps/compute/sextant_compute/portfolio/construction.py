"""My Portfolio construction views (stories 55, 56): rebalancing backtest and efficient frontier.

Both take the demo portfolio's ticker + weight holdings (``PortfolioRequest``) and
work on demo data without sign-in. Prices come through ``api.load_prices``, so
unknown tickers and empty ranges report the same field errors as ``/metrics``.

- ``POST /rebalancing``: the target weights rebalanced by a rule vs bought and held.
  Ids ``<metric>:rebalanced`` / ``<metric>:buy_and_hold``, series
  ``cumulative_return:<same>``, plus ``rebalance_count:rebalanced`` and
  ``turnover:rebalanced``.
- ``POST /frontier``: the long-only mean-variance frontier of the holdings.
  See ``frontier`` below for the ids.
"""

from __future__ import annotations

from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter

from sextant_compute.analytics import rebalancing
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import Detailed, MetricResult, ResultEnvelope, SeriesResult, envelope, metric
from sextant_compute.errors import check
from sextant_compute.portfolio.api import TOOL, PortfolioRequest, load_prices, returns_of
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
