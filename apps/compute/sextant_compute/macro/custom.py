"""Macro Dashboard (P5): search FRED and add more series (spec stories 78, 94).

Only public-domain series are offered or served; the FRED adapter enforces that
(ADR 0006), so a shared link naming a copyrighted series gets ``missing_data``
for it, never its data.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.data.adapters import EconomicSeries
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import MetricResult, ResultEnvelope, SeriesResult, envelope, metric, series
from sextant_compute.errors import INPUT_ERROR, check
from sextant_compute.macro.api import HISTORY_START, TOOL, _history, _latest

router = APIRouter(tags=["macro"])

SEARCH_LIMIT = 20
MAX_SERIES = 8
SERIES_ID = re.compile(r"^[A-Z0-9_]{1,40}$")


def _strip(value: object) -> object:
    return " ".join(value.split()) if isinstance(value, str) else value


class SearchRequest(BaseModel):
    query: Annotated[
        str, BeforeValidator(_strip), check(lambda v: 1 <= len(v) <= 100, "Enter a name, keyword or series id.")
    ]
    source: Literal["fred"] = "fred"


class SeriesHit(BaseModel):
    id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    last_updated: str
    observation_end: str


class SearchEnvelope(ResultEnvelope):
    query: str
    results: list[SeriesHit]


@router.post("/search")
def search_series(req: SearchRequest, data: Data, ctx: Ctx) -> SearchEnvelope:
    """Public-domain FRED series matching ``query``, best match first (at most 20).
    Copyrighted series are never offered."""
    hits = data.search_series(ctx, req.query, limit=SEARCH_LIMIT, source=req.source)
    base = envelope(tool=TOOL, request=req, metrics={}, source=data.source_info(req.source))
    return SearchEnvelope(
        **base.model_dump(), query=req.query, results=[SeriesHit(**h.__dict__) for h in hits]
    )


class SeriesRequest(BaseModel):
    series: list[str]
    """FRED series ids, in display order (upper-cased, duplicates dropped)."""
    start: date = HISTORY_START
    source: Literal["fred"] = "fred"

    @field_validator("series", mode="before")
    @classmethod
    def _normalize(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        ids = [v.strip().upper() if isinstance(v, str) else v for v in value]
        return list(dict.fromkeys(ids))

    @field_validator("series")
    @classmethod
    def _valid_ids(cls, ids: list[str]) -> list[str]:
        if not ids:
            raise PydanticCustomError(INPUT_ERROR, "Add at least one series.")
        if len(ids) > MAX_SERIES:
            raise PydanticCustomError(INPUT_ERROR, f"Add at most {MAX_SERIES} series.")
        bad = next((i for i in ids if not SERIES_ID.match(i)), None)
        if bad is not None:
            raise PydanticCustomError(INPUT_ERROR, f"{bad[:40]!r} is not a FRED series id (letters, digits, _).")
        return ids


def _unit(found: EconomicSeries | NoSuchData) -> str | None:
    """``percent`` for values already in percent (FRED units "Percent", "Percent
    Change ..."); otherwise none, and the page shows ``details.units``."""
    if isinstance(found, EconomicSeries) and found.meta.units.lower().startswith("percent"):
        return "percent"
    return None


@router.post("/series")
def added_series(req: SeriesRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    """Latest value + history + metadata for each requested series. Ids:
    metric ``latest:<SERIES_ID>`` (details as ``/indicators``), series
    ``history:<SERIES_ID>``. A series that is unknown, copyrighted or not public
    domain is ``missing_data`` on its own; a FRED outage is 503."""
    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    cutoffs: list[date] = []
    for series_id in req.series:
        found: EconomicSeries | NoSuchData
        try:
            found = data.economic_series(ctx, series_id, start=req.start, source=req.source)
        except NoSuchData as exc:
            found = exc
        if isinstance(found, EconomicSeries) and found.latest:
            cutoffs.append(found.latest[0])
        unit = _unit(found)
        metrics[f"latest:{series_id}"] = metric(lambda found=found: _latest(found), unit=unit)
        charts[f"history:{series_id}"] = series(lambda found=found: _history(found), x_unit="date", y_unit=unit)
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=data.source_info(req.source),
        data_cutoff=max(cutoffs) if cutoffs else None,
    )
