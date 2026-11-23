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

from sextant_compute.analytics.guards import positive

Get = Callable[[str, int], float]


@dataclass(frozen=True)
class ScreenMetric:
    id: str
    label: str
    unit: str  # envelope unit: "currency", "decimal" (shown as %), "ratio"
    inputs: tuple[tuple[str, int], ...]
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
        ScreenMetric("revenue", "Revenue", "currency", (("revenue", 0),), lambda get: get("revenue", 0)),
        ScreenMetric("revenue_growth", "Revenue growth", "decimal", (("revenue", 0), ("revenue", -1)), _growth),
        ScreenMetric(
            "gross_margin",
            "Gross margin",
            "decimal",
            (("gross_profit", 0), ("revenue", 0)),
            _ratio("gross_profit", "revenue", "Revenue"),
        ),
        ScreenMetric(
            "operating_margin",
            "Operating margin",
            "decimal",
            (("operating_income", 0), ("revenue", 0)),
            _ratio("operating_income", "revenue", "Revenue"),
        ),
        ScreenMetric(
            "net_margin",
            "Net margin",
            "decimal",
            (("net_income", 0), ("revenue", 0)),
            _ratio("net_income", "revenue", "Revenue"),
        ),
        ScreenMetric(
            "roe",
            "Return on equity",
            "decimal",
            (("net_income", 0), ("total_equity", 0)),
            _ratio("net_income", "total_equity", "Equity"),
        ),
        ScreenMetric(
            "debt_ratio",
            "Debt ratio",
            "decimal",
            (("total_liabilities", 0), ("total_assets", 0)),
            _ratio("total_liabilities", "total_assets", "Total assets"),
        ),
        ScreenMetric(
            "current_ratio",
            "Current ratio",
            "ratio",
            (("current_assets", 0), ("current_liabilities", 0)),
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
