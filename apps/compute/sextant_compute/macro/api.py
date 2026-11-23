"""Macro Dashboard (P5) endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import rates
from sextant_compute.data.adapters import EconomicSeries, YieldCurves
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import (
    Band,
    Detailed,
    MetricResult,
    MissingData,
    ResultEnvelope,
    SeriesData,
    SeriesResult,
    envelope,
    metric,
    series,
)
from sextant_compute.errors import INPUT_ERROR, check

router = APIRouter(tags=["macro"])

TOOL = "macro"
HISTORY_START = date(2015, 1, 1)


@dataclass(frozen=True)
class Indicator:
    key: str
    series_id: str
    units: str = "lin"
    """FRED transformation (see ``fred.adapter.UNITS_LABELS``)."""


# The four US headline indicators. Every value is in percent.
HEADLINE = [
    Indicator("gdp_growth", "A191RL1Q225SBEA"),
    Indicator("cpi_inflation", "CPIAUCSL", units="pc1"),
    Indicator("unemployment_rate", "UNRATE"),
    Indicator("fed_funds_rate", "FEDFUNDS"),
]


class IndicatorsRequest(BaseModel):
    start: date = HISTORY_START
    source: Literal["fred"] = "fred"


def _latest(found: EconomicSeries | NoSuchData) -> Detailed:
    if isinstance(found, NoSuchData):
        raise MissingData(found.message)
    latest = found.latest
    if latest is None:
        raise MissingData(f"{found.meta.title} has no observations in the range.")
    when, value = latest
    m = found.meta
    return Detailed(
        value,
        {
            "date": when.isoformat(),
            "series_id": m.id,
            "title": m.title,
            "source": m.source,
            "units": m.units,
            "frequency": m.frequency,
            "seasonal_adjustment": m.seasonal_adjustment,
            "last_updated": m.last_updated,
        },
    )


def _history(found: EconomicSeries | NoSuchData) -> list[tuple[float | str, float | None]]:
    if isinstance(found, NoSuchData):
        raise MissingData(found.message)
    return [(when.isoformat(), value) for when, value in found.observations]


@router.post("/indicators")
def headline_indicators(req: IndicatorsRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    """Latest value + history + metadata for each headline indicator.
    A FRED outage (``SourceUnavailable``) fails the whole request with 503."""
    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    cutoffs: list[date] = []
    for ind in HEADLINE:
        found: EconomicSeries | NoSuchData
        try:
            found = data.economic_series(ctx, ind.series_id, start=req.start, units=ind.units, source=req.source)
        except NoSuchData as exc:
            found = exc
        if isinstance(found, EconomicSeries) and found.latest:
            cutoffs.append(found.latest[0])
        metrics[f"latest:{ind.key}"] = metric(lambda: _latest(found), unit="percent")
        charts[f"history:{ind.key}"] = series(lambda: _history(found), x_unit="date", y_unit="percent")
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=data.source_info(req.source),
        data_cutoff=max(cutoffs) if cutoffs else None,
    )


# --- Rates: Treasury yield curve and the 10Y-2Y term spread -----------------

RATES_START = date(2018, 1, 1)
TREASURY_FIRST = date(1990, 1, 2)  # the par yield curve starts here

# Curves overlaid on the chart: series id suffix -> calendar months before the latest curve.
CURVES = {"latest": 0, "1m_ago": 1, "1y_ago": 12}


class RatesRequest(BaseModel):
    start: Annotated[
        date, check(lambda v: v >= TREASURY_FIRST, "Treasury yield curve data starts on 1990-01-02.")
    ] = RATES_START
    """First day of the spread history."""
    end: date | None = None
    """Last day considered (default: today, UTC). The latest curve is the newest on or before it."""
    source: Literal["treasury"] = "treasury"

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("start")
        if end is not None and start is not None and end < start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be on or after the start date.")
        return end


def _meta_details(found: YieldCurves) -> dict[str, str | float | int | None]:
    m = found.meta
    return {"title": m.title, "source": m.source, "frequency": m.frequency, "last_updated": m.last_updated}


@router.post("/rates")
def treasury_rates(req: RatesRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    """The latest Treasury par yield curve with the curves one month and one year
    earlier, and the 10Y-2Y spread history with its inversion periods (spread < 0).
    Metrics: ``latest:yield_2y``, ``latest:yield_10y`` (percent),
    ``latest:spread_10y_2y`` (percentage points). Series: ``yield_curve:<latest|1m_ago|1y_ago>``
    (x = maturity in years, details.date = the curve's date) and
    ``history:spread_10y_2y`` (bands = inversion periods)."""
    end = req.end or datetime.now(UTC).date()
    # Reach back far enough for the year-ago curve even when ``start`` is recent.
    fetch_from = min(req.start, rates.months_before(end, 12) - timedelta(days=14))
    found = data.yield_curves(ctx, start=fetch_from, end=end, source=req.source)
    curves = found.curves
    history = [(when, curve) for when, curve in curves if when >= req.start]
    latest_date = rates.curve_on_or_before(curves, end)[0] if any(c for _, c in curves) else None

    def curve(months: int) -> SeriesData:
        if latest_date is None:
            raise MissingData("No Treasury yield curve in the range.")
        when, points = rates.curve_on_or_before(curves, rates.months_before(latest_date, months))
        return SeriesData(rates.curve_points(points), details={"date": when.isoformat()})

    def latest_yield(months: float) -> Detailed:
        if latest_date is None:
            raise MissingData("No Treasury yield curve in the range.")
        when, points = rates.curve_on_or_before(curves, latest_date)
        if months not in points:
            raise MissingData(f"Treasury did not publish the {months / 12:g}-year yield on {when.isoformat()}.")
        return Detailed(points[months], {"date": when.isoformat(), "units": "Percent", **_meta_details(found)})

    spread = rates.term_spread(history)

    def latest_spread() -> Detailed:
        for when, value in reversed(spread):
            if value is not None:
                return Detailed(value, {"date": when.isoformat(), "units": "Percentage points", **_meta_details(found)})
        raise MissingData("No day in the range has both the 10-year and 2-year yields.")

    def spread_history() -> SeriesData:
        if not spread:
            raise MissingData("No Treasury yield curve in the range.")
        bands = [
            Band(start=first.isoformat(), end=last.isoformat(), label="Inverted")
            for first, last in rates.inversion_periods(spread)
        ]
        return SeriesData([(when.isoformat(), value) for when, value in spread], bands=bands)

    return envelope(
        tool=TOOL,
        request=req,
        metrics={
            "latest:yield_2y": metric(lambda: latest_yield(rates.TWO_YEARS), unit="percent"),
            "latest:yield_10y": metric(lambda: latest_yield(rates.TEN_YEARS), unit="percent"),
            "latest:spread_10y_2y": metric(latest_spread, unit="percentage_points"),
        },
        series={
            **{
                f"yield_curve:{key}": series(lambda months=months: curve(months), x_unit="years", y_unit="percent")
                for key, months in CURVES.items()
            },
            "history:spread_10y_2y": series(spread_history, x_unit="date", y_unit="percentage_points"),
        },
        source=found.source,
        data_cutoff=latest_date,
    )
