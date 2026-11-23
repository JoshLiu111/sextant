"""Turn a companyfacts body into quarterly ``FinancialStatements``.

Rules (on top of the annual ones in ``standardize``):

- Fiscal years come from the annual reports (their start and end), plus the
  year after the latest one, whose quarters may already be filed. A quarter's
  number is its position in the year: a 10-Q's year-to-date facts start on the
  fiscal year's first day and span about 3, 6 or 9 months. Q4 ends with the
  year. Labels are "Q2 FY2026" (the company's own fiscal year).
- Balance-sheet items are the instant at the quarter end (10-Q, or the 10-K
  for Q4).
- Flows (income, cash flow): the three-month fact when the company reports one.
  Otherwise the year-to-date fact minus the previous year-to-date one (10-Q cash
  flow statements are year to date). Companies file no Q4 report, so Q4 is the
  year (10-K) minus the nine months to Q3, or minus Q1 + Q2 + Q3. Each quarter
  holds only its own three months, so the four quarters add up to the year.
- Per-share amounts and weighted-average share counts don't add up across
  periods, so they are never subtracted: they come only from three-month facts,
  and Q4 is ``Missing`` saying why.
- As in the annual statements: the first tag with a value wins per period, the
  earliest filing wins among duplicates, then ``derive`` formulas fill gaps.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sextant_compute.data.edgar.mapping import LineItemSpec
from sextant_compute.data.edgar.standardize import (
    ANNUAL_FORMS,
    Fact,
    complete,
    facts_for,
    filing_url,
    first_reported,
    fiscal_periods,
)
from sextant_compute.data.statements import Company, Filing, FinancialStatements, FiscalPeriod, Reported
from sextant_compute.envelope import DataSource

QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A"})
FORMS = ANNUAL_FORMS | QUARTERLY_FORMS
QUARTER_DAYS = range(70, 111)
# Year-to-date spans by quarter: about 3, 6 and 9 months.
YTD_DAYS = {1: range(70, 111), 2: range(160, 201), 3: range(250, 291)}
MONTHS = {1: "three", 2: "six", 3: "nine"}


@dataclass(frozen=True)
class _Year:
    start: date
    end: date | None  # None: the year after the latest 10-K, not yet over
    fiscal_year: int
    filing: Filing | None  # its 10-K


@dataclass(frozen=True)
class _Quarter:
    year: _Year
    number: int
    start: date | None  # None when the previous quarter isn't in the data
    end: date


class _Spans:
    """One tag's duration facts by (start, end), earliest filed first."""

    def __init__(self, facts: Sequence[Fact]) -> None:
        self.by_span: dict[tuple[date | None, date], Fact] = {}
        self.by_end: dict[date, list[Fact]] = {}
        for f in sorted(facts, key=lambda f: (f.filed, f.accession)):
            self.by_span.setdefault((f.start, f.end), f)
            self.by_end.setdefault(f.end, []).append(f)

    def ytd(self, start: date, end: date) -> Fact | None:
        return self.by_span.get((start, end))

    def three_months(self, end: date) -> Fact | None:
        return next((f for f in self.by_end.get(end, []) if f.days in QUARTER_DAYS), None)


def _note(f: Fact) -> str:
    return f"{f.form} filed {f.filed.isoformat()}"


def standardize_quarterly(
    body: Mapping[str, Any], specs: Sequence[LineItemSpec], *, ticker: str, source: DataSource
) -> FinancialStatements:
    cik = int(body["cik"])
    company = Company(ticker=ticker, cik=cik, name=str(body.get("entityName") or ticker))

    annual_by_tag = {
        spec.id: [
            (str(tag), first_reported(facts_for(body, tag.taxonomy, tag.name, spec.item.unit, instant=spec.item.statement == "balance")))
            for tag in spec.tags
        ]
        for spec in specs
    }
    years = [
        _Year(p.start, p.end, p.fiscal_year, p.filing)
        for p in fiscal_periods(annual_by_tag, specs, cik)
        if p.start is not None
    ]
    if not years:
        return FinancialStatements(source, company, tuple(s.item for s in specs), (), {})
    years.append(_Year(years[-1].end + timedelta(days=1), None, years[-1].fiscal_year + 1, None))  # type: ignore[operator]

    flows: dict[str, list[tuple[str, _Spans]]] = {}
    instants: dict[str, list[tuple[str, dict[date, Fact]]]] = {}
    for spec in specs:
        for tag in spec.tags:
            if spec.item.statement == "balance":
                facts = facts_for(body, tag.taxonomy, tag.name, spec.item.unit, instant=True, forms=FORMS)
                instants.setdefault(spec.id, []).append((str(tag), first_reported(facts)))
            else:
                facts = facts_for(body, tag.taxonomy, tag.name, spec.item.unit, instant=False, forms=FORMS, days=None)
                flows.setdefault(spec.id, []).append((str(tag), _Spans(facts)))

    filings: dict[str, Filing] = {}

    def filing(f: Fact) -> Filing:
        if f.accession not in filings:
            filings[f.accession] = Filing(f.accession, f.form, f.filed, filing_url(cik, f.accession))
        return filings[f.accession]

    quarters, own = _quarters(years, [s for tags in flows.values() for _, s in tags], filing)
    periods = [
        FiscalPeriod(
            id=q.end.isoformat(),
            label=f"Q{q.number} FY{q.year.fiscal_year}",
            fiscal_year=q.year.fiscal_year,
            start=q.start,
            end=q.end,
            filed=own[q].filed,
            filing=own[q],
            fiscal_quarter=q.number,
        )
        for q in quarters
    ]
    by_end = {q.end: q for q in quarters}
    ends = {(q.year, q.number): q.end for q in quarters}

    found: dict[str, dict[str, Reported]] = {}
    missing: dict[str, dict[str, str]] = {}
    for spec in specs:
        row: dict[str, Reported] = {}
        additive = spec.item.unit == "USD"
        for p in periods:
            q = by_end[p.end]
            if spec.item.statement == "balance":
                for tag, facts in instants.get(spec.id, []):
                    if (fact := facts.get(p.end)) is not None:
                        row[p.id] = Reported(fact.value, filing(fact), tag=tag)
                        break
                continue
            for tag, spans in flows.get(spec.id, []):
                cell = _flow(spans, q, ends, additive, filing, tag)
                if cell is not None:
                    row[p.id] = cell
                    break
            if p.id not in row and not additive and q.number == 4:
                missing.setdefault(spec.id, {})[p.id] = (
                    f"{spec.item.label} is not reported for {p.label}: companies report per-share amounts and "
                    "weighted-average shares for the whole year, and the year minus three quarters isn't "
                    "meaningful for them."
                )
        found[spec.id] = row

    ever = {
        spec.id: any(facts for _, facts in instants.get(spec.id, []))
        or any(spans.by_span for _, spans in flows.get(spec.id, []))
        for spec in specs
    }
    return FinancialStatements(
        source=source,
        company=company,
        items=tuple(s.item for s in specs),
        periods=tuple(periods),
        cells=complete(specs, periods, found, ever, missing),
    )


def _quarters(
    years: Sequence[_Year], spans: Sequence[_Spans], filing: Callable[[Fact], Filing]
) -> tuple[list[_Quarter], dict[_Quarter, Filing]]:
    """Every fiscal quarter with data, oldest first, and each one's own report
    (the earliest 10-Q reporting its year to date; the 10-K for Q4)."""
    quarters: list[_Quarter] = []
    own: dict[_Quarter, Filing] = {}
    for year in years:
        found: dict[int, Counter[date]] = {}
        first: dict[date, Fact] = {}
        for s in spans:
            for (start, end), f in s.by_span.items():
                if start != year.start or f.form not in QUARTERLY_FORMS:
                    continue
                for number, days in YTD_DAYS.items():
                    if f.days in days:
                        found.setdefault(number, Counter())[end] += 1
                        if end not in first or (f.filed, f.accession) < (first[end].filed, first[end].accession):
                            first[end] = f
        ends = {n: c.most_common(1)[0][0] for n, c in found.items()}
        if year.end is not None and year.filing is not None and ends:
            ends[4] = year.end
        for number in sorted(ends):
            previous = year.start - timedelta(days=1) if number == 1 else ends.get(number - 1)
            q = _Quarter(year, number, previous + timedelta(days=1) if previous else None, ends[number])
            quarters.append(q)
            own[q] = year.filing if number == 4 and year.filing is not None else filing(first[q.end])
    return quarters, own


def _flow(
    spans: _Spans,
    q: _Quarter,
    ends: Mapping[tuple[_Year, int], date],
    additive: bool,
    filing: Callable[[Fact], Filing],
    tag: str,
) -> Reported | None:
    """One tag's value for the three months of ``q`` (see the module docstring)."""
    if (f := spans.three_months(q.end)) is not None:
        return Reported(f.value, filing(f), tag=tag)
    if not additive or q.number == 1:
        return None
    now = spans.ytd(q.year.start, q.end)
    if now is None:
        return None
    what = f"FY{q.year.fiscal_year} ({_note(now)})" if q.number == 4 else f"the {MONTHS[q.number]} months to {q.end} ({_note(now)})"
    prev_end = ends.get((q.year, q.number - 1))
    before = spans.ytd(q.year.start, prev_end) if prev_end else None
    if before is not None:
        later = max(now, before, key=lambda f: (f.filed, f.accession))
        return Reported(
            now.value - before.value,
            filing(later),
            tag=tag,
            derived_from=f"{what} minus the {MONTHS[q.number - 1]} months to {prev_end} ({_note(before)})",
        )
    earlier = [
        _flow(spans, _Quarter(q.year, n, q.year.start, ends[(q.year, n)]), ends, additive, filing, tag)
        if (q.year, n) in ends
        else None
        for n in range(1, q.number)
    ]
    if any(c is None for c in earlier):
        return None
    cells = [c for c in earlier if c is not None]
    names = ", ".join(f"Q{n}" for n in range(1, q.number))
    return Reported(
        now.value - sum(c.value for c in cells),
        filing(now),
        tag=tag,
        derived_from=f"{what} minus {names} FY{q.year.fiscal_year}",
    )
