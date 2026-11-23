"""Fundamental screening metrics (P7): price-free ratios on unified line items.

Each metric names the line items it needs (``inputs``: item id and a year
offset, -1 = the prior year) and computes from a ``get(item_id, offset)``
callback that raises ``MissingData`` when the company didn't report the item.
A metric raises ``MetricError`` when a denominator is zero or negative, because
the ratio means nothing then (e.g. ROE on negative equity); see ``guards.positive``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, NamedTuple

from sextant_compute.analytics.guards import positive

Get = Callable[[str, int], float]
Unit = Literal["currency", "decimal", "ratio"]  # envelope units; "decimal" is shown as %


class Input(NamedTuple):
    """A line item a metric reads, and which year: 0 = the screened year, -1 = the one before."""

    item_id: str
    year_offset: int = 0


@dataclass(frozen=True)
class ScreenMetric:
    id: str
    label: str
    unit: Unit
    inputs: tuple[Input, ...]
    compute: Callable[[Get], float]


def _ratio(numerator: str, denominator: str, denominator_label: str) -> Callable[[Get], float]:
    def compute(get: Get) -> float:
        return get(numerator, 0) / positive(get(denominator, 0), denominator_label)

    return compute


def _growth(get: Get) -> float:
    return get("revenue", 0) / positive(get("revenue", -1), "Prior-year revenue") - 1


METRICS: dict[str, ScreenMetric] = {
    m.id: m
    for m in [
        ScreenMetric("revenue", "Revenue", "currency", (Input("revenue"),), lambda get: get("revenue", 0)),
        ScreenMetric("revenue_growth", "Revenue growth", "decimal", (Input("revenue"), Input("revenue", -1)), _growth),
        ScreenMetric(
            "gross_margin",
            "Gross margin",
            "decimal",
            (Input("gross_profit"), Input("revenue")),
            _ratio("gross_profit", "revenue", "Revenue"),
        ),
        ScreenMetric(
            "operating_margin",
            "Operating margin",
            "decimal",
            (Input("operating_income"), Input("revenue")),
            _ratio("operating_income", "revenue", "Revenue"),
        ),
        ScreenMetric(
            "net_margin",
            "Net margin",
            "decimal",
            (Input("net_income"), Input("revenue")),
            _ratio("net_income", "revenue", "Revenue"),
        ),
        ScreenMetric(
            "roe",
            "Return on equity",
            "decimal",
            (Input("net_income"), Input("total_equity")),
            _ratio("net_income", "total_equity", "Equity"),
        ),
        ScreenMetric(
            "debt_ratio",
            "Debt ratio",
            "decimal",
            (Input("total_liabilities"), Input("total_assets")),
            _ratio("total_liabilities", "total_assets", "Total assets"),
        ),
        ScreenMetric(
            "current_ratio",
            "Current ratio",
            "ratio",
            (Input("current_assets"), Input("current_liabilities")),
            _ratio("current_assets", "current_liabilities", "Current liabilities"),
        ),
    ]
}


def items_for(metric_ids: list[str]) -> dict[int, list[str]]:
    """Year offset -> line item ids the metrics need (deduplicated, in order)."""
    out: dict[int, list[str]] = {}
    for metric_id in metric_ids:
        for item_id, offset in METRICS[metric_id].inputs:
            bucket = out.setdefault(offset, [])
            if item_id not in bucket:
                bucket.append(item_id)
    return out
