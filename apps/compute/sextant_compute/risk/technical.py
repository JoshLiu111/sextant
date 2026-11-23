"""Risk & Performance (P3): technical indicator overlays and the return correlation matrix.

``POST /risk/indicators`` returns the price of one ticker plus every requested
indicator, computed on history fetched from before ``start`` so each indicator
is defined from the first visible date. ``POST /risk/correlation`` takes the
same body as ``/risk/metrics`` and returns the pairwise correlation of daily
total returns for the tickers and the benchmark.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import performance, technical
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import MetricResult, ResultEnvelope, SeriesResult, envelope, metric, series
from sextant_compute.errors import INPUT_ERROR, ApiError, check
from sextant_compute.risk.api import TOOL, RiskRequest, Ticker, _fields_for

router = APIRouter(tags=["risk"])

MAX_WINDOW = 250

Window = Annotated[int, check(lambda v: 2 <= v <= MAX_WINDOW, f"Enter a window between 2 and {MAX_WINDOW} days.")]


class SmaParams(BaseModel):
    window: Window = 20


class EmaParams(BaseModel):
    window: Window = 50


class BollingerParams(BaseModel):
    window: Window = 20
    width: Annotated[float, check(lambda v: 0 < v <= 5, "Enter a band width between 0 and 5 standard deviations.")] = 2.0


class RsiParams(BaseModel):
    window: Window = 14


class MacdParams(BaseModel):
    fast: Window = 12
    slow: Window = 26
    signal: Window = 9

    @field_validator("slow")
    @classmethod
    def _slow_after_fast(cls, slow: int, info: ValidationInfo) -> int:
        fast = info.data.get("fast")
        if fast is not None and slow <= fast:
            raise PydanticCustomError(INPUT_ERROR, "The slow window must be longer than the fast window.")
        return slow


class IndicatorRequest(BaseModel):
    """One ticker's price chart; each indicator is drawn when its parameters are given (null = off)."""

    ticker: Ticker
    start: date
    end: date
    sma: SmaParams | None = None
    ema: EmaParams | None = None
    bollinger: BollingerParams | None = None
    rsi: RsiParams | None = None
    macd: MacdParams | None = None
    source: Literal["synthetic"] = "synthetic"

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end

    def lookback_days(self) -> int:
        """Trading days of history the requested indicators need before ``start``."""
        return technical.lookback(
            sma_window=self.sma and self.sma.window,
            ema_span=self.ema and self.ema.window,
            bollinger_window=self.bollinger and self.bollinger.window,
            rsi_window=self.rsi and self.rsi.window,
            macd_spans=self.macd and (self.macd.fast, self.macd.slow, self.macd.signal),
        )


def _visible(values: pd.Series, start: date, y_unit: str) -> SeriesResult:
    """Chart points from ``start`` on (the lookback rows are dropped); NaN (not yet defined) is a null y."""
    shown = values.loc[pd.Timestamp(start) :]
    return series(
        lambda: [(ts.date().isoformat(), None if pd.isna(v) else float(v)) for ts, v in shown.items()],
        x_unit="date",
        y_unit=y_unit,
    )


def _indicator_series(req: IndicatorRequest, close: pd.Series) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {"price": close}
    if req.sma:
        out["sma"] = technical.sma(close, req.sma.window)
    if req.ema:
        out["ema"] = technical.ema(close, req.ema.window)
    if req.bollinger:
        upper, middle, lower = technical.bollinger(close, req.bollinger.window, req.bollinger.width)
        out |= {"bollinger_upper": upper, "bollinger_middle": middle, "bollinger_lower": lower}
    if req.rsi:
        out["rsi"] = technical.rsi(close, req.rsi.window)
    if req.macd:
        line, signal, histogram = technical.macd(close, req.macd.fast, req.macd.slow, req.macd.signal)
        out |= {"macd": line, "macd_signal": signal, "macd_histogram": histogram}
    return out


def _y_unit(series_id: str) -> str:
    if series_id == "rsi":
        return "index"
    return "price"


@router.post("/indicators")
def risk_indicators(req: IndicatorRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    fetch_from = req.start - timedelta(days=technical.calendar_days(req.lookback_days()))
    try:
        prices = data.daily_prices(ctx, [req.ticker], fetch_from, req.end, source=req.source)
    except NoSuchData as exc:
        field = "ticker" if req.ticker in exc.missing else "start"
        raise ApiError(422, "no_such_data", exc.message, {field: exc.missing.get(req.ticker, exc.message)}) from exc
    close = prices.frames[req.ticker]["close"]
    if close.loc[pd.Timestamp(req.start) :].empty:
        message = f"No data for {req.ticker} between {req.start} and {req.end}."
        raise ApiError(422, "no_such_data", message, {"start": message})

    charts: dict[str, SeriesResult] = {
        series_id: _visible(values, req.start, _y_unit(series_id))
        for series_id, values in _indicator_series(req, close).items()
    }
    return envelope(
        tool=TOOL,
        request=req,
        metrics={},
        series=charts,
        source=prices.source,
        data_cutoff=prices.last_date,
    )


@router.post("/correlation")
def risk_correlation(req: RiskRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    symbols = list(dict.fromkeys([*req.tickers, req.benchmark]))
    try:
        prices = data.daily_prices(ctx, symbols, req.start, req.end, source=req.source)
    except NoSuchData as exc:
        raise ApiError(422, "no_such_data", exc.message, _fields_for(exc, req)) from exc

    returns = {
        t: performance.total_returns(prices.frames[t]["close"], prices.frames[t]["dividend"]) for t in symbols
    }
    metrics: dict[str, MetricResult] = {
        f"correlation:{a}:{b}": metric(lambda a=a, b=b: technical.correlation(returns, a, b), unit="ratio")
        for a in symbols
        for b in symbols
    }
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        source=prices.source,
        data_cutoff=prices.last_date,
    )

