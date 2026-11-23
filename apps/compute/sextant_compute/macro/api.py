"""Macro Dashboard (P5) endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from sextant_compute.data.adapters import EconomicSeries
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import Detailed, MetricResult, MissingData, ResultEnvelope, SeriesResult, envelope, metric, series

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
