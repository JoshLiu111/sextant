"""Turn a companyfacts body into ``FinancialStatements`` using the line-item mapping.

Rules (annual statements):

- Only annual-report facts count: form in ``ANNUAL_FORMS``. Duration facts
  (income, cash flow) must span about a year (``ANNUAL_DAYS``); balance-sheet
  facts are instants (no ``start``).
- Fiscal periods: each annual report's own period is the latest annual duration
  it reports. The earliest report for a period end is that period's filing; its
  ``fy`` names the fiscal year ("FY2025").
- Per item and period, the first candidate tag with a fact for that period wins
  (tags go stale, so the choice is per period, not per company). Among duplicate
  facts (comparatives in later reports, restatements) the earliest filed wins:
  values are "as first reported", which keeps them free of look-ahead.
- No tag: try the item's ``derive`` formula; else ``Missing`` with a reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sextant_compute.data.edgar.mapping import LineItemSpec
from sextant_compute.data.statements import (
    Cell,
    Company,
    Filing,
    FinancialStatements,
    FiscalPeriod,
    Missing,
    Reported,
)
from sextant_compute.envelope import DataSource

ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A"})
ANNUAL_DAYS = range(335, 396)
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"


def filing_url(cik: int, accession: str) -> str:
    """The filing's index page on sec.gov (CIK without zeros, accession with and without dashes)."""
    return f"{ARCHIVES_URL}/{cik}/{accession.replace('-', '')}/{accession}-index.htm"


@dataclass(frozen=True)
class Fact:
    start: date | None
    end: date
    value: float
    accession: str
    form: str
    filed: date
    fy: int | None

    @property
    def days(self) -> int | None:
        return (self.end - self.start).days if self.start else None


def facts_for(
    body: Mapping[str, Any],
    taxonomy: str,
    name: str,
    unit: str,
    *,
    instant: bool,
    forms: frozenset[str] = ANNUAL_FORMS,
    days: range | None = ANNUAL_DAYS,
) -> list[Fact]:
    """The tag's facts from ``forms``: instants, or durations spanning ``days``
    (any length when ``days`` is None)."""
    concept = body.get("facts", {}).get(taxonomy, {}).get(name)
    if not concept:
        return []
    out = []
    for row in concept.get("units", {}).get(unit, []):
        if row.get("form") not in forms or row.get("val") is None:
            continue
        start = date.fromisoformat(row["start"]) if row.get("start") else None
        if instant != (start is None):
            continue
        fact = Fact(
            start=start,
            end=date.fromisoformat(row["end"]),
            value=float(row["val"]),
            accession=row["accn"],
            form=row["form"],
            filed=date.fromisoformat(row["filed"]),
            fy=row.get("fy"),
        )
        if not instant and days is not None and fact.days not in days:
            continue
        out.append(fact)
    return out


def first_reported(facts: Sequence[Fact]) -> dict[date, Fact]:
    """Per period end, the earliest-filed fact."""
    best: dict[date, Fact] = {}
    for f in facts:
        cur = best.get(f.end)
        if cur is None or (f.filed, f.accession) < (cur.filed, cur.accession):
            best[f.end] = f
    return best


def standardize(
    body: Mapping[str, Any], specs: Sequence[LineItemSpec], *, ticker: str, source: DataSource
) -> FinancialStatements:
    cik = int(body["cik"])
    company = Company(ticker=ticker, cik=cik, name=str(body.get("entityName") or ticker))

    # Per item, per candidate tag (priority order): period end -> first-reported fact.
    by_tag: dict[str, list[tuple[str, dict[date, Fact]]]] = {}
    for spec in specs:
        instant = spec.item.statement == "balance"
        by_tag[spec.id] = [
            (str(tag), first_reported(facts_for(body, tag.taxonomy, tag.name, spec.item.unit, instant=instant)))
            for tag in spec.tags
        ]

    periods = fiscal_periods(by_tag, specs, cik)
    filings: dict[str, Filing] = {}

    def filing(f: Fact) -> Filing:
        if f.accession not in filings:
            filings[f.accession] = Filing(f.accession, f.form, f.filed, filing_url(cik, f.accession))
        return filings[f.accession]

    found: dict[str, dict[str, Reported]] = {}
    for spec in specs:
        row: dict[str, Reported] = {}
        for p in periods:
            for tag, facts in by_tag[spec.id]:
                fact = facts.get(p.end)
                if fact is not None:
                    row[p.id] = Reported(value=fact.value, filing=filing(fact), tag=tag)
                    break
        found[spec.id] = row

    ever = {spec.id: any(facts for _, facts in by_tag[spec.id]) for spec in specs}
    cells = complete(specs, periods, found, ever)

    return FinancialStatements(
        source=source,
        company=company,
        items=tuple(s.item for s in specs),
        periods=tuple(periods),
        cells=cells,
    )



def complete(
    specs: Sequence[LineItemSpec],
    periods: Sequence[FiscalPeriod],
    found: Mapping[str, dict[str, Reported]],
    ever: Mapping[str, bool],
    missing: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, dict[str, Cell]]:
    """Fill each item's gaps: its ``derive`` formula when every input is there,
    else ``Missing``. ``ever``: whether the company reports the item at all;
    ``missing``: item -> period id -> a message to use instead of the default."""
    for spec in specs:
        if spec.derive is None:
            continue
        row = found[spec.id]
        for p in periods:
            if p.id in row:
                continue
            inputs = [(sign, found[ref].get(p.id)) for sign, ref in spec.derive.terms]
            if all(cell is not None for _, cell in inputs):
                cells = [(sign, cell) for sign, cell in inputs if cell is not None]
                source_filing = max((c.filing for _, c in cells), key=lambda f: (f.filed, f.accession))
                row[p.id] = Reported(
                    value=sum(sign * c.value for sign, c in cells),
                    filing=source_filing,
                    derived_from=spec.derive.formula,
                )

    out: dict[str, dict[str, Cell]] = {}
    for spec in specs:
        row = found[spec.id]
        label = spec.item.label
        special = (missing or {}).get(spec.id, {})
        out[spec.id] = {
            p.id: row.get(p.id)
            or (
                Missing("not_reported_for_period", special[p.id])
                if p.id in special
                else Missing("not_reported_for_period", f"{label} is not reported by this company for {p.label}.")
                if ever[spec.id] or row
                else Missing("not_reported", f"{label} is not reported by this company.")
            )
            for p in periods
        }
    return out

def fiscal_periods(
    by_tag: Mapping[str, list[tuple[str, dict[date, Fact]]]], specs: Sequence[LineItemSpec], cik: int
) -> list[FiscalPeriod]:
    """One period per annual report's own fiscal year (see module docstring)."""
    durations: list[Fact] = []
    for spec in specs:
        if spec.item.statement != "balance":
            for _, facts in by_tag[spec.id]:
                durations.extend(facts.values())
    own_end: dict[str, Fact] = {}  # accession -> its latest annual duration fact
    for f in durations:
        cur = own_end.get(f.accession)
        if cur is None or f.end > cur.end:
            own_end[f.accession] = f
    first: dict[date, Fact] = first_reported(list(own_end.values()))
    periods = []
    for end in sorted(first):
        f = first[end]
        fy = f.fy if f.fy is not None else end.year
        periods.append(
            FiscalPeriod(
                id=end.isoformat(),
                label=f"FY{fy}",
                fiscal_year=fy,
                start=f.start,
                end=end,
                filed=f.filed,
                filing=Filing(f.accession, f.form, f.filed, filing_url(cik, f.accession)),
            )
        )
    return periods
