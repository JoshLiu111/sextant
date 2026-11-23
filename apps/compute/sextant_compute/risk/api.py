"""Risk & Performance (P3) endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import performance, risk
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import Detailed, MetricResult, ResultEnvelope, SeriesResult, envelope, metric, series
from sextant_compute.errors import INPUT_ERROR, ApiError, check

router = APIRouter(tags=["risk"])

TOOL = "risk"
MAX_TICKERS = 10


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
    source: Literal["synthetic"] = "synthetic"
    """Which DataService adapter backs the result. Add ids here as adapters arrive."""

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


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _max_drawdown(wealth: pd.Series) -> Detailed:
    mdd = risk.max_drawdown(wealth)
    return Detailed(mdd.depth, {"peak": _iso(mdd.peak), "trough": _iso(mdd.trough), "recovery": _iso(mdd.recovery)})


@router.post("/metrics")
def risk_metrics(req: RiskRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    symbols = list(dict.fromkeys([*req.tickers, req.benchmark]))
    try:
        prices = data.daily_prices(ctx, symbols, req.start, req.end, source=req.source)
    except NoSuchData as exc:
        raise ApiError(422, "no_such_data", exc.message, _fields_for(exc, req)) from exc

    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    for ticker in symbols:
        frame = prices.frames[ticker]
        returns = performance.total_returns(frame["close"], frame["dividend"])
        wealth = performance.total_return_index(frame["close"], frame["dividend"])
        metrics[f"annualized_return:{ticker}"] = metric(lambda: performance.annualized_return(returns), unit="decimal")
        metrics[f"annualized_volatility:{ticker}"] = metric(
            lambda: performance.annualized_volatility(returns), unit="decimal"
        )
        metrics[f"max_drawdown:{ticker}"] = metric(lambda: _max_drawdown(wealth), unit="decimal")
        charts[f"drawdown:{ticker}"] = series(
            lambda: [(ts.date().isoformat(), float(v)) for ts, v in risk.drawdown(wealth).items()],
            x_unit="date",
            y_unit="decimal",
        )
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=prices.source,
        data_cutoff=prices.last_date,
    )
