"""The unified result envelope every compute endpoint returns.

Shape (JSON)::

    {
      "calculation_id": "calc_<32 hex>",
      "tool": "options",
      "metrics": {"<metric_id>": {"value": 1.23 | null, "status": "ok" | "missing_data" | "error",
                                  "reason": str | null, "unit": str | null,
                                  "details": {"<key>": str | number | null}}},
      "series":  {"<series_id>": {"status": ..., "reason": ..., "x_unit": ..., "y_unit": ...,
                                  "points": [{"x": number | "YYYY-MM-DD", "y": number | null}],
                                  "details": {"<key>": str | number | null},
                                  "bands": [{"start": x, "end": x, "label": str | null}]}},
      "source":  {"id": "user_input", "name": "User input", "is_demo": false},
      "meta":    {"parameters": {...request...}, "computed_at": ISO-8601 UTC, "data_cutoff": date | null}
    }

Per-metric error isolation: compute each metric through ``metric(...)`` (or each
series through ``series(...)``). The analytics function raises ``MissingData``
or ``MetricError`` for *expected* problems (missing line item, no IV solution);
only that metric gets a non-ok status. Anything else (TypeError, bugs) propagates
and fails the request, so code defects are never hidden.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

from sextant_compute.analytics.errors import MetricError, MissingData

__all__ = [
    "Band",
    "CalculationMeta",
    "DataSource",
    "Detailed",
    "MetricError",
    "MetricResult",
    "MetricStatus",
    "MissingData",
    "Point",
    "ResultEnvelope",
    "SeriesData",
    "SeriesResult",
    "USER_INPUT",
    "envelope",
    "metric",
    "new_calculation_id",
    "series",
    "thin_points",
]


class MetricStatus(StrEnum):
    OK = "ok"
    MISSING_DATA = "missing_data"
    ERROR = "error"


Detail = str | float | int | None


class MetricResult(BaseModel):
    value: float | None
    status: MetricStatus
    reason: str | None = None
    unit: str | None = None
    details: dict[str, Detail] = Field(default_factory=dict)
    """Extra facts about an ok value, e.g. a max drawdown's ``peak``/``trough`` dates
    (ISO strings) or a score's zone. Empty unless the metric returns ``Detailed``."""


class Detailed(NamedTuple):
    """Return this from a ``metric`` computation to attach ``details`` to the value."""

    value: float
    details: dict[str, Detail]


class Point(BaseModel):
    x: float | str
    y: float | None


class Band(BaseModel):
    """A shaded x range on a chart, e.g. an inversion period (``start``..``end`` inclusive)."""

    start: float | str
    end: float | str
    label: str | None = None


class SeriesResult(BaseModel):
    status: MetricStatus
    reason: str | None = None
    x_unit: str | None = None
    y_unit: str | None = None
    points: list[Point] = Field(default_factory=list)
    details: dict[str, Detail] = Field(default_factory=dict)
    """Extra facts about the series, e.g. the date a yield curve was observed."""
    bands: list[Band] = Field(default_factory=list)
    """Shaded x ranges to draw with the series (in the series' x unit)."""


class SeriesData(NamedTuple):
    """Return this from a ``series`` computation to attach ``details`` and ``bands``."""

    points: Sequence[tuple[float | str, float | None]]
    details: dict[str, Detail] = {}
    bands: Sequence[Band] = ()


class DataSource(BaseModel):
    id: str
    name: str
    is_demo: bool


USER_INPUT = DataSource(id="user_input", name="User input", is_demo=False)


class CalculationMeta(BaseModel):
    parameters: dict[str, Any]
    computed_at: datetime
    data_cutoff: date | None = None


class ResultEnvelope(BaseModel):
    calculation_id: str
    tool: str
    metrics: dict[str, MetricResult]
    series: dict[str, SeriesResult] = Field(default_factory=dict)
    source: DataSource
    meta: CalculationMeta


def metric(compute: Callable[[], float | Detailed], *, unit: str | None = None) -> MetricResult:
    """Run one metric's computation, isolating expected failures to this metric."""
    try:
        out = compute()
        if isinstance(out, Detailed):
            return MetricResult(value=float(out.value), status=MetricStatus.OK, unit=unit, details=out.details)
        return MetricResult(value=float(out), status=MetricStatus.OK, unit=unit)
    except MissingData as exc:
        return MetricResult(value=None, status=MetricStatus.MISSING_DATA, reason=str(exc), unit=unit)
    except MetricError as exc:
        return MetricResult(value=None, status=MetricStatus.ERROR, reason=str(exc), unit=unit)


def thin_points(
    points: Sequence[tuple[float | str, float | None]], max_points: int
) -> list[tuple[float | str, float | None]]:
    """At most ``max_points`` of ``points`` (x-ordered), for drawing.

    Keeps the first and the last point, and from each of ``(max_points - 2) // 2``
    equal runs of the points between them its lowest and highest ``y``, in x
    order. So a thinned line still spans the whole range and still reaches every
    run's extremes (a drawdown's trough, a volatility spike) on their own x.
    """
    if len(points) <= max_points:
        return list(points)
    inner = points[1:-1]
    buckets = max(1, (max_points - 2) // 2)
    size = len(inner) / buckets
    kept: list[int] = []
    for b in range(buckets):
        run = range(round(b * size), round((b + 1) * size))
        valued = [i for i in run if inner[i][1] is not None]
        if not valued:
            kept.extend(run[:1])
            continue
        low = min(valued, key=lambda i: inner[i][1])  # type: ignore[arg-type,return-value]
        high = max(valued, key=lambda i: inner[i][1])  # type: ignore[arg-type,return-value]
        kept.extend(sorted({low, high}))
    return [points[0], *(inner[i] for i in kept), points[-1]]


def series(
    compute: Callable[[], Sequence[tuple[float | str, float | None]] | SeriesData],
    *,
    x_unit: str | None = None,
    y_unit: str | None = None,
    max_points: int | None = None,
) -> SeriesResult:
    """Run one series' computation with the same isolation rules as ``metric``.

    ``max_points`` thins a long series for drawing (``thin_points``); compute any
    metric from the full data, never from a thinned series."""
    try:
        out = compute()
        data = out if isinstance(out, SeriesData) else SeriesData(out)
        points = data.points if max_points is None else thin_points(data.points, max_points)
        return SeriesResult(
            status=MetricStatus.OK,
            x_unit=x_unit,
            y_unit=y_unit,
            points=[Point(x=x, y=y) for x, y in points],
            details=dict(data.details),
            bands=list(data.bands),
        )
    except MissingData as exc:
        return SeriesResult(status=MetricStatus.MISSING_DATA, reason=str(exc), x_unit=x_unit, y_unit=y_unit)
    except MetricError as exc:
        return SeriesResult(status=MetricStatus.ERROR, reason=str(exc), x_unit=x_unit, y_unit=y_unit)


def new_calculation_id() -> str:
    return f"calc_{uuid.uuid4().hex}"


def envelope(
    *,
    tool: str,
    request: BaseModel,
    metrics: dict[str, MetricResult],
    series: dict[str, SeriesResult] | None = None,
    source: DataSource = USER_INPUT,
    data_cutoff: date | None = None,
) -> ResultEnvelope:
    """Wrap computed metrics in the envelope, recording the request as parameters."""
    return ResultEnvelope(
        calculation_id=new_calculation_id(),
        tool=tool,
        metrics=metrics,
        series=series or {},
        source=source,
        meta=CalculationMeta(
            parameters=request.model_dump(mode="json"),
            computed_at=datetime.now(UTC),
            data_cutoff=data_cutoff,
        ),
    )
