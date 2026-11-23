"""Cross-sections: one unified line item, one fiscal year, every company.

The provider-neutral shape behind the screener (P7). EDGAR builds it from XBRL
frames (``data/edgar/frames.py``); the line items are the same ones the
standardized statements use (``data/edgar/line_items.toml``), so a screener
value and the P1 statements cell for the same company and year agree, except
that a frame holds the *last filed* value (restatements win) while statements
keep the first reported one.

A frame is calendar-aligned: year 2025 holds, for each company, the fiscal year
that most closely fits calendar 2025 (AAPL: the year ended 2025-09-27). Each
value carries its own ``end`` date.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class CompanyValue:
    """One company's value of the item for the year."""

    cik: int
    ticker: str  # the company's primary ticker (first in SEC's ticker map)
    name: str
    value: float
    end: date  # the company's own period end (fiscal year end, or the balance-sheet date)
    accession: str  # the filing the value was last filed in
    tag: str | None = None  # the XBRL tag used; None when derived
    derived_from: str | None = None  # the formula, e.g. "revenue - cost_of_revenue"


@dataclass(frozen=True)
class CrossSection:
    """``values`` is keyed by CIK; companies that didn't report the item are absent."""

    item_id: str
    label: str  # the line item's display name, e.g. "Gross Profit"
    year: int
    values: Mapping[int, CompanyValue]

    def to_json(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "label": self.label,
            "year": self.year,
            "values": [
                [v.cik, v.ticker, v.name, v.value, v.end.isoformat(), v.accession, v.tag, v.derived_from]
                for v in self.values.values()
            ],
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> CrossSection:
        values = {}
        for cik, ticker, name, value, end, accession, tag, derived_from in raw["values"]:
            values[cik] = CompanyValue(cik, ticker, name, value, date.fromisoformat(end), accession, tag, derived_from)
        return cls(item_id=raw["item_id"], label=raw["label"], year=raw["year"], values=values)
