"""Standardized financial statements: the provider-neutral shape tools consume.

``FinancialStatements`` is a grid of unified line items (rows, see
``data/edgar/line_items.toml``) by fiscal periods (columns, oldest first). Each
cell is either ``Reported`` (a value with the filing it came from) or
``Missing`` (with a reason a person can read). Tools read values with
``statements.value(item_id, period_id)``, which raises ``MissingData`` naming the
item, so a ratio built in ``metric(lambda: ...)`` goes ``missing_data`` on its own.

Look-ahead: ``FiscalPeriod.filed`` is the date the period's own annual report
was filed; a daily metric dated before it must use an older period. A few cells
can come from a later filing (an item the company first tagged a year later);
each ``Reported.filing.filed`` is exact, so strict point-in-time code checks it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal

from sextant_compute.analytics.errors import MissingData
from sextant_compute.envelope import DataSource

Statement = Literal["income", "balance", "cash_flow"]
STATEMENTS: tuple[Statement, ...] = ("income", "balance", "cash_flow")
MissingReason = Literal["not_reported", "not_reported_for_period"]


@dataclass(frozen=True)
class LineItem:
    id: str
    label: str
    statement: Statement
    unit: str  # "USD", "USD/shares" or "shares"
    display: bool = True


@dataclass(frozen=True)
class Filing:
    """The SEC filing a value came from."""

    accession: str  # "0000320193-25-000079"
    form: str  # "10-K", "10-K/A", ...
    filed: date
    url: str  # the filing index page on sec.gov


@dataclass(frozen=True)
class Reported:
    value: float
    filing: Filing
    tag: str | None = None  # the XBRL tag used, e.g. "us-gaap:Revenues"; None when derived
    derived_from: str | None = None  # the formula, e.g. "revenue - cost_of_revenue"


@dataclass(frozen=True)
class Missing:
    """``not_reported``: the company never reported any candidate tag.
    ``not_reported_for_period``: it reports the item, just not for this period."""

    reason: MissingReason
    message: str


Cell = Reported | Missing


@dataclass(frozen=True)
class FiscalPeriod:
    id: str  # the period end as ISO date, e.g. "2025-09-27"; unique within a company
    label: str  # "FY2025" (the company's own fiscal year number)
    fiscal_year: int
    start: date | None
    end: date
    filed: date  # when the period's own annual report was filed (= filing.filed)
    filing: Filing  # the period's own annual report (most values come from it)


@dataclass(frozen=True)
class Company:
    ticker: str
    cik: int
    name: str


@dataclass(frozen=True)
class FinancialStatements:
    source: DataSource
    company: Company
    items: tuple[LineItem, ...]
    periods: tuple[FiscalPeriod, ...]  # oldest first
    cells: Mapping[str, Mapping[str, Cell]]  # item id -> period id -> cell

    def item(self, item_id: str) -> LineItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def cell(self, item_id: str, period_id: str) -> Cell:
        return self.cells[item_id][period_id]

    def value(self, item_id: str, period_id: str) -> float:
        """The reported value, or ``MissingData`` with the reason (names the item)."""
        cell = self.cell(item_id, period_id)
        if isinstance(cell, Missing):
            raise MissingData(cell.message)
        return cell.value

    def last(self, n: int) -> FinancialStatements:
        """Only the ``n`` most recent periods."""
        periods = self.periods[-n:] if n > 0 else ()
        keep = {p.id for p in periods}
        cells = {i: {p: c for p, c in row.items() if p in keep} for i, row in self.cells.items()}
        return replace(self, periods=periods, cells=cells)

    # --- JSON (cache) -------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        filings: dict[str, Filing] = {}

        def ref(f: Filing) -> str:
            filings[f.accession] = f
            return f.accession

        def cell_json(c: Cell) -> dict[str, Any]:
            if isinstance(c, Missing):
                return {"missing": c.reason, "message": c.message}
            return {"value": c.value, "filing": ref(c.filing), "tag": c.tag, "derived_from": c.derived_from}

        periods = [
            {
                "id": p.id,
                "label": p.label,
                "fiscal_year": p.fiscal_year,
                "start": p.start.isoformat() if p.start else None,
                "end": p.end.isoformat(),
                "filed": p.filed.isoformat(),
                "filing": ref(p.filing),
            }
            for p in self.periods
        ]
        cells = {i: {p: cell_json(c) for p, c in row.items()} for i, row in self.cells.items()}
        return {
            "source": self.source.model_dump(),
            "company": {"ticker": self.company.ticker, "cik": self.company.cik, "name": self.company.name},
            "items": [
                {"id": i.id, "label": i.label, "statement": i.statement, "unit": i.unit, "display": i.display}
                for i in self.items
            ],
            "filings": {
                a: {"form": f.form, "filed": f.filed.isoformat(), "url": f.url} for a, f in filings.items()
            },
            "periods": periods,
            "cells": cells,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> FinancialStatements:
        filings = {
            a: Filing(accession=a, form=f["form"], filed=date.fromisoformat(f["filed"]), url=f["url"])
            for a, f in raw["filings"].items()
        }

        def cell(c: Mapping[str, Any]) -> Cell:
            if "missing" in c:
                return Missing(reason=c["missing"], message=c["message"])
            return Reported(
                value=float(c["value"]), filing=filings[c["filing"]], tag=c["tag"], derived_from=c["derived_from"]
            )

        return cls(
            source=DataSource(**raw["source"]),
            company=Company(**raw["company"]),
            items=tuple(LineItem(**i) for i in raw["items"]),
            periods=tuple(
                FiscalPeriod(
                    id=p["id"],
                    label=p["label"],
                    fiscal_year=p["fiscal_year"],
                    start=date.fromisoformat(p["start"]) if p["start"] else None,
                    end=date.fromisoformat(p["end"]),
                    filed=date.fromisoformat(p["filed"]),
                    filing=filings[p["filing"]],
                )
                for p in raw["periods"]
            ),
            cells={i: {p: cell(c) for p, c in row.items()} for i, row in raw["cells"].items()},
        )
